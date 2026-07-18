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

function Get-B33CanonicalFileHash {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    $ResolvedPath = Assert-B32File `
        -Path $Path `
        -Description "Controlled configuration"

    $Text = [System.IO.File]::ReadAllText($ResolvedPath)

    $CanonicalText = (
        $Text.Replace("`r`n", "`n").Replace("`r", "`n")
    ).TrimEnd("`n") + "`n"

    $Bytes = [System.Text.Encoding]::UTF8.GetBytes($CanonicalText)
    $Hasher = [System.Security.Cryptography.SHA256]::Create()

    try {
        $HashBytes = $Hasher.ComputeHash($Bytes)

        (
            [System.BitConverter]::ToString($HashBytes)
        ).Replace("-", "")
    }
    finally {
        $Hasher.Dispose()
    }
}

$Timestamp = Get-B33Timestamp
$EvidenceDir = Get-B33EvidenceDirectory -RepoRoot $RepoRoot

$BaselinePath = Join-Path `
    $RepoRoot `
    "tools\config\B3.3_configuration_baseline.json"

$SummaryPath = Join-Path `
    $EvidenceDir `
    "B3.3_configuration_drift_summary_${Timestamp}.txt"

$ResultPath = Join-Path `
    $EvidenceDir `
    "B3.3_configuration_drift_result_${Timestamp}.json"

$ComparisonPath = Join-Path `
    $EvidenceDir `
    "B3.3_configuration_drift_comparison_${Timestamp}.csv"

try {
    Write-B32Section -Title "B3.3 CONFIGURATION DRIFT CHECK"

    $Branch = Assert-B33FeatureBranch -RepoRoot $RepoRoot

    $ResolvedBaselinePath = Assert-B32File `
        -Path $BaselinePath `
        -Description "B3.3 configuration baseline"

    $Baseline = Get-Content `
        -LiteralPath $ResolvedBaselinePath `
        -Raw |
        ConvertFrom-Json

    if ([int]$Baseline.schema_version -ne 1) {
        throw "Unsupported configuration baseline schema version '$($Baseline.schema_version)'."
    }

    $Environment = Initialize-B33Environment `
        -RepoRoot $RepoRoot `
        -IdfPath $IdfPath

    $RepositoryState = Get-B32RepositoryState `
        -RepoRoot $Environment.RepoRoot

    $FileComparisons = @(
        foreach ($Record in @($Baseline.controlled_files)) {
            $RelativePath = [string]$Record.relative_path
            $ExpectedHash = [string]$Record.canonical_sha256
            $FullPath = Join-Path $Environment.RepoRoot $RelativePath

            $Exists = Test-Path `
                -LiteralPath $FullPath `
                -PathType Leaf

            $ActualHash = if ($Exists) {
                Get-B33CanonicalFileHash -Path $FullPath
            }
            else {
                $null
            }

            [PSCustomObject]@{
                RecordType = "controlled-file"
                Name = $RelativePath
                Profile = $null
                Check = "canonical-sha256"
                Expected = $ExpectedHash
                Actual = $ActualHash
                Pass = (
                    $Exists -and
                    $ActualHash -eq $ExpectedHash
                )
            }
        }
    )

    $GeneratedComparisons = @()

    foreach ($Profile in @($Baseline.profiles)) {
        $NormalizedProfile = Assert-B32Profile `
            -Profile ([string]$Profile)

        $Defaults = Get-B32ProfileDefaults `
            -RepoRoot $Environment.RepoRoot `
            -Profile $NormalizedProfile

        $Layout = Get-B33BuildLayout `
            -RepoRoot $Environment.RepoRoot `
            -Profile $NormalizedProfile `
            -Instance "config_drift"

        if (Test-Path -LiteralPath $Layout.BuildDir) {
            Remove-Item `
                -LiteralPath $Layout.BuildDir `
                -Recurse `
                -Force
        }

        New-B32Directory -Path $Layout.BuildDir | Out-Null

        $env:SQD_BUILD_PROFILE = $NormalizedProfile
        $env:SQD_HARDWARE_COMPATIBILITY = $Environment.HardwareCompatibility
        $env:SOURCE_DATE_EPOCH = [string]$Environment.SourceDateEpoch

        $BuildDirCMake = $Layout.BuildDir.Replace("\", "/")
        $SdkconfigCMake = $Layout.Sdkconfig.Replace("\", "/")

        $Arguments = @(
            "-DIDF_TARGET=$($Environment.Target)"
            "-DSDKCONFIG=$SdkconfigCMake"
            "-DSDKCONFIG_DEFAULTS=$($Defaults.CMakeValue)"
            "-B"
            $BuildDirCMake
            "reconfigure"
        )

        Invoke-B33Idf `
            -Environment $Environment `
            -Arguments $Arguments `
            -Operation "config_drift_$NormalizedProfile" `
            -Timestamp $Timestamp |
            Out-Null

        Assert-B32GeneratedConfiguration `
            -SdkconfigPath $Layout.Sdkconfig `
            -Profile $NormalizedProfile |
            Out-Null

        $GeneratedLines = @(
            Get-Content `
                -LiteralPath $Layout.Sdkconfig `
                -ErrorAction Stop
        )

        foreach ($RequiredLine in @(
            $Baseline.generated_configuration.required
        )) {
            $RequiredText = [string]$RequiredLine

            $GeneratedComparisons += [PSCustomObject]@{
                RecordType = "generated-sdkconfig"
                Name = $Layout.Sdkconfig
                Profile = $NormalizedProfile
                Check = "required-setting"
                Expected = $RequiredText
                Actual = if ($GeneratedLines -contains $RequiredText) {
                    $RequiredText
                }
                else {
                    "<missing>"
                }
                Pass = $GeneratedLines -contains $RequiredText
            }
        }

        foreach ($ForbiddenLine in @(
            $Baseline.generated_configuration.forbidden_enabled
        )) {
            $ForbiddenText = [string]$ForbiddenLine
            $IsEnabled = $GeneratedLines -contains $ForbiddenText

            $GeneratedComparisons += [PSCustomObject]@{
                RecordType = "generated-sdkconfig"
                Name = $Layout.Sdkconfig
                Profile = $NormalizedProfile
                Check = "forbidden-setting"
                Expected = "<not enabled>"
                Actual = if ($IsEnabled) {
                    $ForbiddenText
                }
                else {
                    "<not enabled>"
                }
                Pass = -not $IsEnabled
            }
        }
    }

    $Comparisons = @(
        $FileComparisons
        $GeneratedComparisons
    )

    $Comparisons |
        Export-Csv `
            -LiteralPath $ComparisonPath `
            -NoTypeInformation `
            -Encoding UTF8

    $Failures = @(
        $Comparisons |
        Where-Object { -not $_.Pass }
    )

    $Status = if ($Failures.Count -eq 0) {
        "PASS"
    }
    else {
        "FAIL"
    }

    $Result = [ordered]@{
        work_package = "B3.3"
        operation = "configuration-drift"
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
            controlled_file_count = @(
                $Baseline.controlled_files
            ).Count
            profile_count = @(
                $Baseline.profiles
            ).Count
        }
        toolchain = [ordered]@{
            idf_path = $Environment.IdfPath
            idf_version = $Environment.IdfVersion
            python = $Environment.PythonExe
            target = $Environment.Target
            source_date_epoch = $Environment.SourceDateEpoch
        }
        verification = [ordered]@{
            check_count = $Comparisons.Count
            pass_count = @(
                $Comparisons |
                Where-Object Pass
            ).Count
            fail_count = $Failures.Count
            comparison_csv = $ComparisonPath
        }
    }

    Write-B32JsonFile `
        -InputObject $Result `
        -Path $ResultPath `
        -Depth 12 |
        Out-Null

    $Summary = @(
        "============================================================"
        "B3.3 CONFIGURATION DRIFT CHECK"
        "============================================================"
        "Status:                    $Status"
        "Timestamp:                 $((Get-Date).ToString('o'))"
        "Branch:                    $Branch"
        "Commit:                    $($RepositoryState.Commit)"
        "Baseline:                  $ResolvedBaselinePath"
        "Controlled files:          $(@($Baseline.controlled_files).Count)"
        "Profiles checked:          $(@($Baseline.profiles).Count)"
        "Total checks:              $($Comparisons.Count)"
        "Passed checks:             $(@($Comparisons | Where-Object Pass).Count)"
        "Failed checks:             $($Failures.Count)"
        "Comparison CSV:            $ComparisonPath"
        "Result JSON:               $ResultPath"
        ""
        "B3.3 CONFIGURATION DRIFT CHECK $Status"
    ) -join [Environment]::NewLine

    Write-B32TextFile `
        -Content ($Summary + [Environment]::NewLine) `
        -Path $SummaryPath |
        Out-Null

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "B3.3 CONFIGURATION DRIFT CHECK $Status"
    Write-Host "============================================================"
    Write-Host "Controlled files: $(@($Baseline.controlled_files).Count)"
    Write-Host "Profiles:         $(@($Baseline.profiles).Count)"
    Write-Host "Checks:           $($Comparisons.Count)"
    Write-Host "Failures:         $($Failures.Count)"
    Write-Host "Summary:          $SummaryPath"
    Write-Host "Result JSON:      $ResultPath"
    Write-Host "Comparison CSV:   $ComparisonPath"

    if ($Status -ne "PASS") {
        throw "Configuration-drift verification failed."
    }
}
catch {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "B3.3 CONFIGURATION DRIFT CHECK FAILED"
    Write-Host "============================================================"
    Write-Host $_.Exception.Message -ForegroundColor Red
    throw
}
