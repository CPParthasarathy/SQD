[CmdletBinding()]
param(
    [ValidateSet("debug", "validation", "production")]
    [string]$Profile = "production",

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

function Get-B33FlashRecords {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$BuildDir
    )

    $FlasherArgsPath = Assert-B32File `
        -Path (Join-Path $BuildDir "flasher_args.json") `
        -Description "Flasher arguments"

    $FlasherArgs = Get-Content -LiteralPath $FlasherArgsPath -Raw |
        ConvertFrom-Json

    if ($null -eq $FlasherArgs.flash_files) {
        throw "flasher_args.json does not contain flash_files: $FlasherArgsPath"
    }

    @(
        foreach ($Property in $FlasherArgs.flash_files.PSObject.Properties) {
            $Offset = [string]$Property.Name
            $ArtifactPath = [string]$Property.Value

            if (-not [System.IO.Path]::IsPathRooted($ArtifactPath)) {
                $ArtifactPath = Join-Path $BuildDir $ArtifactPath
            }

            $ResolvedPath = Assert-B32File `
                -Path $ArtifactPath `
                -Description "Flash binary at $Offset"

            $RelativePath = $ResolvedPath

            if ($ResolvedPath.StartsWith(
                $BuildDir,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
                $RelativePath = $ResolvedPath.Substring(
                    $BuildDir.Length
                ).TrimStart("\")
            }

            $Item = Get-Item -LiteralPath $ResolvedPath

            [PSCustomObject]@{
                Key = "$Offset|$($RelativePath.Replace('\', '/'))"
                Offset = $Offset
                RelativePath = $RelativePath.Replace("\", "/")
                Path = $ResolvedPath
                SizeBytes = [int64]$Item.Length
                SHA256 = (
                    Get-FileHash -LiteralPath $ResolvedPath -Algorithm SHA256
                ).Hash
            }
        }
    ) | Sort-Object Key
}

$Timestamp = Get-B33Timestamp
$EvidenceDir = Get-B33EvidenceDirectory -RepoRoot $RepoRoot
$SummaryPath = Join-Path $EvidenceDir "B3.3_reproducibility_summary_${Timestamp}.txt"
$ResultPath = Join-Path $EvidenceDir "B3.3_reproducibility_result_${Timestamp}.json"
$ComparisonPath = Join-Path $EvidenceDir "B3.3_reproducibility_comparison_${Timestamp}.csv"

try {
    Write-B32Section -Title "B3.3 REPRODUCIBLE BUILD TEST"

    $Branch = Assert-B33FeatureBranch -RepoRoot $RepoRoot
    $RepositoryState = Get-B32RepositoryState -RepoRoot $RepoRoot
    $Environment = Initialize-B33Environment -RepoRoot $RepoRoot -IdfPath $IdfPath
    $NormalizedProfile = Assert-B32Profile -Profile $Profile
    $Defaults = Get-B32ProfileDefaults `
        -RepoRoot $Environment.RepoRoot `
        -Profile $NormalizedProfile

    $LayoutA = Get-B33BuildLayout `
        -RepoRoot $Environment.RepoRoot `
        -Profile $NormalizedProfile `
        -Instance "repro_a"

    $LayoutB = Get-B33BuildLayout `
        -RepoRoot $Environment.RepoRoot `
        -Profile $NormalizedProfile `
        -Instance "repro_b"

    foreach ($Layout in @($LayoutA, $LayoutB)) {
        if (Test-Path -LiteralPath $Layout.BuildDir) {
            Remove-Item -LiteralPath $Layout.BuildDir -Recurse -Force
        }

        New-B32Directory -Path $Layout.BuildDir | Out-Null
    }

    $env:SQD_BUILD_PROFILE = $NormalizedProfile
    $env:SQD_HARDWARE_COMPATIBILITY = $Environment.HardwareCompatibility
    $env:SOURCE_DATE_EPOCH = [string]$Environment.SourceDateEpoch

    Write-Host "Profile:           $NormalizedProfile"
    Write-Host "Branch:            $Branch"
    Write-Host "Commit:            $($RepositoryState.Commit)"
    Write-Host "ESP-IDF:           $($Environment.IdfVersion)"
    Write-Host "Python:            $($Environment.PythonExe)"
    Write-Host "SOURCE_DATE_EPOCH: $($Environment.SourceDateEpoch)"
    Write-Host "Build A:           $($LayoutA.BuildDir)"
    Write-Host "Build B:           $($LayoutB.BuildDir)"
    Write-Host ""

    $BuildResults = @{}

    foreach ($Definition in @(
        [PSCustomObject]@{ Name = "a"; Layout = $LayoutA },
        [PSCustomObject]@{ Name = "b"; Layout = $LayoutB }
    )) {
        $BuildDirCMake = $Definition.Layout.BuildDir.Replace("\", "/")
        $SdkconfigCMake = $Definition.Layout.Sdkconfig.Replace("\", "/")

        $Arguments = @(
            "-DIDF_TARGET=$($Environment.Target)"
            "-DSDKCONFIG=$SdkconfigCMake"
            "-DSDKCONFIG_DEFAULTS=$($Defaults.CMakeValue)"
            "-B"
            $BuildDirCMake
            "build"
        )

        $BuildResults[$Definition.Name] = Invoke-B33Idf `
            -Environment $Environment `
            -Arguments $Arguments `
            -Operation "repro_build_$($Definition.Name)" `
            -Timestamp $Timestamp

        Assert-B33ReproducibleConfiguration `
            -SdkconfigPath $Definition.Layout.Sdkconfig `
            -Profile $NormalizedProfile |
            Out-Null
    }

    $ConfigAHash = (
        Get-FileHash -LiteralPath $LayoutA.Sdkconfig -Algorithm SHA256
    ).Hash

    $ConfigBHash = (
        Get-FileHash -LiteralPath $LayoutB.Sdkconfig -Algorithm SHA256
    ).Hash

    $RecordsA = @(Get-B33FlashRecords -BuildDir $LayoutA.BuildDir)
    $RecordsB = @(Get-B33FlashRecords -BuildDir $LayoutB.BuildDir)

    $MapA = @{}
    $MapB = @{}

    foreach ($Record in $RecordsA) {
        $MapA[$Record.Key] = $Record
    }

    foreach ($Record in $RecordsB) {
        $MapB[$Record.Key] = $Record
    }

    $AllKeys = @(
        @($MapA.Keys) + @($MapB.Keys) |
        Sort-Object -Unique
    )

    $Comparisons = @(
        foreach ($Key in $AllKeys) {
            $A = $MapA[$Key]
            $B = $MapB[$Key]
            $Match = (
                $null -ne $A -and
                $null -ne $B -and
                $A.SizeBytes -eq $B.SizeBytes -and
                $A.SHA256 -eq $B.SHA256
            )

            [PSCustomObject]@{
                Key = $Key
                BuildASizeBytes = if ($null -ne $A) { $A.SizeBytes } else { $null }
                BuildASHA256 = if ($null -ne $A) { $A.SHA256 } else { $null }
                BuildBSizeBytes = if ($null -ne $B) { $B.SizeBytes } else { $null }
                BuildBSHA256 = if ($null -ne $B) { $B.SHA256 } else { $null }
                Match = $Match
            }
        }
    )

    $Comparisons |
        Export-Csv -LiteralPath $ComparisonPath -NoTypeInformation -Encoding UTF8

    $Mismatches = @($Comparisons | Where-Object { -not $_.Match })
    $ConfigurationMatch = $ConfigAHash -eq $ConfigBHash
    $BinarySetMatch = (
        $RecordsA.Count -eq $RecordsB.Count -and
        $Mismatches.Count -eq 0
    )

    $Status = if ($ConfigurationMatch -and $BinarySetMatch) {
        "PASS"
    }
    else {
        "FAIL"
    }

    $Result = [ordered]@{
        work_package = "B3.3"
        operation = "reproducible-build"
        status = $Status
        timestamp_local = (Get-Date).ToString("o")
        profile = $NormalizedProfile
        repository = [ordered]@{
            branch = $RepositoryState.Branch
            commit = $RepositoryState.Commit
            tracked_tree_clean = [string]::IsNullOrWhiteSpace(
                $RepositoryState.TrackedStatusPorcelain
            )
        }
        toolchain = [ordered]@{
            idf_path = $Environment.IdfPath
            idf_version = $Environment.IdfVersion
            python = $Environment.PythonExe
            target = $Environment.Target
            source_date_epoch = $Environment.SourceDateEpoch
        }
        build_a = [ordered]@{
            directory = $LayoutA.BuildDir
            duration_seconds = $BuildResults["a"].DurationSeconds
            sdkconfig_sha256 = $ConfigAHash
        }
        build_b = [ordered]@{
            directory = $LayoutB.BuildDir
            duration_seconds = $BuildResults["b"].DurationSeconds
            sdkconfig_sha256 = $ConfigBHash
        }
        comparison = [ordered]@{
            generated_configuration_match = $ConfigurationMatch
            flash_binary_count_a = $RecordsA.Count
            flash_binary_count_b = $RecordsB.Count
            flash_binary_set_match = $BinarySetMatch
            mismatch_count = $Mismatches.Count
            csv = $ComparisonPath
        }
    }

    Write-B32JsonFile -InputObject $Result -Path $ResultPath -Depth 12 |
        Out-Null

    $Summary = @(
        "B3.3 REPRODUCIBLE BUILD TEST"
        "Status: $Status"
        "Timestamp: $((Get-Date).ToString('o'))"
        "Profile: $NormalizedProfile"
        "Branch: $($RepositoryState.Branch)"
        "Commit: $($RepositoryState.Commit)"
        "ESP-IDF: $($Environment.IdfVersion)"
        "Python: $($Environment.PythonExe)"
        "SOURCE_DATE_EPOCH: $($Environment.SourceDateEpoch)"
        "Configuration match: $ConfigurationMatch"
        "Flash binary count A: $($RecordsA.Count)"
        "Flash binary count B: $($RecordsB.Count)"
        "Flash binary set match: $BinarySetMatch"
        "Binary mismatch count: $($Mismatches.Count)"
        "Comparison CSV: $ComparisonPath"
        "Result JSON: $ResultPath"
    ) -join [Environment]::NewLine

    Write-B32TextFile `
        -Content ($Summary + [Environment]::NewLine) `
        -Path $SummaryPath |
        Out-Null

    Write-Host ""
    Write-Host "B3.3 REPRODUCIBLE BUILD TEST $Status"
    Write-Host "Configuration match: $ConfigurationMatch"
    Write-Host "Flash binaries:      $($RecordsA.Count)"
    Write-Host "Binary mismatches:   $($Mismatches.Count)"
    Write-Host "Summary:             $SummaryPath"
    Write-Host "Result JSON:         $ResultPath"
    Write-Host "Comparison CSV:      $ComparisonPath"

    if ($Status -ne "PASS") {
        throw "Reproducible-build verification failed."
    }
}
catch {
    Write-Host ""
    Write-Host "B3.3 REPRODUCIBLE BUILD TEST FAILED"
    Write-Host $_.Exception.Message -ForegroundColor Red
    throw
}
