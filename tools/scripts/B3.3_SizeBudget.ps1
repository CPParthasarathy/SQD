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

$Timestamp = Get-B33Timestamp
$EvidenceDir = Get-B33EvidenceDirectory -RepoRoot $RepoRoot

$BaselinePath = Join-Path `
    $RepoRoot `
    "tools\config\B3.3_size_budget.json"

$SummaryPath = Join-Path `
    $EvidenceDir `
    "B3.3_size_budget_summary_${Timestamp}.txt"

$ResultPath = Join-Path `
    $EvidenceDir `
    "B3.3_size_budget_result_${Timestamp}.json"

$ComparisonPath = Join-Path `
    $EvidenceDir `
    "B3.3_size_budget_comparison_${Timestamp}.csv"

$SizeReportPath = Join-Path `
    $EvidenceDir `
    "B3.3_size_budget_measurement_${Timestamp}.json"

try {
    Write-B32Section -Title "B3.3 FIRMWARE IMAGE-SIZE BUDGET"

    $Branch = Assert-B33FeatureBranch -RepoRoot $RepoRoot

    $ResolvedBaselinePath = Assert-B32File `
        -Path $BaselinePath `
        -Description "B3.3 size-budget baseline"

    $Baseline = Get-Content `
        -LiteralPath $ResolvedBaselinePath `
        -Raw |
        ConvertFrom-Json

    if ([int]$Baseline.schema_version -ne 1) {
        throw "Unsupported size-budget schema version '$($Baseline.schema_version)'."
    }

    $Profile = Assert-B32Profile `
        -Profile ([string]$Baseline.profile)

    if ($Profile -ne "production") {
        throw "Size budget must use the production profile."
    }

    $Environment = Initialize-B33Environment `
        -RepoRoot $RepoRoot `
        -IdfPath $IdfPath

    $RepositoryState = Get-B32RepositoryState `
        -RepoRoot $Environment.RepoRoot

    $Defaults = Get-B32ProfileDefaults `
        -RepoRoot $Environment.RepoRoot `
        -Profile $Profile

    $Layout = Get-B33BuildLayout `
        -RepoRoot $Environment.RepoRoot `
        -Profile $Profile `
        -Instance "size_budget"

    if (Test-Path -LiteralPath $Layout.BuildDir) {
        Remove-Item `
            -LiteralPath $Layout.BuildDir `
            -Recurse `
            -Force
    }

    New-B32Directory -Path $Layout.BuildDir | Out-Null

    $env:SQD_BUILD_PROFILE = $Profile
    $env:SQD_HARDWARE_COMPATIBILITY = $Environment.HardwareCompatibility
    $env:SOURCE_DATE_EPOCH = [string]$Environment.SourceDateEpoch

    $BuildDirCMake = $Layout.BuildDir.Replace("\", "/")
    $SdkconfigCMake = $Layout.Sdkconfig.Replace("\", "/")

    $BuildArguments = @(
        "-DIDF_TARGET=$($Environment.Target)"
        "-DSDKCONFIG=$SdkconfigCMake"
        "-DSDKCONFIG_DEFAULTS=$($Defaults.CMakeValue)"
        "-B"
        $BuildDirCMake
        "build"
    )

    $BuildResult = Invoke-B33Idf `
        -Environment $Environment `
        -Arguments $BuildArguments `
        -Operation "size_budget_build" `
        -Timestamp $Timestamp

    Assert-B33ReproducibleConfiguration `
        -SdkconfigPath $Layout.Sdkconfig `
        -Profile $Profile |
        Out-Null

    $SizeArguments = @(
        "-B"
        $BuildDirCMake
        "size"
        "--format"
        "json2"
        "--output-file"
        $SizeReportPath
    )

    $SizeResult = Invoke-B33Idf `
        -Environment $Environment `
        -Arguments $SizeArguments `
        -Operation "size_budget_measurement" `
        -Timestamp $Timestamp

    $ResolvedSizeReport = Assert-B32File `
        -Path $SizeReportPath `
        -Description "JSON size report"

    $SizeReport = Get-Content `
        -LiteralPath $ResolvedSizeReport `
        -Raw |
        ConvertFrom-Json

    $ProjectDescription = Get-B32ProjectDescription `
        -BuildDir $Layout.BuildDir

    $ProjectName = [string]$ProjectDescription.project_name

    if ([string]::IsNullOrWhiteSpace($ProjectName)) {
        throw "Project name was not found in project_description.json."
    }

    $ApplicationBinaryPath = Assert-B32File `
        -Path (Join-Path $Layout.BuildDir "$ProjectName.bin") `
        -Description "Application binary"

    $ApplicationBinaryBytes = [int64](
        Get-Item -LiteralPath $ApplicationBinaryPath
    ).Length

    $ApplicationBinaryHash = (
        Get-FileHash `
            -LiteralPath $ApplicationBinaryPath `
            -Algorithm SHA256
    ).Hash

    $LinkedImageTotalBytes = [int64]$SizeReport.total_size
    $ApplicationCapacityBytes = [int64](
        $Baseline.partition.application_capacity_bytes
    )
    $MinimumHeadroomBytes = [int64](
        $Baseline.partition.minimum_headroom_bytes
    )
    $ApplicationBudgetBytes = [int64](
        $Baseline.budgets.application_binary_max_bytes
    )
    $LinkedImageBudgetBytes = [int64](
        $Baseline.budgets.linked_image_total_max_bytes
    )

    $PartitionHeadroomBytes = (
        $ApplicationCapacityBytes -
        $ApplicationBinaryBytes
    )

    $PartitionUsagePercent = [math]::Round(
        (
            $ApplicationBinaryBytes /
            $ApplicationCapacityBytes
        ) * 100,
        2
    )

    $GeneratedConfig = @(
        Get-Content `
            -LiteralPath $Layout.Sdkconfig `
            -ErrorAction Stop
    )

    $SingleAppEnabled = (
        $GeneratedConfig -contains
        "CONFIG_PARTITION_TABLE_SINGLE_APP=y"
    )

    $Checks = @(
        [PSCustomObject]@{
            Check = "production-profile"
            Actual = $Profile
            Limit = "production"
            Unit = "profile"
            Pass = $Profile -eq "production"
        }
        [PSCustomObject]@{
            Check = "single-app-partition-scheme"
            Actual = [string]$SingleAppEnabled
            Limit = "True"
            Unit = "boolean"
            Pass = $SingleAppEnabled
        }
        [PSCustomObject]@{
            Check = "application-binary-budget"
            Actual = $ApplicationBinaryBytes
            Limit = $ApplicationBudgetBytes
            Unit = "bytes-max"
            Pass = (
                $ApplicationBinaryBytes -le
                $ApplicationBudgetBytes
            )
        }
        [PSCustomObject]@{
            Check = "linked-image-total-budget"
            Actual = $LinkedImageTotalBytes
            Limit = $LinkedImageBudgetBytes
            Unit = "bytes-max"
            Pass = (
                $LinkedImageTotalBytes -le
                $LinkedImageBudgetBytes
            )
        }
        [PSCustomObject]@{
            Check = "application-partition-capacity"
            Actual = $ApplicationBinaryBytes
            Limit = $ApplicationCapacityBytes
            Unit = "bytes-max"
            Pass = (
                $ApplicationBinaryBytes -le
                $ApplicationCapacityBytes
            )
        }
        [PSCustomObject]@{
            Check = "minimum-partition-headroom"
            Actual = $PartitionHeadroomBytes
            Limit = $MinimumHeadroomBytes
            Unit = "bytes-min"
            Pass = (
                $PartitionHeadroomBytes -ge
                $MinimumHeadroomBytes
            )
        }
    )

    $Checks |
        Export-Csv `
            -LiteralPath $ComparisonPath `
            -NoTypeInformation `
            -Encoding UTF8

    $Failures = @(
        $Checks |
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
        operation = "firmware-image-size-budget"
        status = $Status
        timestamp_local = (Get-Date).ToString("o")
        repository = [ordered]@{
            root = $Environment.RepoRoot
            branch = $RepositoryState.Branch
            commit = $RepositoryState.Commit
            commit_short = $RepositoryState.CommitShort
        }
        toolchain = [ordered]@{
            idf_path = $Environment.IdfPath
            idf_version = $Environment.IdfVersion
            python = $Environment.PythonExe
            target = $Environment.Target
            source_date_epoch = $Environment.SourceDateEpoch
        }
        baseline = [ordered]@{
            path = $ResolvedBaselinePath
            schema_version = [int]$Baseline.schema_version
            profile = $Profile
        }
        measurement = [ordered]@{
            project = $ProjectName
            build_directory = $Layout.BuildDir
            application_binary = $ApplicationBinaryPath
            application_binary_bytes = $ApplicationBinaryBytes
            application_binary_sha256 = $ApplicationBinaryHash
            linked_image_total_bytes = $LinkedImageTotalBytes
            application_partition_capacity_bytes = $ApplicationCapacityBytes
            application_partition_headroom_bytes = $PartitionHeadroomBytes
            application_partition_usage_percent = $PartitionUsagePercent
            size_report = $ResolvedSizeReport
        }
        budgets = [ordered]@{
            application_binary_max_bytes = $ApplicationBudgetBytes
            linked_image_total_max_bytes = $LinkedImageBudgetBytes
            minimum_partition_headroom_bytes = $MinimumHeadroomBytes
        }
        verification = [ordered]@{
            check_count = $Checks.Count
            pass_count = @(
                $Checks |
                Where-Object Pass
            ).Count
            fail_count = $Failures.Count
            comparison_csv = $ComparisonPath
        }
        execution = [ordered]@{
            build_duration_seconds = $BuildResult.DurationSeconds
            size_duration_seconds = $SizeResult.DurationSeconds
            build_stdout = $BuildResult.StdoutPath
            build_stderr = $BuildResult.StderrPath
            size_stdout = $SizeResult.StdoutPath
            size_stderr = $SizeResult.StderrPath
        }
    }

    Write-B32JsonFile `
        -InputObject $Result `
        -Path $ResultPath `
        -Depth 20 |
        Out-Null

    $Summary = @(
        "============================================================"
        "B3.3 FIRMWARE IMAGE-SIZE BUDGET"
        "============================================================"
        "Status:                       $Status"
        "Timestamp:                    $((Get-Date).ToString('o'))"
        "Branch:                       $Branch"
        "Commit:                       $($RepositoryState.Commit)"
        "Profile:                      $Profile"
        "Project:                      $ProjectName"
        "Application binary bytes:     $ApplicationBinaryBytes"
        "Application binary budget:    $ApplicationBudgetBytes"
        "Linked image total bytes:     $LinkedImageTotalBytes"
        "Linked image budget:          $LinkedImageBudgetBytes"
        "Application partition bytes:  $ApplicationCapacityBytes"
        "Partition headroom bytes:     $PartitionHeadroomBytes"
        "Minimum required headroom:    $MinimumHeadroomBytes"
        "Partition usage percent:      $PartitionUsagePercent"
        "Checks:                       $($Checks.Count)"
        "Failures:                     $($Failures.Count)"
        "Comparison CSV:               $ComparisonPath"
        "Size report:                  $ResolvedSizeReport"
        "Result JSON:                  $ResultPath"
        ""
        "B3.3 FIRMWARE IMAGE-SIZE BUDGET $Status"
    ) -join [Environment]::NewLine

    Write-B32TextFile `
        -Content ($Summary + [Environment]::NewLine) `
        -Path $SummaryPath |
        Out-Null

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "B3.3 FIRMWARE IMAGE-SIZE BUDGET $Status"
    Write-Host "============================================================"
    Write-Host "Application binary: $ApplicationBinaryBytes / $ApplicationBudgetBytes bytes"
    Write-Host "Linked image:       $LinkedImageTotalBytes / $LinkedImageBudgetBytes bytes"
    Write-Host "Partition headroom: $PartitionHeadroomBytes bytes"
    Write-Host "Checks:             $($Checks.Count)"
    Write-Host "Failures:           $($Failures.Count)"
    Write-Host "Summary:            $SummaryPath"
    Write-Host "Result JSON:        $ResultPath"
    Write-Host "Comparison CSV:     $ComparisonPath"

    if ($Status -ne "PASS") {
        throw "Firmware image-size budget verification failed."
    }
}
catch {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "B3.3 FIRMWARE IMAGE-SIZE BUDGET FAILED"
    Write-Host "============================================================"
    Write-Host $_.Exception.Message -ForegroundColor Red
    throw
}
