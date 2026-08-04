[CmdletBinding()]
param(
    [string]$RepoRoot = "",

    [string]$IdfPath = "D:\esp\v6.0.2\esp-idf",

    [string]$PythonPath = (
        "C:\Users\parth\.espressif\python_env\" +
        "idf6.0_py3.11_env\Scripts\python.exe"
    )
)

Clear-Host -ErrorAction SilentlyContinue

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-C22Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$FailureMessage,

        [string]$RequiredMarker = ""
    )

    $PreviousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    $Output = @(
        & $FilePath @Arguments 2>&1
    )

    $ExitCode = $LASTEXITCODE
    $ErrorActionPreference = $PreviousErrorAction

    $Output |
        ForEach-Object {
            Write-Host $_
        }

    if ($ExitCode -ne 0) {
        throw $FailureMessage
    }

    if (
        -not [string]::IsNullOrWhiteSpace($RequiredMarker) -and
        -not (($Output -join "`n").Contains($RequiredMarker))
    ) {
        throw "Required output marker is missing: $RequiredMarker"
    }
}

function Write-C22Utf8Lf {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [AllowEmptyString()]
        [string[]]$Lines
    )

    $Text = ($Lines -join "`n") + "`n"
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    [System.IO.File]::WriteAllText(
        $Path,
        $Text,
        $Utf8NoBom
    )
}

function Get-C22NormalizedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return $Path.Replace([char]92, [char]47).ToLowerInvariant()
}

function Invoke-C22BoardVerification {
    if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
        $RepoRoot = (
            Resolve-Path (
                Join-Path $PSScriptRoot "..\.."
            )
        ).Path
    }
    else {
        $RepoRoot = (Resolve-Path $RepoRoot).Path
    }

    $VerifierPath = Join-Path $RepoRoot "tools\ci\verify_c2_2.py"
    $HostRunner = Join-Path $RepoRoot "tools\ci\run_host_tests.py"
    $DefaultsPath = Join-Path $RepoRoot "sdkconfig.defaults"
    $IdfExport = Join-Path $IdfPath "export.ps1"
    $IdfPy = Join-Path $IdfPath "tools\idf.py"

    $RequiredPaths = @(
        $PythonPath
        $VerifierPath
        $HostRunner
        $DefaultsPath
        $IdfExport
        $IdfPy
    )

    foreach ($Path in $RequiredPaths) {
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
            throw "Required verification file is missing: $Path"
        }
    }

    $GitRoot = (
        git -C $RepoRoot rev-parse --show-toplevel
    ).Trim()

    if (
        (Get-C22NormalizedPath $GitRoot) -ne
        (Get-C22NormalizedPath $RepoRoot)
    ) {
        throw "Selected repository root does not match Git root."
    }

    Write-Host ""
    Write-Host "=== C2.2 board-support verification ==="
    Write-Host ("Repository:          {0}" -f $RepoRoot)
    Write-Host ("ESP-IDF:             {0}" -f $IdfPath)
    Write-Host ("Python:              {0}" -f $PythonPath)

    Write-Host ""
    Write-Host "=== Validate repository whitespace ==="

    Invoke-C22Native `
        -FilePath "git" `
        -Arguments @(
            "-C"
            $RepoRoot
            "diff"
            "--check"
        ) `
        -FailureMessage "Repository whitespace validation failed."

    Write-Host "Repository whitespace: PASS"

    Write-Host ""
    Write-Host "=== Execute static C2.2 verifier ==="

    Invoke-C22Native `
        -FilePath $PythonPath `
        -Arguments @(
            $VerifierPath
            "--repo-root"
            $RepoRoot
        ) `
        -FailureMessage "Static C2.2 verifier failed." `
        -RequiredMarker (
            "PASS: C2.2 board support contract validated."
        )

    Write-Host "Static C2.2 verifier: PASS"

    Write-Host ""
    Write-Host "=== Execute complete host-test suite ==="

    Invoke-C22Native `
        -FilePath $PythonPath `
        -Arguments @($HostRunner) `
        -FailureMessage "Complete host-test suite failed." `
        -RequiredMarker "PASS: B4.1 host tests passed."

    Write-Host "Complete host-test suite: PASS"

    Write-Host ""
    Write-Host "=== Perform isolated ESP-IDF build ==="

    $TemporaryRoot = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) (
        "SQD_C2_2_" + [guid]::NewGuid().ToString("N")
    )

    $BuildDirectory = Join-Path $TemporaryRoot "build"
    $SdkconfigPath = Join-Path $TemporaryRoot "sdkconfig"
    $ChildScriptPath = Join-Path $TemporaryRoot "build.ps1"
    $BuildValidated = $false

    $EnvironmentNames = @(
        "C22_IDF_EXPORT"
        "C22_PYTHON"
        "C22_IDF_PY"
        "C22_REPO_ROOT"
        "C22_BUILD_DIR"
        "C22_SDKCONFIG"
        "C22_DEFAULTS"
    )

    $EnvironmentBackup = @{}

    foreach ($Name in $EnvironmentNames) {
        $EnvironmentBackup[$Name] = (
            [Environment]::GetEnvironmentVariable(
                $Name,
                "Process"
            )
        )
    }

    try {
        [void](
            New-Item `
                -ItemType Directory `
                -Path $TemporaryRoot `
                -Force
        )

        $env:C22_IDF_EXPORT = $IdfExport
        $env:C22_PYTHON = $PythonPath
        $env:C22_IDF_PY = $IdfPy
        $env:C22_REPO_ROOT = $RepoRoot
        $env:C22_BUILD_DIR = $BuildDirectory
        $env:C22_SDKCONFIG = $SdkconfigPath
        $env:C22_DEFAULTS = $DefaultsPath

        $ChildLines = @(
            '$ErrorActionPreference = "Stop"'
            'Set-StrictMode -Version Latest'
            '. $env:C22_IDF_EXPORT'
            '$env:SDKCONFIG = $env:C22_SDKCONFIG'
            '$env:SDKCONFIG_DEFAULTS = $env:C22_DEFAULTS'
            '$SdkconfigArgument = "SDKCONFIG=$($env:C22_SDKCONFIG)"'
            '$DefaultsArgument = "SDKCONFIG_DEFAULTS=$($env:C22_DEFAULTS)"'
            '& $env:C22_PYTHON $env:C22_IDF_PY `'
            '    -C $env:C22_REPO_ROOT `'
            '    -B $env:C22_BUILD_DIR `'
            '    -D $SdkconfigArgument `'
            '    -D $DefaultsArgument `'
            '    -D "CMAKE_EXPORT_COMPILE_COMMANDS=ON" `'
            '    build'
            'exit $LASTEXITCODE'
        )

        Write-C22Utf8Lf `
            -Path $ChildScriptPath `
            -Lines $ChildLines

        $PowerShellPath = (
            Get-Process -Id $PID
        ).Path

        Invoke-C22Native `
            -FilePath $PowerShellPath `
            -Arguments @(
                "-NoProfile"
                "-ExecutionPolicy"
                "Bypass"
                "-File"
                $ChildScriptPath
            ) `
            -FailureMessage "Isolated ESP-IDF build failed."

        $CompileCommandsPath = Join-Path (
            $BuildDirectory
        ) "compile_commands.json"

        $BoardLibraryPath = Join-Path (
            $BuildDirectory
        ) "esp-idf\board\libboard.a"

        foreach ($BuildArtifact in @(
            $CompileCommandsPath
            $BoardLibraryPath
            $SdkconfigPath
        )) {
            if (
                -not (
                    Test-Path `
                        -LiteralPath $BuildArtifact `
                        -PathType Leaf
                )
            ) {
                throw "Required build artifact is missing: $BuildArtifact"
            }
        }

        try {
                        $ParsedCompileCommands =
                Get-Content `
                    -LiteralPath $CompileCommandsPath `
                    -Raw |
                    ConvertFrom-Json

            $CompileCommands = @(
                $ParsedCompileCommands |
                    ForEach-Object {
                        $_
                    }
            )
        }
        catch {
            throw "compile_commands.json is invalid."
        }

        $CompiledPaths = @()

        foreach ($Entry in $CompileCommands) {
            $FileValue = [string]$Entry.file

            if ([System.IO.Path]::IsPathRooted($FileValue)) {
                $ResolvedFile = $FileValue
            }
            else {
                $ResolvedFile = Join-Path (
                    [string]$Entry.directory
                ) $FileValue
            }

            $CompiledPaths += (
                Get-C22NormalizedPath $ResolvedFile
            )
        }

        $ExpectedBoardSources = @(
            Join-Path $RepoRoot "components\board\sqd_board.c"
            Join-Path $RepoRoot "components\board\sqd_board_mapping.c"
        )

        foreach ($SourcePath in $ExpectedBoardSources) {
            $NormalizedSource = (
                Get-C22NormalizedPath $SourcePath
            )

            if ($NormalizedSource -notin $CompiledPaths) {
                throw "Board source was not compiled: $SourcePath"
            }

            Write-Host ("COMPILED: {0}" -f $SourcePath)
        }

        $GeneratedConfiguration = (
            Get-Content -LiteralPath $SdkconfigPath
        )

        $SelectionCount = @(
            $GeneratedConfiguration |
                Where-Object {
                    $_ -eq (
                        "CONFIG_SQD_BOARD_" +
                        "HELTEC_WIFI_LORA_32_V3_2=y"
                    )
                }
        ).Count

        if ($SelectionCount -ne 1) {
            throw "Generated sdkconfig lacks the exact V3.2 selection."
        }

        Write-Host ("Board library:       {0}" -f $BoardLibraryPath)
        Write-Host ("Generated sdkconfig: {0}" -f $SdkconfigPath)
        Write-Host "ESP-IDF board-component build: PASS"

        $BuildValidated = $true
    }
    finally {
        foreach ($Name in $EnvironmentNames) {
            $PreviousValue = $EnvironmentBackup[$Name]

            if ($null -eq $PreviousValue) {
                Remove-Item `
                    -LiteralPath ("Env:\" + $Name) `
                    -ErrorAction SilentlyContinue
            }
            else {
                [Environment]::SetEnvironmentVariable(
                    $Name,
                    [string]$PreviousValue,
                    "Process"
                )
            }
        }

        if (
            $BuildValidated -and
            (Test-Path -LiteralPath $TemporaryRoot)
        ) {
            Remove-Item `
                -LiteralPath $TemporaryRoot `
                -Recurse `
                -Force
        }
        elseif (Test-Path -LiteralPath $TemporaryRoot) {
            Write-Host (
                "Build workspace retained for diagnosis: {0}" -f
                $TemporaryRoot
            )
        }
    }

    Write-Host ""
    Write-Host "PASS: static C2.2 verification passed."
    Write-Host "PASS: all controlled host tests passed."
    Write-Host "PASS: the ESP-IDF build compiled both board sources."
    Write-Host "PASS: the generated sdkconfig selected exact V3.2 support."
    Write-Host ""
    Write-Host "C2.2 board support verification PASSED."
}

try {
    Invoke-C22BoardVerification
    exit 0
}
catch {
    [Console]::Error.WriteLine(
        "ERROR: " + $_.Exception.Message
    )
    exit 1
}
