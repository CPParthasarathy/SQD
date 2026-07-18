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

function New-B33VerificationRecord {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Category,

        [Parameter(Mandatory)]
        [string]$Check,

        [Parameter(Mandatory)]
        [ValidateSet("PASS", "FAIL")]
        [string]$Status,

        [string]$Diagnostic = "",

        [string]$Stdout = "",

        [string]$Stderr = ""
    )

    [PSCustomObject]@{
        Category = $Category
        Check = $Check
        Status = $Status
        Diagnostic = $Diagnostic
        Stdout = $Stdout
        Stderr = $Stderr
    }
}

$Timestamp = Get-B33Timestamp
$EvidenceDir = Get-B33EvidenceDirectory -RepoRoot $RepoRoot

$SummaryPath = Join-Path `
    $EvidenceDir `
    "B3.3_verification_summary_${Timestamp}.txt"

$ResultPath = Join-Path `
    $EvidenceDir `
    "B3.3_verification_result_${Timestamp}.json"

$CsvPath = Join-Path `
    $EvidenceDir `
    "B3.3_verification_results_${Timestamp}.csv"

try {
    Write-B32Section -Title "B3.3 CONSOLIDATED VERIFICATION"

    $Branch = Assert-B33FeatureBranch -RepoRoot $RepoRoot
    $RepositoryState = Get-B32RepositoryState -RepoRoot $RepoRoot
    $Checks = @()

    $RequiredScripts = @(
        "B3.3_Common.ps1"
        "B3.3_ConfigDrift.ps1"
        "B3.3_Reproducibility.ps1"
        "B3.3_SizeBudget.ps1"
        "B3.3_ToolchainGuard.ps1"
        "B3.3_Verify.ps1"
    )

    foreach ($ScriptName in $RequiredScripts) {
        $Path = Join-Path $PSScriptRoot $ScriptName

        try {
            $ResolvedPath = Assert-B32File `
                -Path $Path `
                -Description $ScriptName

            $Tokens = $null
            $Errors = $null

            [System.Management.Automation.Language.Parser]::ParseFile(
                $ResolvedPath,
                [ref]$Tokens,
                [ref]$Errors
            ) | Out-Null

            if ($Errors.Count -gt 0) {
                throw (
                    $Errors |
                    ForEach-Object Message
                ) -join "; "
            }

            $Checks += New-B33VerificationRecord `
                -Category "script-syntax" `
                -Check $ScriptName `
                -Status "PASS" `
                -Diagnostic "PowerShell syntax valid."
        }
        catch {
            $Checks += New-B33VerificationRecord `
                -Category "script-syntax" `
                -Check $ScriptName `
                -Status "FAIL" `
                -Diagnostic $_.Exception.Message
        }
    }

    $RequiredBaselines = @(
        "B3.3_configuration_baseline.json"
        "B3.3_size_budget.json"
        "B3.3_toolchain_baseline.json"
    )

    foreach ($BaselineName in $RequiredBaselines) {
        $Path = Join-Path `
            $RepoRoot `
            "tools\config\$BaselineName"

        try {
            $ResolvedPath = Assert-B32File `
                -Path $Path `
                -Description $BaselineName

            $Parsed = Get-Content `
                -LiteralPath $ResolvedPath `
                -Raw |
                ConvertFrom-Json

            if ([int]$Parsed.schema_version -ne 1) {
                throw "Unsupported schema version '$($Parsed.schema_version)'."
            }

            if ([string]$Parsed.work_package -ne "B3.3") {
                throw "Unexpected work package '$($Parsed.work_package)'."
            }

            $Checks += New-B33VerificationRecord `
                -Category "baseline-json" `
                -Check $BaselineName `
                -Status "PASS" `
                -Diagnostic "JSON parsed; schema version 1."
        }
        catch {
            $Checks += New-B33VerificationRecord `
                -Category "baseline-json" `
                -Check $BaselineName `
                -Status "FAIL" `
                -Diagnostic $_.Exception.Message
        }
    }

    $ControlScripts = @(
        [PSCustomObject]@{
            Check = "reproducible-build"
            Script = "B3.3_Reproducibility.ps1"
        }
        [PSCustomObject]@{
            Check = "configuration-drift"
            Script = "B3.3_ConfigDrift.ps1"
        }
        [PSCustomObject]@{
            Check = "toolchain-rejection"
            Script = "B3.3_ToolchainGuard.ps1"
        }
        [PSCustomObject]@{
            Check = "firmware-image-size-budget"
            Script = "B3.3_SizeBudget.ps1"
        }
    )

    $PowerShellExe = (
        Get-Command powershell.exe -ErrorAction Stop
    ).Source

    foreach ($Control in $ControlScripts) {
        $ControlScript = Assert-B32File `
            -Path (Join-Path $PSScriptRoot $Control.Script) `
            -Description $Control.Script

        $SafeCheck = $Control.Check -replace '[^A-Za-z0-9_.-]', '_'

        $StdoutPath = Join-Path `
            $EvidenceDir `
            "B3.3_verify_${SafeCheck}_stdout_${Timestamp}.txt"

        $StderrPath = Join-Path `
            $EvidenceDir `
            "B3.3_verify_${SafeCheck}_stderr_${Timestamp}.txt"

        $Arguments = @(
            "-NoProfile"
            "-ExecutionPolicy"
            "Bypass"
            "-File"
            $ControlScript
            "-RepoRoot"
            $RepoRoot
            "-IdfPath"
            $IdfPath
        )

        try {
            $Execution = Invoke-B32CapturedProcess `
                -FilePath $PowerShellExe `
                -ArgumentList $Arguments `
                -WorkingDirectory $RepoRoot `
                -StdoutPath $StdoutPath `
                -StderrPath $StderrPath `
                -Operation "B3.3 $($Control.Check)"

            $Checks += New-B33VerificationRecord `
                -Category "control-execution" `
                -Check $Control.Check `
                -Status "PASS" `
                -Diagnostic "Completed in $($Execution.DurationSeconds) seconds." `
                -Stdout $StdoutPath `
                -Stderr $StderrPath
        }
        catch {
            $Checks += New-B33VerificationRecord `
                -Category "control-execution" `
                -Check $Control.Check `
                -Status "FAIL" `
                -Diagnostic $_.Exception.Message `
                -Stdout $StdoutPath `
                -Stderr $StderrPath
        }
    }

    $Checks |
        Export-Csv `
            -LiteralPath $CsvPath `
            -NoTypeInformation `
            -Encoding UTF8

    $PassCount = @(
        $Checks |
        Where-Object Status -eq "PASS"
    ).Count

    $FailCount = @(
        $Checks |
        Where-Object Status -eq "FAIL"
    ).Count

    $Status = if ($FailCount -eq 0) {
        "PASS"
    }
    else {
        "FAIL"
    }

    $Result = [ordered]@{
        work_package = "B3.3"
        operation = "consolidated-verification"
        status = $Status
        timestamp_local = (Get-Date).ToString("o")
        repository = [ordered]@{
            root = $RepoRoot
            branch = $Branch
            commit = $RepositoryState.Commit
            commit_short = $RepositoryState.CommitShort
            tracked_status = $RepositoryState.TrackedStatusPorcelain
        }
        verification = [ordered]@{
            total_checks = $Checks.Count
            pass_count = $PassCount
            fail_count = $FailCount
            result_csv = $CsvPath
        }
        checks = @($Checks)
    }

    Write-B32JsonFile `
        -InputObject $Result `
        -Path $ResultPath `
        -Depth 20 |
        Out-Null

    $FailureDetails = @(
        $Checks |
        Where-Object Status -eq "FAIL" |
        ForEach-Object {
            "FAIL: [$($_.Category)] $($_.Check) - $($_.Diagnostic)"
        }
    )

    $SummaryLines = @(
        "============================================================"
        "B3.3 CONSOLIDATED VERIFICATION"
        "============================================================"
        "Status:                    $Status"
        "Timestamp:                 $((Get-Date).ToString('o'))"
        "Branch:                    $Branch"
        "Commit:                    $($RepositoryState.Commit)"
        "Total checks:              $($Checks.Count)"
        "PASS:                      $PassCount"
        "FAIL:                      $FailCount"
        "Results CSV:               $CsvPath"
        "Result JSON:               $ResultPath"
    )

    if ($FailureDetails.Count -gt 0) {
        $SummaryLines += ""
        $SummaryLines += "FAILURE DETAILS"
        $SummaryLines += $FailureDetails
    }

    $SummaryLines += ""
    $SummaryLines += "B3.3 CONSOLIDATED VERIFICATION $Status"

    Write-B32TextFile `
        -Content (
            ($SummaryLines -join [Environment]::NewLine) +
            [Environment]::NewLine
        ) `
        -Path $SummaryPath |
        Out-Null

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "B3.3 CONSOLIDATED VERIFICATION $Status"
    Write-Host "============================================================"
    Write-Host "PASS:        $PassCount"
    Write-Host "FAIL:        $FailCount"
    Write-Host "Summary:     $SummaryPath"
    Write-Host "Results CSV: $CsvPath"
    Write-Host "Result JSON: $ResultPath"

    if ($Status -ne "PASS") {
        throw "B3.3 consolidated verification failed."
    }
}
catch {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "B3.3 CONSOLIDATED VERIFICATION FAILED"
    Write-Host "============================================================"
    Write-Host $_.Exception.Message -ForegroundColor Red
    throw
}
