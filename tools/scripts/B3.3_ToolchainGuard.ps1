[CmdletBinding()]
param(
    [string]$RepoRoot = "D:\OneDrive\SQD",

    [string]$IdfPath = "D:\esp\v6.0.2\esp-idf"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$CommonLibrary = Join-Path $PSScriptRoot "B3.3_Common.ps1"

if (-not (Test-Path -LiteralPath $CommonLibrary -PathType Leaf)) {
    throw "B3.3 common library is missing: $CommonLibrary"
}

. $CommonLibrary

function Get-B33FirstOutputLine {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,

        [string[]]$Arguments = @()
    )

    $Output = @(& $FilePath @Arguments 2>&1)
    $ExitCode = $LASTEXITCODE

    if ($ExitCode -ne 0) {
        throw "$FilePath $($Arguments -join ' ') failed with exit code $ExitCode."
    }

    $Line = @(
        $Output |
        ForEach-Object { [string]$_ } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    ) | Select-Object -First 1

    if ([string]::IsNullOrWhiteSpace($Line)) {
        throw "No version output was returned by $FilePath."
    }

    $Line.Trim()
}

function Assert-B33ExactText {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [AllowEmptyString()]
        [string]$Actual,

        [AllowEmptyString()]
        [string]$Expected
    )

    if ($Actual -ne $Expected) {
        throw "$Name mismatch. Expected '$Expected'; detected '$Actual'."
    }
}

function Assert-B33ExactPath {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$Actual,

        [Parameter(Mandatory)]
        [string]$Expected
    )

    $ActualFull = [System.IO.Path]::GetFullPath($Actual)
    $ExpectedFull = [System.IO.Path]::GetFullPath($Expected)

    if (-not [string]::Equals(
        $ActualFull,
        $ExpectedFull,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "$Name path mismatch. Expected '$ExpectedFull'; detected '$ActualFull'."
    }
}

function Assert-B33ToolchainSnapshot {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [psobject]$Snapshot,

        [Parameter(Mandatory)]
        [psobject]$Baseline
    )

    Assert-B33ExactText `
        -Name "Target" `
        -Actual ([string]$Snapshot.target) `
        -Expected ([string]$Baseline.target)

    Assert-B33ExactPath `
        -Name "ESP-IDF" `
        -Actual ([string]$Snapshot.idf.path) `
        -Expected ([string]$Baseline.idf.path)

    Assert-B33ExactText `
        -Name "ESP-IDF version" `
        -Actual ([string]$Snapshot.idf.version) `
        -Expected ([string]$Baseline.idf.version)

    Assert-B33ExactPath `
        -Name "Python" `
        -Actual ([string]$Snapshot.python.path) `
        -Expected ([string]$Baseline.python.path)

    Assert-B33ExactText `
        -Name "Python version" `
        -Actual ([string]$Snapshot.python.version) `
        -Expected ([string]$Baseline.python.version)

    Assert-B33ExactPath `
        -Name "CMake" `
        -Actual ([string]$Snapshot.cmake.path) `
        -Expected ([string]$Baseline.cmake.path)

    Assert-B33ExactText `
        -Name "CMake version" `
        -Actual ([string]$Snapshot.cmake.version) `
        -Expected ([string]$Baseline.cmake.version)

    Assert-B33ExactPath `
        -Name "Ninja" `
        -Actual ([string]$Snapshot.ninja.path) `
        -Expected ([string]$Baseline.ninja.path)

    Assert-B33ExactText `
        -Name "Ninja version" `
        -Actual ([string]$Snapshot.ninja.version) `
        -Expected ([string]$Baseline.ninja.version)

    Assert-B33ExactPath `
        -Name "Compiler" `
        -Actual ([string]$Snapshot.compiler.path) `
        -Expected ([string]$Baseline.compiler.path)

    $CompilerPattern = [string]$Baseline.compiler.version_pattern
    $CompilerVersion = [string]$Snapshot.compiler.version

    if (-not $CompilerVersion.Contains($CompilerPattern)) {
        throw "Compiler version mismatch. Required marker '$CompilerPattern'; detected '$CompilerVersion'."
    }

    Assert-B33ExactPath `
        -Name "Git" `
        -Actual ([string]$Snapshot.git.path) `
        -Expected ([string]$Baseline.git.path)

    Assert-B33ExactText `
        -Name "Git version" `
        -Actual ([string]$Snapshot.git.version) `
        -Expected ([string]$Baseline.git.version)

    $true
}

function Copy-B33Object {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$InputObject
    )

    $InputObject |
        ConvertTo-Json -Depth 20 |
        ConvertFrom-Json
}

function Test-B33ExpectedRejection {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [scriptblock]$Action
    )

    try {
        & $Action | Out-Null

        [PSCustomObject]@{
            Test = $Name
            Expected = "REJECT"
            Actual = "ACCEPT"
            Pass = $false
            Diagnostic = "Mutation was incorrectly accepted."
        }
    }
    catch {
        [PSCustomObject]@{
            Test = $Name
            Expected = "REJECT"
            Actual = "REJECT"
            Pass = $true
            Diagnostic = $_.Exception.Message
        }
    }
}

$Timestamp = Get-B33Timestamp
$EvidenceDir = Get-B33EvidenceDirectory -RepoRoot $RepoRoot

$BaselinePath = Join-Path `
    $RepoRoot `
    "tools\config\B3.3_toolchain_baseline.json"

$SummaryPath = Join-Path `
    $EvidenceDir `
    "B3.3_toolchain_guard_summary_${Timestamp}.txt"

$ResultPath = Join-Path `
    $EvidenceDir `
    "B3.3_toolchain_guard_result_${Timestamp}.json"

$ComparisonPath = Join-Path `
    $EvidenceDir `
    "B3.3_toolchain_rejection_tests_${Timestamp}.csv"

try {
    Write-B32Section -Title "B3.3 TOOLCHAIN GUARD"

    $Branch = Assert-B33FeatureBranch -RepoRoot $RepoRoot

    $ResolvedBaselinePath = Assert-B32File `
        -Path $BaselinePath `
        -Description "B3.3 toolchain baseline"

    $Baseline = Get-Content `
        -LiteralPath $ResolvedBaselinePath `
        -Raw |
        ConvertFrom-Json

    if ([int]$Baseline.schema_version -ne 1) {
        throw "Unsupported toolchain baseline schema version '$($Baseline.schema_version)'."
    }

    $Environment = Initialize-B33Environment `
        -RepoRoot $RepoRoot `
        -IdfPath $IdfPath

    $PythonCommand = Get-Command python.exe -ErrorAction Stop
    $CMakeCommand = Get-Command cmake.exe -ErrorAction Stop
    $NinjaCommand = Get-Command ninja.exe -ErrorAction Stop
    $CompilerCommand = Get-Command `
        ([string]$Baseline.compiler.command) `
        -ErrorAction Stop
    $GitCommand = Get-Command git.exe -ErrorAction Stop

    $Snapshot = [ordered]@{
        target = $Environment.Target
        idf = [ordered]@{
            path = $Environment.IdfPath
            version = $Environment.IdfVersion
        }
        python = [ordered]@{
            path = $PythonCommand.Source
            version = Get-B33FirstOutputLine `
                -FilePath $PythonCommand.Source `
                -Arguments @("--version")
        }
        cmake = [ordered]@{
            path = $CMakeCommand.Source
            version = Get-B33FirstOutputLine `
                -FilePath $CMakeCommand.Source `
                -Arguments @("--version")
        }
        ninja = [ordered]@{
            path = $NinjaCommand.Source
            version = Get-B33FirstOutputLine `
                -FilePath $NinjaCommand.Source `
                -Arguments @("--version")
        }
        compiler = [ordered]@{
            path = $CompilerCommand.Source
            version = Get-B33FirstOutputLine `
                -FilePath $CompilerCommand.Source `
                -Arguments @("--version")
        }
        git = [ordered]@{
            path = $GitCommand.Source
            version = Get-B33FirstOutputLine `
                -FilePath $GitCommand.Source `
                -Arguments @("--version")
        }
    }

    Assert-B33ToolchainSnapshot `
        -Snapshot ([pscustomobject]$Snapshot) `
        -Baseline $Baseline |
        Out-Null

    $RejectionTests = @()

    $Mutation = Copy-B33Object -InputObject $Snapshot
    $Mutation.target = "esp32"
    $RejectionTests += Test-B33ExpectedRejection `
        -Name "reject-wrong-target" `
        -Action {
            Assert-B33ToolchainSnapshot `
                -Snapshot $Mutation `
                -Baseline $Baseline
        }

    $Mutation = Copy-B33Object -InputObject $Snapshot
    $Mutation.idf.version = "ESP-IDF v0.0.0"
    $RejectionTests += Test-B33ExpectedRejection `
        -Name "reject-wrong-idf-version" `
        -Action {
            Assert-B33ToolchainSnapshot `
                -Snapshot $Mutation `
                -Baseline $Baseline
        }

    $Mutation = Copy-B33Object -InputObject $Snapshot
    $Mutation.idf.path = "C:\unapproved\esp-idf"
    $RejectionTests += Test-B33ExpectedRejection `
        -Name "reject-wrong-idf-path" `
        -Action {
            Assert-B33ToolchainSnapshot `
                -Snapshot $Mutation `
                -Baseline $Baseline
        }

    $Mutation = Copy-B33Object -InputObject $Snapshot
    $Mutation.python.version = "Python 3.13.0"
    $RejectionTests += Test-B33ExpectedRejection `
        -Name "reject-wrong-python-version" `
        -Action {
            Assert-B33ToolchainSnapshot `
                -Snapshot $Mutation `
                -Baseline $Baseline
        }

    $Mutation = Copy-B33Object -InputObject $Snapshot
    $Mutation.cmake.version = "cmake version 3.0.0"
    $RejectionTests += Test-B33ExpectedRejection `
        -Name "reject-wrong-cmake-version" `
        -Action {
            Assert-B33ToolchainSnapshot `
                -Snapshot $Mutation `
                -Baseline $Baseline
        }

    $Mutation = Copy-B33Object -InputObject $Snapshot
    $Mutation.ninja.version = "0.0.0"
    $RejectionTests += Test-B33ExpectedRejection `
        -Name "reject-wrong-ninja-version" `
        -Action {
            Assert-B33ToolchainSnapshot `
                -Snapshot $Mutation `
                -Baseline $Baseline
        }

    $Mutation = Copy-B33Object -InputObject $Snapshot
    $Mutation.compiler.version = "unapproved compiler"
    $RejectionTests += Test-B33ExpectedRejection `
        -Name "reject-wrong-compiler-version" `
        -Action {
            Assert-B33ToolchainSnapshot `
                -Snapshot $Mutation `
                -Baseline $Baseline
        }

    $Mutation = Copy-B33Object -InputObject $Snapshot
    $Mutation.git.version = "git version 0.0.0"
    $RejectionTests += Test-B33ExpectedRejection `
        -Name "reject-wrong-git-version" `
        -Action {
            Assert-B33ToolchainSnapshot `
                -Snapshot $Mutation `
                -Baseline $Baseline
        }

    $RejectionTests |
        Export-Csv `
            -LiteralPath $ComparisonPath `
            -NoTypeInformation `
            -Encoding UTF8

    $RejectionFailures = @(
        $RejectionTests |
        Where-Object { -not $_.Pass }
    )

    $Status = if ($RejectionFailures.Count -eq 0) {
        "PASS"
    }
    else {
        "FAIL"
    }

    $RepositoryState = Get-B32RepositoryState `
        -RepoRoot $Environment.RepoRoot

    $Result = [ordered]@{
        work_package = "B3.3"
        operation = "toolchain-guard"
        status = $Status
        timestamp_local = (Get-Date).ToString("o")
        repository = [ordered]@{
            root = $Environment.RepoRoot
            branch = $RepositoryState.Branch
            commit = $RepositoryState.Commit
            commit_short = $RepositoryState.CommitShort
        }
        baseline = [ordered]@{
            path = $ResolvedBaselinePath
            schema_version = [int]$Baseline.schema_version
        }
        approved_toolchain = $Snapshot
        rejection_tests = [ordered]@{
            count = $RejectionTests.Count
            pass_count = @(
                $RejectionTests |
                Where-Object Pass
            ).Count
            fail_count = $RejectionFailures.Count
            csv = $ComparisonPath
        }
    }

    Write-B32JsonFile `
        -InputObject $Result `
        -Path $ResultPath `
        -Depth 20 |
        Out-Null

    $Summary = @(
        "============================================================"
        "B3.3 TOOLCHAIN GUARD"
        "============================================================"
        "Status:                    $Status"
        "Timestamp:                 $((Get-Date).ToString('o'))"
        "Branch:                    $Branch"
        "Commit:                    $($RepositoryState.Commit)"
        "Target:                    $($Snapshot.target)"
        "ESP-IDF:                   $($Snapshot.idf.version)"
        "ESP-IDF path:              $($Snapshot.idf.path)"
        "Python:                    $($Snapshot.python.version)"
        "CMake:                     $($Snapshot.cmake.version)"
        "Ninja:                     $($Snapshot.ninja.version)"
        "Compiler:                  $($Snapshot.compiler.version)"
        "Git:                       $($Snapshot.git.version)"
        "Rejection tests:           $($RejectionTests.Count)"
        "Rejected correctly:        $(@($RejectionTests | Where-Object Pass).Count)"
        "Rejection failures:        $($RejectionFailures.Count)"
        "Rejection CSV:             $ComparisonPath"
        "Result JSON:               $ResultPath"
        ""
        "B3.3 TOOLCHAIN GUARD $Status"
    ) -join [Environment]::NewLine

    Write-B32TextFile `
        -Content ($Summary + [Environment]::NewLine) `
        -Path $SummaryPath |
        Out-Null

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "B3.3 TOOLCHAIN GUARD $Status"
    Write-Host "============================================================"
    Write-Host "Approved toolchain: PASS"
    Write-Host "Rejection tests:    $($RejectionTests.Count)"
    Write-Host "Rejection failures: $($RejectionFailures.Count)"
    Write-Host "Summary:            $SummaryPath"
    Write-Host "Result JSON:        $ResultPath"
    Write-Host "Rejection CSV:      $ComparisonPath"

    if ($Status -ne "PASS") {
        throw "Toolchain rejection verification failed."
    }
}
catch {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "B3.3 TOOLCHAIN GUARD FAILED"
    Write-Host "============================================================"
    Write-Host $_.Exception.Message -ForegroundColor Red
    throw
}
