Clear-Host

$ErrorActionPreference = "Stop"

$RepoRoot = if (
    -not [string]::IsNullOrWhiteSpace(
        $env:SQD_C13_REPO_ROOT
    )
) {
    (
        Resolve-Path `
            -LiteralPath $env:SQD_C13_REPO_ROOT
    ).Path
}
else {
    (
        Resolve-Path (
            Join-Path $PSScriptRoot "..\.."
        )
    ).Path
}

$ContractPath =
    "tools/ci/c1_architecture_contract.json"

$SourceContractPath =
    "tools/ci/c1_2_component_contract.json"

$ReviewDocumentPath =
    "docs/phase-c/C1.3_Architecture_Review_and_Gate.md"

$script:C13Checks =
    New-Object System.Collections.Generic.List[object]

function Write-C13Section {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title
    )

    Write-Host ""
    Write-Host "=== $Title ==="
}

function Add-C13Check {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Category,

        [Parameter(Mandatory = $true)]
        [string]$Check,

        [Parameter(Mandatory = $true)]
        [ValidateSet("PASS", "FAIL")]
        [string]$Status,

        [string]$Diagnostic = ""
    )

    $script:C13Checks.Add(
        [PSCustomObject][ordered]@{
            Category   = $Category
            Check      = $Check
            Status     = $Status
            Diagnostic = $Diagnostic
        }
    ) | Out-Null

    if ($Status -eq "PASS") {
        Write-Host "PASS: $Check"
    }
    else {
        Write-Host "FAIL: $Check"

        if (
            -not [string]::IsNullOrWhiteSpace(
                $Diagnostic
            )
        ) {
            Write-Host "      $Diagnostic"
        }
    }
}

function Resolve-C13Path {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $PlatformPath = $RelativePath.Replace(
        "/",
        [System.IO.Path]::DirectorySeparatorChar
    )

    return Join-Path $RepoRoot $PlatformPath
}

function Get-C13TrackedBlob {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $Output = @(
        git -C $RepoRoot `
            rev-parse `
            "HEAD:$RelativePath"
    )

    if (
        $LASTEXITCODE -ne 0 -or
        $Output.Count -eq 0
    ) {
        throw (
            "Unable to resolve tracked blob at HEAD: " +
            $RelativePath
        )
    }

    return ([string]$Output[0]).Trim()
}

function Get-C13ArraySignature {
    param(
        [AllowNull()]
        [object[]]$Values
    )

    return (
        @($Values) -join [char]0
    )
}

function Get-C13UniqueSortedStrings {
    param(
        [AllowNull()]
        [object[]]$Values
    )

    return @(
        @($Values) |
            ForEach-Object {
                [string]$_
            } |
            Sort-Object -Unique
    )
}

Write-C13Section `
    -Title "C1.3 ARCHITECTURE CONTRACT VERIFICATION"

$RepositoryRoot = (
    git -C $RepoRoot rev-parse --show-toplevel
).Trim()

if ($LASTEXITCODE -ne 0) {
    throw "RepoRoot is not a Git repository: $RepoRoot"
}

$NormalizedRepositoryRoot = $RepositoryRoot.
    Replace('\', '/').
    TrimEnd([char[]]@('/'))

$ExpectedRepositoryRoot = if (
    -not [string]::IsNullOrWhiteSpace(
        $env:SQD_C13_REPO_ROOT
    )
) {
    $RepoRoot.
        Replace('\', '/').
        TrimEnd([char[]]@('/'))
}
else {
    "D:/OneDrive/SQD"
}

if (
    -not $NormalizedRepositoryRoot.Equals(
        $ExpectedRepositoryRoot,
        [System.StringComparison]::OrdinalIgnoreCase
    )
) {
    throw (
        "Unexpected repository root: " +
        "$NormalizedRepositoryRoot; " +
        "expected $ExpectedRepositoryRoot"
    )
}

$FullContractPath =
    Resolve-C13Path `
        -RelativePath $ContractPath

$FullSourceContractPath =
    Resolve-C13Path `
        -RelativePath $SourceContractPath

$FullReviewDocumentPath =
    Resolve-C13Path `
        -RelativePath $ReviewDocumentPath

foreach ($RequiredPath in @(
    $FullContractPath,
    $FullSourceContractPath,
    $FullReviewDocumentPath
)) {
    if (
        -not (
            Test-Path `
                -LiteralPath $RequiredPath `
                -PathType Leaf
        )
    ) {
        throw (
            "Required C1.3 verification input " +
            "is missing: $RequiredPath"
        )
    }
}

try {
    $Contract = (
        Get-Content `
            -LiteralPath $FullContractPath `
            -Raw
    ) | ConvertFrom-Json
}
catch {
    throw (
        "C1.3 architecture contract is invalid JSON: " +
        $_.Exception.Message
    )
}

try {
    $SourceContract = (
        Get-Content `
            -LiteralPath $FullSourceContractPath `
            -Raw
    ) | ConvertFrom-Json
}
catch {
    throw (
        "Accepted C1.2 contract is invalid JSON: " +
        $_.Exception.Message
    )
}

$ReviewDocument = Get-Content `
    -LiteralPath $FullReviewDocumentPath `
    -Raw

Write-C13Section -Title "CONTRACT IDENTITY"

$IdentityFailures = @()

if ($Contract.schema_version -ne 2) {
    $IdentityFailures +=
        "schema_version must be 2; found '$($Contract.schema_version)'"
}

if ($Contract.work_package -ne "C1.3") {
    $IdentityFailures +=
        "work_package must be C1.3; found '$($Contract.work_package)'"
}

if ($Contract.gate -ne "G-C") {
    $IdentityFailures +=
        "gate must be G-C; found '$($Contract.gate)'"
}

$ValidState = (
    (
        $Contract.status -eq "Draft" -and
        $Contract.gate_status -eq "PENDING_VERIFICATION"
    ) -or
    (
        $Contract.status -eq "Accepted" -and
        $Contract.gate_status -eq "ACCEPTED"
    )
)

if (-not $ValidState) {
    $IdentityFailures +=
        "status/gate_status combination is invalid"
}

if (
    $Contract.completion_criterion -ne
    "No circular dependencies or overlapping responsibilities remain."
) {
    $IdentityFailures +=
        "completion criterion does not match the C1.3 gate"
}

if ($IdentityFailures.Count -eq 0) {
    Add-C13Check `
        -Category "Identity" `
        -Check "C1.3 contract identity and state are valid" `
        -Status "PASS"
}
else {
    Add-C13Check `
        -Category "Identity" `
        -Check "C1.3 contract identity and state are valid" `
        -Status "FAIL" `
        -Diagnostic (
            $IdentityFailures -join "; "
        )
}

Write-C13Section -Title "ACCEPTED SOURCE IDENTITIES"

$ExpectedParentDocuments = @(
    "docs/phase-c/C1.1_System_Architecture.md",
    "docs/phase-c/C1.2_Component_Interface_and_Runtime_Contracts.md"
)

$SourceIdentityFailures = @()

if (
    (
        Get-C13ArraySignature `
            -Values @($Contract.parent_documents)
    ) -ne
    (
        Get-C13ArraySignature `
            -Values $ExpectedParentDocuments
    )
) {
    $SourceIdentityFailures +=
        "parent_documents does not match accepted C1.1/C1.2"
}

if ($Contract.source_contract -ne $SourceContractPath) {
    $SourceIdentityFailures +=
        "source_contract does not match $SourceContractPath"
}

if ($SourceContract.work_package -ne "C1.2") {
    $SourceIdentityFailures +=
        "source contract work_package is not C1.2"
}

if ($SourceContract.status -ne "Accepted") {
    $SourceIdentityFailures +=
        "source contract is not Accepted"
}

$SourceBlobInputs = @(
    [PSCustomObject]@{
        Name     = "C1.1 document"
        Path     = $ExpectedParentDocuments[0]
        Recorded = [string]$Contract.source_blobs.c1_1_document
    },
    [PSCustomObject]@{
        Name     = "C1.2 document"
        Path     = $ExpectedParentDocuments[1]
        Recorded = [string]$Contract.source_blobs.c1_2_document
    },
    [PSCustomObject]@{
        Name     = "C1.2 machine contract"
        Path     = $SourceContractPath
        Recorded = [string]$Contract.source_blobs.c1_2_contract
    }
)

foreach ($SourceBlobInput in $SourceBlobInputs) {
    $ActualBlob = Get-C13TrackedBlob `
        -RelativePath $SourceBlobInput.Path

    if ($ActualBlob -ne $SourceBlobInput.Recorded) {
        $SourceIdentityFailures += (
            "$($SourceBlobInput.Name) blob mismatch: " +
            "recorded '$($SourceBlobInput.Recorded)', " +
            "actual '$ActualBlob'"
        )
    }
}

if ($SourceIdentityFailures.Count -eq 0) {
    Add-C13Check `
        -Category "Source" `
        -Check "accepted source paths and blobs resolve" `
        -Status "PASS"
}
else {
    Add-C13Check `
        -Category "Source" `
        -Check "accepted source paths and blobs resolve" `
        -Status "FAIL" `
        -Diagnostic (
            $SourceIdentityFailures -join "; "
        )
}

Write-C13Section -Title "COMPONENT ALIGNMENT"

$SourceComponents = @(
    $SourceContract.components
)

$TargetComponents = @(
    $Contract.components
)

$SourceComponentById = @{}
$TargetComponentById = @{}
$ComponentAlignmentFailures = @()

foreach ($Component in $SourceComponents) {
    $Id = [string]$Component.id

    if ($SourceComponentById.ContainsKey($Id)) {
        $ComponentAlignmentFailures +=
            "duplicate source component id '$Id'"
    }
    else {
        $SourceComponentById[$Id] = $Component
    }
}

foreach ($Component in $TargetComponents) {
    $Id = [string]$Component.id

    if ($TargetComponentById.ContainsKey($Id)) {
        $ComponentAlignmentFailures +=
            "duplicate C1.3 component id '$Id'"
    }
    else {
        $TargetComponentById[$Id] = $Component
    }
}

$SourceComponentIds =
    Get-C13UniqueSortedStrings `
        -Values @($SourceComponentById.Keys)

$TargetComponentIds =
    Get-C13UniqueSortedStrings `
        -Values @($TargetComponentById.Keys)

$ComponentIdDifference = @(
    Compare-Object `
        -ReferenceObject $SourceComponentIds `
        -DifferenceObject $TargetComponentIds
)

if ($ComponentIdDifference.Count -ne 0) {
    $ComponentAlignmentFailures +=
        "component identifier sets differ"
}

$ExpectedLayerRanks = [ordered]@{
    "composition-root"                    = 0
    "product-application"                 = 1
    "product-services"                    = 2
    "platform-services"                   = 3
    "hardware-abstraction-device-drivers" = 4
    "hardware-abstraction-generic-hal"    = 5
    "board-and-hardware-foundation"       = 6
    "controlled-cross-cutting-leaf"       = 7
}

foreach ($SourceId in $SourceComponentIds) {
    if (
        -not $TargetComponentById.ContainsKey(
            $SourceId
        )
    ) {
        continue
    }

    $SourceComponent =
        $SourceComponentById[$SourceId]

    $TargetComponent =
        $TargetComponentById[$SourceId]

    if ($TargetComponent.path -ne $SourceComponent.path) {
        $ComponentAlignmentFailures +=
            "$SourceId path differs from accepted C1.2"
    }

    if ($TargetComponent.layer -ne $SourceComponent.layer) {
        $ComponentAlignmentFailures +=
            "$SourceId layer differs from accepted C1.2"
    }

    if (
        -not $ExpectedLayerRanks.Contains(
            [string]$TargetComponent.layer
        )
    ) {
        $ComponentAlignmentFailures +=
            "$SourceId uses unknown layer '$($TargetComponent.layer)'"
    }
    elseif (
        [int]$TargetComponent.layer_rank -ne
        [int]$ExpectedLayerRanks[
            [string]$TargetComponent.layer
        ]
    ) {
        $ComponentAlignmentFailures +=
            "$SourceId has incorrect layer_rank"
    }

    if (
        $TargetComponent.implementation_status -ne
        $SourceComponent.implementation_status
    ) {
        $ComponentAlignmentFailures +=
            "$SourceId implementation_status differs from accepted C1.2"
    }

    if (
        $TargetComponent.api_namespace -ne
        $SourceComponent.api_namespace
    ) {
        $ComponentAlignmentFailures +=
            "$SourceId API namespace differs from accepted C1.2"
    }

    if (
        $TargetComponent.execution_model -ne
        $SourceComponent.execution_model
    ) {
        $ComponentAlignmentFailures +=
            "$SourceId execution model differs from accepted C1.2"
    }

    if (
        (
            Get-C13ArraySignature `
                -Values @($TargetComponent.owns)
        ) -ne
        (
            Get-C13ArraySignature `
                -Values @(
                    $SourceComponent.owned_resource_ids
                )
        )
    ) {
        $ComponentAlignmentFailures +=
            "$SourceId ownership list differs from accepted C1.2"
    }

    if (
        (
            Get-C13ArraySignature `
                -Values @(
                    $TargetComponent.permitted_dependencies
                )
        ) -ne
        (
            Get-C13ArraySignature `
                -Values @(
                    $SourceComponent.permitted_dependencies
                )
        )
    ) {
        $ComponentAlignmentFailures +=
            "$SourceId dependency allowlist differs from accepted C1.2"
    }
}

if ($ComponentAlignmentFailures.Count -eq 0) {
    Add-C13Check `
        -Category "Alignment" `
        -Check "C1.3 components exactly match accepted C1.2" `
        -Status "PASS"
}
else {
    Add-C13Check `
        -Category "Alignment" `
        -Check "C1.3 components exactly match accepted C1.2" `
        -Status "FAIL" `
        -Diagnostic (
            $ComponentAlignmentFailures -join "; "
        )
}

Write-C13Section -Title "DEPENDENCY TARGETS"

$UnknownDependencyTargets = @()

foreach ($Component in $TargetComponents) {
    foreach (
        $Dependency in @(
            $Component.permitted_dependencies
        )
    ) {
        if (
            -not $TargetComponentById.ContainsKey(
                [string]$Dependency
            )
        ) {
            $UnknownDependencyTargets +=
                "$($Component.id) -> $Dependency"
        }
    }
}

if ($UnknownDependencyTargets.Count -eq 0) {
    Add-C13Check `
        -Category "Graph" `
        -Check "all dependency targets resolve" `
        -Status "PASS"
}
else {
    Add-C13Check `
        -Category "Graph" `
        -Check "all dependency targets resolve" `
        -Status "FAIL" `
        -Diagnostic (
            $UnknownDependencyTargets -join "; "
        )
}

Write-C13Section -Title "DEPENDENCY CYCLES"

$InDegree = @{}
$Adjacency = @{}

foreach ($ComponentId in $TargetComponentIds) {
    $InDegree[$ComponentId] = 0
    $Adjacency[$ComponentId] = @()
}

foreach ($Component in $TargetComponents) {
    $SourceId = [string]$Component.id

    foreach (
        $Dependency in @(
            $Component.permitted_dependencies
        )
    ) {
        $TargetId = [string]$Dependency

        if (-not $InDegree.ContainsKey($TargetId)) {
            continue
        }

        $Adjacency[$SourceId] += $TargetId

        $InDegree[$TargetId] =
            [int]$InDegree[$TargetId] + 1
    }
}

$ZeroInDegree =
    New-Object System.Collections.Generic.Queue[string]

foreach ($ComponentId in $TargetComponentIds) {
    if ([int]$InDegree[$ComponentId] -eq 0) {
        $ZeroInDegree.Enqueue($ComponentId)
    }
}

$VisitedCount = 0

while ($ZeroInDegree.Count -gt 0) {
    $CurrentId = $ZeroInDegree.Dequeue()
    $VisitedCount++

    foreach ($TargetId in @($Adjacency[$CurrentId])) {
        $InDegree[$TargetId] =
            [int]$InDegree[$TargetId] - 1

        if ([int]$InDegree[$TargetId] -eq 0) {
            $ZeroInDegree.Enqueue($TargetId)
        }
    }
}

if ($VisitedCount -eq $TargetComponentIds.Count) {
    Add-C13Check `
        -Category "Graph" `
        -Check "complete permitted-dependency graph is acyclic" `
        -Status "PASS"
}
else {
    $CycleMembers = @(
        $TargetComponentIds |
            Where-Object {
                [int]$InDegree[$_] -gt 0
            }
    )

    Add-C13Check `
        -Category "Graph" `
        -Check "complete permitted-dependency graph is acyclic" `
        -Status "FAIL" `
        -Diagnostic (
            "cycle members: " +
            ($CycleMembers -join ", ")
        )
}

Write-C13Section -Title "DEPENDENCY DIRECTION"

$DirectionViolations = @()
$SameLevelEdges = @()

foreach ($Component in $TargetComponents) {
    $SourceId = [string]$Component.id
    $SourceRank = [int]$Component.layer_rank

    foreach (
        $Dependency in @(
            $Component.permitted_dependencies
        )
    ) {
        $TargetId = [string]$Dependency

        if (
            -not $TargetComponentById.ContainsKey(
                $TargetId
            )
        ) {
            continue
        }

        $TargetRank = [int](
            $TargetComponentById[$TargetId].layer_rank
        )

        if ($TargetRank -lt $SourceRank) {
            $DirectionViolations +=
                "$SourceId($SourceRank) -> $TargetId($TargetRank)"
        }
        elseif ($TargetRank -eq $SourceRank) {
            $SameLevelEdges +=
                "$SourceId -> $TargetId"
        }
    }
}

if ($DirectionViolations.Count -eq 0) {
    Add-C13Check `
        -Category "Direction" `
        -Check "all dependencies point to a larger layer rank" `
        -Status "PASS"
}
else {
    Add-C13Check `
        -Category "Direction" `
        -Check "all dependencies point to a larger layer rank" `
        -Status "FAIL" `
        -Diagnostic (
            $DirectionViolations -join "; "
        )
}

$SourceSameLevel = @(
    $SourceContract.approved_same_level_dependencies
)

$TargetSameLevel = @(
    $Contract.approved_same_level_dependencies
)

$SameLevelFailures = @()

if ($SourceSameLevel.Count -ne 0) {
    $SameLevelFailures +=
        "accepted C1.2 unexpectedly contains same-level approvals"
}

if ($TargetSameLevel.Count -ne 0) {
    $SameLevelFailures +=
        "C1.3 unexpectedly contains same-level approvals"
}

if ($SameLevelEdges.Count -ne 0) {
    $SameLevelFailures += (
        "same-level graph edges exist: " +
        ($SameLevelEdges -join ", ")
    )
}

if (@($Contract.architecture_decisions).Count -ne 0) {
    $SameLevelFailures +=
        "architecture_decisions must be empty for the current baseline"
}

if ($SameLevelFailures.Count -eq 0) {
    Add-C13Check `
        -Category "Direction" `
        -Check "same-level dependencies and decisions are absent" `
        -Status "PASS"
}
else {
    Add-C13Check `
        -Category "Direction" `
        -Check "same-level dependencies and decisions are absent" `
        -Status "FAIL" `
        -Diagnostic (
            $SameLevelFailures -join "; "
        )
}

Write-C13Section -Title "MUTABLE-RESOURCE OWNERSHIP"

$SourceResources = @(
    $SourceContract.mutable_resources
)

$TargetResources = @(
    $Contract.mutable_resources
)

$SourceResourceById = @{}
$TargetResourceById = @{}
$OwnershipFailures = @()

foreach ($Resource in $SourceResources) {
    $Id = [string]$Resource.id

    if ($SourceResourceById.ContainsKey($Id)) {
        $OwnershipFailures +=
            "duplicate source resource id '$Id'"
    }
    else {
        $SourceResourceById[$Id] = $Resource
    }
}

foreach ($Resource in $TargetResources) {
    $Id = [string]$Resource.id

    if ($TargetResourceById.ContainsKey($Id)) {
        $OwnershipFailures +=
            "duplicate C1.3 resource id '$Id'"
    }
    else {
        $TargetResourceById[$Id] = $Resource
    }
}

$SourceResourceIds =
    Get-C13UniqueSortedStrings `
        -Values @($SourceResourceById.Keys)

$TargetResourceIds =
    Get-C13UniqueSortedStrings `
        -Values @($TargetResourceById.Keys)

$ResourceIdDifference = @(
    Compare-Object `
        -ReferenceObject $SourceResourceIds `
        -DifferenceObject $TargetResourceIds
)

if ($ResourceIdDifference.Count -ne 0) {
    $OwnershipFailures +=
        "mutable-resource identifier sets differ"
}

foreach ($ResourceId in $SourceResourceIds) {
    if (
        -not $TargetResourceById.ContainsKey(
            $ResourceId
        )
    ) {
        continue
    }

    $SourceResource =
        $SourceResourceById[$ResourceId]

    $TargetResource =
        $TargetResourceById[$ResourceId]

    if (
        $TargetResource.owner -ne
        $SourceResource.owner
    ) {
        $OwnershipFailures +=
            "$ResourceId owner differs from accepted C1.2"
    }

    if (
        $TargetResource.description -ne
        $SourceResource.description
    ) {
        $OwnershipFailures +=
            "$ResourceId description differs from accepted C1.2"
    }

    if (
        -not $TargetComponentById.ContainsKey(
            [string]$TargetResource.owner
        )
    ) {
        $OwnershipFailures += (
            "$ResourceId names unknown owner " +
            "'$($TargetResource.owner)'"
        )
    }
}

$ClaimsByResource = @{}

foreach ($Component in $TargetComponents) {
    foreach ($ResourceIdValue in @($Component.owns)) {
        $ResourceId = [string]$ResourceIdValue

        if (
            -not $ClaimsByResource.ContainsKey(
                $ResourceId
            )
        ) {
            $ClaimsByResource[$ResourceId] = @()
        }

        $ClaimsByResource[$ResourceId] +=
            [string]$Component.id

        if (
            -not $TargetResourceById.ContainsKey(
                $ResourceId
            )
        ) {
            $OwnershipFailures += (
                "$($Component.id) claims unknown " +
                "resource '$ResourceId'"
            )
        }
    }
}

foreach ($ResourceId in $TargetResourceIds) {
    $Claims = @(
        $ClaimsByResource[$ResourceId]
    )

    if ($Claims.Count -ne 1) {
        $OwnershipFailures += (
            "$ResourceId has $($Claims.Count) " +
            "component ownership claims"
        )

        continue
    }

    if (
        $Claims[0] -ne
        $TargetResourceById[$ResourceId].owner
    ) {
        $OwnershipFailures += (
            "$ResourceId claim '$($Claims[0])' " +
            "differs from owner " +
            "'$($TargetResourceById[$ResourceId].owner)'"
        )
    }
}

if ($OwnershipFailures.Count -eq 0) {
    Add-C13Check `
        -Category "Ownership" `
        -Check "every mutable resource has exactly one aligned owner" `
        -Status "PASS"
}
else {
    Add-C13Check `
        -Category "Ownership" `
        -Check "every mutable resource has exactly one aligned owner" `
        -Status "FAIL" `
        -Diagnostic (
            $OwnershipFailures -join "; "
        )
}

Write-C13Section `
    -Title "IMPLEMENTATION STATUS AND PATHS"

$PathFailures = @()

foreach ($Component in $TargetComponents) {
    $ComponentPath = [string]$Component.path

    $FullComponentPath =
        Resolve-C13Path `
            -RelativePath $ComponentPath

    $Exists =
        Test-Path -LiteralPath $FullComponentPath

    $ImplementationStatus =
        [string]$Component.implementation_status

    if ($ImplementationStatus -eq "planned") {
        continue
    }

    if (-not $Exists) {
        $PathFailures += (
            "$($Component.id) is '$ImplementationStatus' " +
            "but path is missing: $ComponentPath"
        )
    }
}

if ($PathFailures.Count -eq 0) {
    Add-C13Check `
        -Category "Paths" `
        -Check "existing component paths resolve and planned paths remain declared" `
        -Status "PASS"
}
else {
    Add-C13Check `
        -Category "Paths" `
        -Check "existing component paths resolve and planned paths remain declared" `
        -Status "FAIL" `
        -Diagnostic (
            $PathFailures -join "; "
        )
}

Write-C13Section `
    -Title "OBSOLETE AND REJECTED CANDIDATES"

$CandidateFailures = @()

$TargetIds = @(
    $TargetComponents |
        ForEach-Object {
            [string]$_.id
        }
)

if ("bsp" -in $TargetIds) {
    $CandidateFailures +=
        "obsolete component identifier 'bsp' remains"
}

$RejectedCandidatePaths = @(
    "docs/phase-c/ADR-0001-diagnostics-lateral-dependencies.md",
    "docs/phase-c/ADR-0002-hal-platform-shared-layer.md",
    "verification/c1_3_architecture/C1.3_verification_result_20260726_143352.json"
)

foreach (
    $RejectedCandidatePath in
    $RejectedCandidatePaths
) {
    $FullRejectedCandidatePath =
        Resolve-C13Path `
            -RelativePath $RejectedCandidatePath

    if (
        Test-Path `
            -LiteralPath $FullRejectedCandidatePath
    ) {
        $CandidateFailures +=
            "rejected candidate remains: $RejectedCandidatePath"
    }
}

if (
    @(
        $Contract.rejected_recovered_candidates
    ).Count -ne 2
) {
    $CandidateFailures +=
        "rejected_recovered_candidates must contain exactly two records"
}

if ($CandidateFailures.Count -eq 0) {
    Add-C13Check `
        -Category "Candidates" `
        -Check "obsolete BSP and rejected candidate artifacts are absent" `
        -Status "PASS"
}
else {
    Add-C13Check `
        -Category "Candidates" `
        -Check "obsolete BSP and rejected candidate artifacts are absent" `
        -Status "FAIL" `
        -Diagnostic (
            $CandidateFailures -join "; "
        )
}

Write-C13Section -Title "REVIEW-DOCUMENT STATE"

$DocumentFailures = @()

if ($Contract.status -eq "Draft") {
    if (
        $ReviewDocument -notmatch
        '(?m)^status: "In Progress"$'
    ) {
        $DocumentFailures +=
            "Draft contract requires In Progress review-document status"
    }

    if (
        $ReviewDocument -notmatch
        'Cluster C1 gate: NOT ACCEPTED'
    ) {
        $DocumentFailures +=
            "Draft review document must keep Cluster C1 gate not accepted"
    }
}

if ($Contract.status -eq "Accepted") {
    if (
        $ReviewDocument -notmatch
        '(?m)^status: "Accepted"$'
    ) {
        $DocumentFailures +=
            "Accepted contract requires Accepted review-document status"
    }
}

if ($DocumentFailures.Count -eq 0) {
    Add-C13Check `
        -Category "Document" `
        -Check "review-document state matches contract state" `
        -Status "PASS"
}
else {
    Add-C13Check `
        -Category "Document" `
        -Check "review-document state matches contract state" `
        -Status "FAIL" `
        -Diagnostic (
            $DocumentFailures -join "; "
        )
}

Write-C13Section -Title "WRITE VERIFICATION EVIDENCE"

$FailedChecks = @(
    $script:C13Checks |
        Where-Object {
            $_.Status -eq "FAIL"
        }
)

$Timestamp =
    Get-Date -Format "yyyyMMdd_HHmmss"

$EvidenceDirectory =
    Resolve-C13Path `
        -RelativePath "verification/c1_3_architecture"

New-Item `
    -ItemType Directory `
    -Path $EvidenceDirectory `
    -Force |
    Out-Null

$ResultFileName =
    "C1.3_verification_result_${Timestamp}.json"

$ResultPath = Join-Path `
    $EvidenceDirectory `
    $ResultFileName

$ContractSha256 = (
    Get-FileHash `
        -Algorithm SHA256 `
        -LiteralPath $FullContractPath
).Hash

$SourceContractBlob =
    Get-C13TrackedBlob `
        -RelativePath $SourceContractPath

$Evidence = [PSCustomObject][ordered]@{
    Timestamp          = $Timestamp
    WorkPackage        = "C1.3"
    Gate               = "G-C"
    ContractPath       = $ContractPath
    ContractSha256     = $ContractSha256
    SourceContractPath = $SourceContractPath
    SourceContractBlob = $SourceContractBlob
    ReviewDocumentPath = $ReviewDocumentPath
    Checks             = $script:C13Checks.ToArray()
    OverallResult      = $(
        if ($FailedChecks.Count -eq 0) {
            "PASS"
        }
        else {
            "FAIL"
        }
    )
}

$EvidenceJson = (
    $Evidence |
        ConvertTo-Json -Depth 12
).TrimEnd().
    Replace("`r`n", "`n").
    Replace("`r", "`n") +
    "`n"

$Utf8NoBom =
    New-Object System.Text.UTF8Encoding($false)

[System.IO.File]::WriteAllText(
    $ResultPath,
    $EvidenceJson,
    $Utf8NoBom
)

Write-Host "Evidence written to: $ResultPath"
Write-Host "Checks:              $($script:C13Checks.Count)"
Write-Host "Failed checks:       $($FailedChecks.Count)"
Write-Host "Overall result:      $($Evidence.OverallResult)"

if ($FailedChecks.Count -ne 0) {
    throw (
        "C1.3 architecture verification failed with " +
        "$($FailedChecks.Count) failed check(s)."
    )
}

Write-Host ""
Write-Host "C1.3 architecture contract: PASS"
