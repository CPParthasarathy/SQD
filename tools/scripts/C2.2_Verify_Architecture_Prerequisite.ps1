Clear-Host -ErrorAction SilentlyContinue

Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Get-Location).Path
$AmendmentPath = "tools/ci/c2_2_architecture_amendment.json"
$AdrPath = "docs/phase-c/architecture-decisions/ADR-0003_Shared_Status_Foundation_Contract.md"
$CoreReadmePath = "components/core/README.md"
$CoreCMakePath = "components/core/CMakeLists.txt"
$StatusHeaderPath = "components/core/include/sqd_status.h"

$Checks = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [bool]$Passed,

        [Parameter(Mandatory = $true)]
        [string]$Detail
    )

    $Checks.Add(
        [pscustomobject]@{
            name = $Name
            passed = $Passed
            detail = $Detail
        }
    ) | Out-Null
}

function Get-GitBlob {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $Blob = (git hash-object -- $Path).Trim()

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to calculate Git blob for '$Path'."
    }

    return $Blob
}

Write-Host ""
Write-Host "=== C2.2 architecture-prerequisite verification ==="

if (-not (Test-Path -LiteralPath $AmendmentPath -PathType Leaf)) {
    throw "Missing architecture amendment."
}

$Amendment = Get-Content -LiteralPath $AmendmentPath -Raw | ConvertFrom-Json

$ExpectedStatusCodes = @(
    "SQD_STATUS_OK",
    "SQD_STATUS_INVALID_ARGUMENT",
    "SQD_STATUS_INVALID_STATE",
    "SQD_STATUS_ALREADY_INITIALIZED",
    "SQD_STATUS_NOT_FOUND",
    "SQD_STATUS_BUSY",
    "SQD_STATUS_TIMEOUT",
    "SQD_STATUS_IO",
    "SQD_STATUS_INTEGRITY",
    "SQD_STATUS_AUTHORIZATION",
    "SQD_STATUS_NO_MEMORY",
    "SQD_STATUS_NOT_SUPPORTED",
    "SQD_STATUS_CANCELLED",
    "SQD_STATUS_INTERNAL"
)

$SourceRecords = @(
    $Amendment.accepted_sources.PSObject.Properties |
        ForEach-Object { $_.Value }
)

$BlobFailures = @()

foreach ($SourceRecord in $SourceRecords) {
    $ActualBlob = Get-GitBlob -Path ([string]$SourceRecord.path)

    if ($ActualBlob -ne [string]$SourceRecord.blob) {
        $BlobFailures += (
            "{0}: expected {1}, found {2}" -f
            $SourceRecord.path,
            $SourceRecord.blob,
            $ActualBlob
        )
    }
}

$BlobPassed = $BlobFailures.Count -eq 0
$BlobDetail = "All accepted architecture source blobs match."

if (-not $BlobPassed) {
    $BlobDetail = $BlobFailures -join "; "
}

Add-Check -Name "accepted-source-blobs" -Passed $BlobPassed -Detail $BlobDetail

$RequiredFiles = @(
    $AdrPath,
    $CoreReadmePath,
    $CoreCMakePath,
    $StatusHeaderPath
)

$MissingFiles = @(
    $RequiredFiles |
        Where-Object {
            -not (Test-Path -LiteralPath $_ -PathType Leaf)
        }
)

$FilesPassed = $MissingFiles.Count -eq 0
$FilesDetail = "All ADR and core-component files are present."

if (-not $FilesPassed) {
    $FilesDetail = "Missing files: " + ($MissingFiles -join ", ")
}

Add-Check -Name "required-files" -Passed $FilesPassed -Detail $FilesDetail

$ExpectedCMakeLines = @(
    "idf_component_register(",
    '    INCLUDE_DIRS "include"',
    ")"
)

$ActualCMakeLines = @()

if (Test-Path -LiteralPath $CoreCMakePath -PathType Leaf) {
    $ActualCMakeLines = @(Get-Content -LiteralPath $CoreCMakePath)
}

$CMakePassed = (
    ($ActualCMakeLines -join "
") -eq
    ($ExpectedCMakeLines -join "
")
)

$CMakeDetail = "Core component is header-only and dependency-free."

if (-not $CMakePassed) {
    $CMakeDetail = "Core CMake registration differs from the approved contract."
}

Add-Check -Name "header-only-core" -Passed $CMakePassed -Detail $CMakeDetail

$HeaderText = ""

if (Test-Path -LiteralPath $StatusHeaderPath -PathType Leaf) {
    $HeaderText = Get-Content -LiteralPath $StatusHeaderPath -Raw
}

$MissingStatusValues = @()

for ($Index = 0; $Index -lt $ExpectedStatusCodes.Count; $Index++) {
    $ExpectedDefinition = "{0} = {1}" -f $ExpectedStatusCodes[$Index], $Index

    if (-not $HeaderText.Contains($ExpectedDefinition)) {
        $MissingStatusValues += $ExpectedDefinition
    }
}

$StatusPassed = (
    $HeaderText.Contains("} sqd_status_t;") -and
    $MissingStatusValues.Count -eq 0
)

$StatusDetail = "sqd_status_t contains all 14 controlled values."

if (-not $StatusPassed) {
    $StatusDetail = "Missing status definitions: " + ($MissingStatusValues -join ", ")
}

Add-Check -Name "status-contract" -Passed $StatusPassed -Detail $StatusDetail

$ForbiddenHeaderTokens = @(
    "esp_err_t",
    "driver/",
    "freertos/",
    "gpio_num_t",
    "sqd_board",
    "sqd_platform"
)

$FoundForbiddenTokens = @(
    $ForbiddenHeaderTokens |
        Where-Object {
            $HeaderText.Contains($_)
        }
)

$NeutralPassed = $FoundForbiddenTokens.Count -eq 0
$NeutralDetail = "Status header has no ESP-IDF, board or platform dependency."

if (-not $NeutralPassed) {
    $NeutralDetail = "Forbidden header tokens: " + ($FoundForbiddenTokens -join ", ")
}

Add-Check -Name "neutral-status-boundary" -Passed $NeutralPassed -Detail $NeutralDetail

$AdrText = ""

if (Test-Path -LiteralPath $AdrPath -PathType Leaf) {
    $AdrText = Get-Content -LiteralPath $AdrPath -Raw
}

$RequiredAdrTokens = @(
    "ADR-0003",
    "components/core",
    "sqd_status_t",
    "board -> core",
    "accepted C1.1, C1.2 and C1.3",
    "must remain header-only"
)

$MissingAdrTokens = @(
    $RequiredAdrTokens |
        Where-Object {
            -not $AdrText.Contains($_)
        }
)

$AdrPassed = $MissingAdrTokens.Count -eq 0
$AdrDetail = "ADR-0003 contains the required ownership and preservation clauses."

if (-not $AdrPassed) {
    $AdrDetail = "Missing ADR tokens: " + ($MissingAdrTokens -join ", ")
}

Add-Check -Name "adr-contract" -Passed $AdrPassed -Detail $AdrDetail

$Component = $Amendment.component_addition

$ComponentPassed = (
    $Component.id -eq "core" -and
    $Component.path -eq "components/core" -and
    $Component.implementation_status -eq "header-only" -and
    $Component.owns_mutable_state -eq $false -and
    @($Component.permitted_dependencies).Count -eq 0
)

$ComponentDetail = "Core is recorded as a stateless, dependency-free foundation contract."

if (-not $ComponentPassed) {
    $ComponentDetail = "Core architecture amendment record is invalid."
}

Add-Check -Name "core-amendment" -Passed $ComponentPassed -Detail $ComponentDetail

$DependencyRecords = @($Amendment.dependency_additions)

$MatchingDependencies = @(
    $DependencyRecords |
        Where-Object {
            $_.caller -eq "board" -and
            $_.target -eq "core" -and
            $_.direction -eq "downward" -and
            $_.same_level_exception -eq $false
        }
)

$DependencyPassed = (
    $DependencyRecords.Count -eq 1 -and
    $MatchingDependencies.Count -eq 1
)

$DependencyDetail = "Exactly one downward board-to-core dependency is approved."

if (-not $DependencyPassed) {
    $DependencyDetail = "Board-to-core dependency record is missing or ambiguous."
}

Add-Check -Name "board-core-dependency" -Passed $DependencyPassed -Detail $DependencyDetail

$ConfiguredCodes = @($Amendment.status_contract.status_codes)

$OrderPassed = (
    ($ConfiguredCodes -join "|") -eq
    ($ExpectedStatusCodes -join "|")
)

$OrderDetail = "Machine-readable status order matches the public header."

if (-not $OrderPassed) {
    $OrderDetail = "Machine-readable status order is invalid."
}

Add-Check -Name "status-order" -Passed $OrderPassed -Detail $OrderDetail

$Rules = $Amendment.preservation_rules

$PreservationPassed = (
    $Rules.accepted_c1_sources_are_modified -eq $false -and
    $Rules.accepted_contracts_are_modified -eq $false -and
    $Rules.board_owned_status_type_forbidden -eq $true -and
    $Rules.platform_owned_status_type_forbidden -eq $true -and
    $Rules.public_esp_err_t_forbidden -eq $true -and
    $Rules.core_runtime_state_forbidden -eq $true -and
    $Rules.core_general_utility_role_forbidden -eq $true
)

$PreservationDetail = "Accepted-source preservation rules are complete."

if (-not $PreservationPassed) {
    $PreservationDetail = "Architecture preservation rules are incomplete."
}

Add-Check -Name "preservation-rules" -Passed $PreservationPassed -Detail $PreservationDetail

$PassedCount = @($Checks | Where-Object { $_.passed }).Count
$FailedCount = $Checks.Count - $PassedCount

Write-Host ""

foreach ($Check in $Checks) {
    $State = "FAIL"

    if ($Check.passed) {
        $State = "PASS"
    }

    Write-Host (
        "{0,-4} {1}: {2}" -f
        $State,
        $Check.name,
        $Check.detail
    )
}

Write-Host ""
Write-Host ("PASS: {0}" -f $PassedCount)
Write-Host ("FAIL: {0}" -f $FailedCount)

if ($FailedCount -ne 0) {
    exit 1
}

Write-Host ""
Write-Host "C2.2 architecture prerequisite PASSED."
exit 0
