Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# B3.3 shared reproducible-build control library.
# Reuses accepted B3.2 low-level helpers without modifying B3.2 behavior.

$B32Common = Join-Path $PSScriptRoot "B3.2_Common.ps1"

if (-not (Test-Path -LiteralPath $B32Common -PathType Leaf)) {
    throw "B3.2 common library is missing: $B32Common"
}

. $B32Common

$script:B33_DefaultRepoRoot = "D:\OneDrive\SQD"
$script:B33_DefaultIdfPath = "D:\esp\v6.0.2\esp-idf"
$script:B33_RequiredIdfVersionPattern = '^ESP-IDF v6\.0\.2(?:\b|$)'
$script:B33_RequiredPythonVersion = "Python 3.11.15"
$script:B33_RequiredPythonEnvPath = "C:\Users\parth\.espressif\python_env\idf6.0_py3.11_env"
$script:B33_ExpectedBranch = "feat/b3.3-reproducible-build-controls"
$script:B33_Target = "esp32s3"
$script:B33_HardwareCompatibility = "heltec-wifi-lora-32-v3"

function Get-B33Timestamp {
    [CmdletBinding()]
    param()

    Get-Date -Format "yyyyMMdd_HHmmss"
}

function Get-B33EvidenceDirectory {
    [CmdletBinding()]
    param(
        [string]$RepoRoot = $script:B33_DefaultRepoRoot
    )

    New-B32Directory -Path (Join-Path $RepoRoot "docs\evidence\logs\B3.3")
}

function New-B33EvidencePath {
    [CmdletBinding()]
    param(
        [string]$RepoRoot = $script:B33_DefaultRepoRoot,

        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$Stem,

        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$Extension,

        [string]$Timestamp = (Get-B33Timestamp)
    )

    $EvidenceDir = Get-B33EvidenceDirectory -RepoRoot $RepoRoot
    $CleanExtension = $Extension.TrimStart(".")

    Join-Path $EvidenceDir "${Stem}_${Timestamp}.${CleanExtension}"
}

function Assert-B33FeatureBranch {
    [CmdletBinding()]
    param(
        [string]$RepoRoot = $script:B33_DefaultRepoRoot
    )

    $Branch = Invoke-B32GitCapture `
        -RepoRoot $RepoRoot `
        -Arguments @("branch", "--show-current")

    if ($Branch -ne $script:B33_ExpectedBranch) {
        throw "Expected Git branch '$($script:B33_ExpectedBranch)'; current branch is '$Branch'."
    }

    $Branch
}

function Get-B33SourceDateEpoch {
    [CmdletBinding()]
    param(
        [string]$RepoRoot = $script:B33_DefaultRepoRoot
    )

    $Epoch = Invoke-B32GitCapture `
        -RepoRoot $RepoRoot `
        -Arguments @("show", "-s", "--format=%ct", "HEAD")

    if ($Epoch -notmatch '^[0-9]+$') {
        throw "Git commit timestamp is invalid: '$Epoch'."
    }

    [int64]$Epoch
}

function Initialize-B33Environment {
    [CmdletBinding()]
    param(
        [string]$RepoRoot = $script:B33_DefaultRepoRoot,

        [string]$IdfPath = $script:B33_DefaultIdfPath
    )

    $RequiredPythonEnvPath = Assert-B32Directory `
        -Path $script:B33_RequiredPythonEnvPath `
        -Description "Approved ESP-IDF Python environment"

    $RequiredPythonScripts = Assert-B32Directory `
        -Path (Join-Path $RequiredPythonEnvPath "Scripts") `
        -Description "Approved ESP-IDF Python Scripts"

    $RequiredPythonExe = Assert-B32File `
        -Path (Join-Path $RequiredPythonScripts "python.exe") `
        -Description "Approved ESP-IDF Python executable"

    $env:IDF_PYTHON_ENV_PATH = $RequiredPythonEnvPath

    $PathEntries = @(
        $RequiredPythonScripts
        @(
            $env:Path -split ";" |
            Where-Object {
                -not [string]::IsNullOrWhiteSpace($_) -and
                -not $_.StartsWith(
                    (Join-Path $env:IDF_TOOLS_PATH "python_env"),
                    [System.StringComparison]::OrdinalIgnoreCase
                )
            }
        )
    )

    $env:Path = $PathEntries -join ";"

    # B3.2 considers the environment active from IDF/Python variables alone.
    # Force export when mandatory ESP-IDF build tools are not actually on PATH.
    $RequiredCommandsAvailable = (
        $null -ne (Get-Command cmake.exe -ErrorAction SilentlyContinue) -and
        $null -ne (Get-Command ninja.exe -ErrorAction SilentlyContinue)
    )

    if (-not $RequiredCommandsAvailable) {
        Remove-Item Env:ESP_IDF_VERSION -ErrorAction SilentlyContinue
    }

    $Environment = Initialize-B32IdfEnvironment `
        -RepoRoot $RepoRoot `
        -IdfPath $IdfPath `
        -HardwareCompatibility $script:B33_HardwareCompatibility

    if (-not [string]::Equals(
        $Environment.PythonExe,
        $RequiredPythonExe,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Unapproved Python executable '$($Environment.PythonExe)'. Expected '$RequiredPythonExe'."
    }

    $PythonVersion = (
        & $Environment.PythonExe --version 2>&1 |
        Out-String
    ).Trim()

    if ($LASTEXITCODE -ne 0) {
        throw "Python version command failed with exit code $LASTEXITCODE."
    }

    if ($PythonVersion -ne $script:B33_RequiredPythonVersion) {
        throw "Unapproved Python version '$PythonVersion'. Expected '$($script:B33_RequiredPythonVersion)'."
    }

    $ExpectedIdfPath = (
        Resolve-Path -LiteralPath $script:B33_DefaultIdfPath -ErrorAction Stop
    ).Path

    if (-not [string]::Equals(
        $Environment.IdfPath,
        $ExpectedIdfPath,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Unapproved ESP-IDF path '$($Environment.IdfPath)'. Expected '$ExpectedIdfPath'."
    }

    if ($Environment.IdfVersion -notmatch $script:B33_RequiredIdfVersionPattern) {
        throw "Unapproved ESP-IDF version '$($Environment.IdfVersion)'. Expected ESP-IDF v6.0.2."
    }

    $env:SOURCE_DATE_EPOCH = [string](Get-B33SourceDateEpoch -RepoRoot $Environment.RepoRoot)
    $env:SQD_HARDWARE_COMPATIBILITY = $script:B33_HardwareCompatibility

    [PSCustomObject]@{
        RepoRoot = $Environment.RepoRoot
        IdfPath = $Environment.IdfPath
        IdfPy = $Environment.IdfPy
        PythonExe = $Environment.PythonExe
        IdfVersion = $Environment.IdfVersion
        Target = $script:B33_Target
        HardwareCompatibility = $script:B33_HardwareCompatibility
        SourceDateEpoch = [int64]$env:SOURCE_DATE_EPOCH
    }
}

function Get-B33BuildLayout {
    [CmdletBinding()]
    param(
        [string]$RepoRoot = $script:B33_DefaultRepoRoot,

        [ValidateSet("debug", "validation", "production")]
        [string]$Profile = "production",

        [Parameter(Mandatory)]
        [ValidatePattern('^[A-Za-z0-9_.-]+$')]
        [string]$Instance
    )

    $NormalizedProfile = Assert-B32Profile -Profile $Profile
    $BuildRoot = Join-Path $RepoRoot "build\b3.3"
    $BuildDir = Join-Path $BuildRoot "${NormalizedProfile}_${Instance}"

    [PSCustomObject]@{
        Profile = $NormalizedProfile
        Instance = $Instance
        BuildRoot = $BuildRoot
        BuildDir = $BuildDir
        Sdkconfig = Join-Path $BuildDir "sdkconfig"
        ProjectDescription = Join-Path $BuildDir "project_description.json"
        FlasherArgs = Join-Path $BuildDir "flasher_args.json"
    }
}

function Invoke-B33Idf {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [psobject]$Environment,

        [Parameter(Mandatory)]
        [string[]]$Arguments,

        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$Operation,

        [string]$Timestamp = (Get-B33Timestamp)
    )

    $EvidenceDir = Get-B33EvidenceDirectory -RepoRoot $Environment.RepoRoot
    $SafeOperation = $Operation -replace '[^A-Za-z0-9_.-]', '_'

    $StdoutPath = Join-Path `
        $EvidenceDir `
        "B3.3_${SafeOperation}_stdout_${Timestamp}.txt"

    $StderrPath = Join-Path `
        $EvidenceDir `
        "B3.3_${SafeOperation}_stderr_${Timestamp}.txt"

    $ProcessArguments = @($Environment.IdfPy) + @($Arguments)

    Invoke-B32CapturedProcess `
        -FilePath $Environment.PythonExe `
        -ArgumentList $ProcessArguments `
        -WorkingDirectory $Environment.RepoRoot `
        -StdoutPath $StdoutPath `
        -StderrPath $StderrPath `
        -Operation $Operation
}

function Assert-B33ReproducibleConfiguration {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SdkconfigPath,

        [ValidateSet("debug", "validation", "production")]
        [string]$Profile = "production"
    )

    Assert-B32GeneratedConfiguration `
        -SdkconfigPath $SdkconfigPath `
        -Profile $Profile |
        Out-Null

    $Lines = @(
        Get-Content `
            -LiteralPath $SdkconfigPath `
            -ErrorAction Stop
    )

    if ($Lines -notcontains "CONFIG_APP_REPRODUCIBLE_BUILD=y") {
        throw "Generated sdkconfig does not enable CONFIG_APP_REPRODUCIBLE_BUILD."
    }

    $ForbiddenEnabled = @(
        "CONFIG_APP_COMPILE_TIME_DATE=y"
        "CONFIG_BOOTLOADER_COMPILE_TIME_DATE=y"
    )

    $EnabledDateOptions = @(
        $ForbiddenEnabled |
        Where-Object { $Lines -contains $_ }
    )

    if ($EnabledDateOptions.Count -gt 0) {
        throw "Generated sdkconfig enables forbidden compile-time date controls:`n$($EnabledDateOptions -join [Environment]::NewLine)"
    }

    $true
}
