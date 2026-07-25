[CmdletBinding()]
param(
    [ValidateSet("debug", "validation", "production")]
    [string]$Profile = "debug",

    [string]$RepoRoot = (
        Resolve-Path (
            Join-Path $PSScriptRoot "..\.."
        )
    ).Path,

    [string]$IdfPath = $env:IDF_PATH,

    [string]$HardwareCompatibility = "heltec-wifi-lora-32-v3",

    [switch]$ContractOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$B32CompatibilityBranch = "feat/b3.2-controlled-tooling"

$RequiredProfiles = @(
    "debug"
    "validation"
    "production"
)

function Invoke-B41Git {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory)]
        [string[]]$Arguments,

        [switch]$AllowExitCodeOne
    )

    $GitCommand = Get-Command `
        git.exe `
        -ErrorAction SilentlyContinue

    if ($null -eq $GitCommand) {
        $GitCommand = Get-Command `
            git `
            -ErrorAction Stop
    }

    $Output = @(
        & $GitCommand.Source `
            -C $WorkingDirectory `
            @Arguments `
            2>&1
    )

    $ExitCode = $LASTEXITCODE
    $Text = ($Output -join [Environment]::NewLine).Trim()

    if (
        $ExitCode -ne 0 -and
        -not (
            $AllowExitCodeOne -and
            $ExitCode -eq 1
        )
    ) {
        throw @"
Git command failed.

Working directory: $WorkingDirectory
Exit code:        $ExitCode
Command:          git $($Arguments -join ' ')
Output:
$Text
"@
    }

    [PSCustomObject]@{
        ExitCode = $ExitCode
        Text = $Text
        Lines = @($Output)
    }
}

function Get-B41PowerShellAst {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    $Tokens = $null
    $ParseErrors = $null

    $Ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $Path,
        [ref]$Tokens,
        [ref]$ParseErrors
    )

    if ($ParseErrors.Count -ne 0) {
        $FailureText = @(
            $ParseErrors |
                ForEach-Object {
                    "$($_.Extent.File):" +
                    "$($_.Extent.StartLineNumber): " +
                    "$($_.Message)"
                }
        ) -join [Environment]::NewLine

        throw "PowerShell parsing failed:`n$FailureText"
    }

    $Ast
}

function Assert-B41Repository {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if (
        -not (
            Test-Path `
                -LiteralPath $Path `
                -PathType Container
        )
    ) {
        throw "Repository directory does not exist: $Path"
    }

    $ResolvedPath = (
        Resolve-Path `
            -LiteralPath $Path `
            -ErrorAction Stop
    ).Path

    $GitRootResult = Invoke-B41Git `
        -WorkingDirectory $ResolvedPath `
        -Arguments @(
            "rev-parse"
            "--show-toplevel"
        )

    $GitRoot = (
        Resolve-Path `
            -LiteralPath $GitRootResult.Text `
            -ErrorAction Stop
    ).Path

    if (
        -not [string]::Equals(
            $ResolvedPath,
            $GitRoot,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw (
            "Selected repository does not match the Git root: " +
            "selected='$ResolvedPath', git='$GitRoot'."
        )
    }

    $ResolvedPath
}

function Assert-B41TrackedTreeClean {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$RepositoryRoot
    )

    $StatusResult = Invoke-B41Git `
        -WorkingDirectory $RepositoryRoot `
        -Arguments @(
            "status"
            "--porcelain"
            "--untracked-files=no"
        )

    if (
        -not [string]::IsNullOrWhiteSpace(
            $StatusResult.Text
        )
    ) {
        throw (
            "Tracked repository files are not clean:`n" +
            $StatusResult.Text
        )
    }
}

function Assert-B41B32Contract {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$RepositoryRoot
    )

    $BuildScriptPath = Join-Path `
        $RepositoryRoot `
        "tools\scripts\B3.2_Build.ps1"

    $CommonScriptPath = Join-Path `
        $RepositoryRoot `
        "tools\scripts\B3.2_Common.ps1"

    foreach ($RequiredFile in @(
        $BuildScriptPath
        $CommonScriptPath
    )) {
        if (
            -not (
                Test-Path `
                    -LiteralPath $RequiredFile `
                    -PathType Leaf
            )
        ) {
            throw "Required B3.2 file is missing: $RequiredFile"
        }

        Get-B41PowerShellAst `
            -Path $RequiredFile |
            Out-Null
    }

    $CommonAst = Get-B41PowerShellAst `
        -Path $CommonScriptPath

    $FunctionDefinitions = @(
        $CommonAst.FindAll(
            {
                param($Node)

                $Node.GetType().FullName -eq `
                    "System.Management.Automation.Language.FunctionDefinitionAst"
            },
            $true
        )
    )

    $RequiredFunctions = @(
        "Assert-B32FeatureBranch"
        "Assert-B32TrackedTreeClean"
        "Get-B32BuildLayout"
        "Get-B32ProfileDefaults"
        "Assert-B32GeneratedConfiguration"
        "Get-B32ProjectArtifacts"
    )

    foreach ($RequiredFunctionName in $RequiredFunctions) {
        $Matches = @(
            $FunctionDefinitions |
                Where-Object {
                    $_.Name -eq $RequiredFunctionName
                }
        )

        if ($Matches.Count -ne 1) {
            throw (
                "Expected one B3.2 function named " +
                "'$RequiredFunctionName'; found $($Matches.Count)."
            )
        }
    }

    $BranchGuard = @(
        $FunctionDefinitions |
            Where-Object {
                $_.Name -eq "Assert-B32FeatureBranch"
            }
    )[0]

    if (
        -not $BranchGuard.Extent.Text.Contains(
            'feat/b3.2-controlled-tooling'
        )
    ) {
        throw (
            "B3.2 branch guard no longer contains the expected " +
            "compatibility branch."
        )
    }

    $BuildScriptRaw = [System.IO.File]::ReadAllText(
        $BuildScriptPath
    )

    foreach ($RequiredProfile in $RequiredProfiles) {
        if (
            -not $BuildScriptRaw.Contains(
                '"' + $RequiredProfile + '"'
            )
        ) {
            throw (
                "B3.2 build entry point does not contain profile " +
                "'$RequiredProfile'."
            )
        }
    }

    $RequiredBuildCalls = @(
        "Assert-B32FeatureBranch"
        "Assert-B32TrackedTreeClean"
        "Get-B32ProfileDefaults"
        "Get-B32BuildLayout"
        "Assert-B32GeneratedConfiguration"
        "Get-B32ProjectArtifacts"
    )

    foreach ($RequiredBuildCall in $RequiredBuildCalls) {
        if (
            -not $BuildScriptRaw.Contains(
                $RequiredBuildCall
            )
        ) {
            throw (
                "B3.2 build entry point no longer invokes " +
                "'$RequiredBuildCall'."
            )
        }
    }

    [PSCustomObject]@{
        BuildScript = $BuildScriptPath
        CommonScript = $CommonScriptPath
        CompatibilityBranch = $B32CompatibilityBranch
        Profiles = @($RequiredProfiles)
    }
}

function Copy-B41DirectoryIfPresent {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Source,

        [Parameter(Mandatory)]
        [string]$Destination
    )

    if (
        -not (
            Test-Path `
                -LiteralPath $Source `
                -PathType Container
        )
    ) {
        return
    }

    if (
        Test-Path `
            -LiteralPath $Destination
    ) {
        Remove-Item `
            -LiteralPath $Destination `
            -Recurse `
            -Force
    }

    New-Item `
        -ItemType Directory `
        -Path (Split-Path -Parent $Destination) `
        -Force |
        Out-Null

    Copy-Item `
        -LiteralPath $Source `
        -Destination $Destination `
        -Recurse `
        -Force
}

function Copy-B41FileIfPresent {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Source,

        [Parameter(Mandatory)]
        [string]$DestinationDirectory
    )

    if (
        -not (
            Test-Path `
                -LiteralPath $Source `
                -PathType Leaf
        )
    ) {
        return
    }

    New-Item `
        -ItemType Directory `
        -Path $DestinationDirectory `
        -Force |
        Out-Null

    Copy-Item `
        -LiteralPath $Source `
        -Destination $DestinationDirectory `
        -Force
}

function Copy-B41BuildEvidence {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$WorktreeRoot,

        [Parameter(Mandatory)]
        [string]$OriginalRepositoryRoot,

        [Parameter(Mandatory)]
        [string]$ProfileName
    )

    $ArtifactRoot = Join-Path `
        $OriginalRepositoryRoot `
        "artifacts\b4.1\profile-build\$ProfileName"

    New-Item `
        -ItemType Directory `
        -Path $ArtifactRoot `
        -Force |
        Out-Null

    $EvidenceSource = Join-Path `
        $WorktreeRoot `
        "docs\evidence\logs\B3.2"

    $EvidenceDestination = Join-Path `
        $ArtifactRoot `
        "evidence"

    Copy-B41DirectoryIfPresent `
        -Source $EvidenceSource `
        -Destination $EvidenceDestination

    $BuildSource = Join-Path `
        $WorktreeRoot `
        "build\b3.2\$ProfileName"

    $BuildDestination = Join-Path `
        $ArtifactRoot `
        "build"

    New-Item `
        -ItemType Directory `
        -Path $BuildDestination `
        -Force |
        Out-Null

    $ProjectDescriptionPath = Join-Path `
        $BuildSource `
        "project_description.json"

    $ProjectName = "sqd_firmware"

    if (
        Test-Path `
            -LiteralPath $ProjectDescriptionPath `
            -PathType Leaf
    ) {
        try {
            $ProjectDescription = (
                Get-Content `
                    -LiteralPath $ProjectDescriptionPath `
                    -Raw |
                ConvertFrom-Json
            )

            if (
                -not [string]::IsNullOrWhiteSpace(
                    [string]$ProjectDescription.project_name
                )
            ) {
                $ProjectName = [string]$ProjectDescription.project_name
            }
        }
        catch {
            Write-Warning (
                "Unable to parse project_description.json while " +
                "copying evidence: $($_.Exception.Message)"
            )
        }
    }

    $BuildFiles = @(
        "compile_commands.json"
        "sdkconfig"
        "project_description.json"
        "flasher_args.json"
        "$ProjectName.bin"
        "$ProjectName.elf"
        "$ProjectName.map"
    )

    foreach ($BuildFileName in $BuildFiles) {
        Copy-B41FileIfPresent `
            -Source (
                Join-Path `
                    $BuildSource `
                    $BuildFileName
            ) `
            -DestinationDirectory $BuildDestination
    }

    Copy-B41FileIfPresent `
        -Source (
            Join-Path `
                $BuildSource `
                "bootloader\bootloader.bin"
        ) `
        -DestinationDirectory (
            Join-Path `
                $BuildDestination `
                "bootloader"
        )

    Copy-B41FileIfPresent `
        -Source (
            Join-Path `
                $BuildSource `
                "partition_table\partition-table.bin"
        ) `
        -DestinationDirectory (
            Join-Path `
                $BuildDestination `
                "partition_table"
        )

    $ArtifactRoot
}

$ResolvedRepoRoot = Assert-B41Repository `
    -Path $RepoRoot

$Contract = Assert-B41B32Contract `
    -RepositoryRoot $ResolvedRepoRoot

Write-Host "B4.1 profile-build wrapper"
Write-Host "Repository:           $ResolvedRepoRoot"
Write-Host "Profile:              $Profile"
Write-Host "B3.2 build entry:     $($Contract.BuildScript)"
Write-Host "Compatibility branch: $($Contract.CompatibilityBranch)"
Write-Host (
    "Controlled profiles:  " +
    ($Contract.Profiles -join ",")
)

if ($ContractOnly) {
    Write-Host ""
    Write-Host "PowerShell parsing: PASS"
    Write-Host "B3.2 required functions: PASS"
    Write-Host "B3.2 profile contract: PASS"
    Write-Host "B3.2 build-stage calls: PASS"
    Write-Host ""
    Write-Host (
        "PASS: B4.1 profile-build wrapper contract validated."
    )

    return
}

if ([string]::IsNullOrWhiteSpace($IdfPath)) {
    throw (
        "IdfPath is required for profile-build execution. " +
        "Supply -IdfPath or activate ESP-IDF first."
    )
}

$ResolvedIdfPath = (
    Resolve-Path `
        -LiteralPath $IdfPath `
        -ErrorAction Stop
).Path

$IdfExportPath = Join-Path `
    $ResolvedIdfPath `
    "export.ps1"

if (
    -not (
        Test-Path `
            -LiteralPath $IdfExportPath `
            -PathType Leaf
    )
) {
    throw "ESP-IDF export script is missing: $IdfExportPath"
}

Assert-B41TrackedTreeClean `
    -RepositoryRoot $ResolvedRepoRoot

$Commit = (
    Invoke-B41Git `
        -WorkingDirectory $ResolvedRepoRoot `
        -Arguments @(
            "rev-parse"
            "HEAD"
        )
).Text

if ($Commit -notmatch '^[0-9a-fA-F]{40}$') {
    throw "Unable to resolve a full source commit: '$Commit'"
}

$ExistingCompatibilityBranch = Invoke-B41Git `
    -WorkingDirectory $ResolvedRepoRoot `
    -Arguments @(
        "show-ref"
        "--verify"
        "--quiet"
        "refs/heads/$B32CompatibilityBranch"
    ) `
    -AllowExitCodeOne

if ($ExistingCompatibilityBranch.ExitCode -eq 0) {
    throw (
        "Local compatibility branch already exists: " +
        "$B32CompatibilityBranch"
    )
}

$TemporaryBase = if (
    -not [string]::IsNullOrWhiteSpace(
        $env:RUNNER_TEMP
    )
) {
    $env:RUNNER_TEMP
}
else {
    [System.IO.Path]::GetTempPath()
}

$WorktreeRoot = Join-Path `
    $TemporaryBase `
    (
        "sqd-b4.1-" +
        $Profile +
        "-" +
        [System.Guid]::NewGuid().ToString("N")
    )

$ArtifactRoot = Join-Path `
    $ResolvedRepoRoot `
    "artifacts\b4.1\profile-build\$Profile"

$WorktreeCreated = $false
$CompatibilityBranchCreated = $false
$BuildPassed = $false

try {
    if (
        Test-Path `
            -LiteralPath $ArtifactRoot
    ) {
        Remove-Item `
            -LiteralPath $ArtifactRoot `
            -Recurse `
            -Force
    }

    Write-Host ""
    Write-Host "=== Create isolated compatibility worktree ==="

    $WorktreeResult = Invoke-B41Git `
        -WorkingDirectory $ResolvedRepoRoot `
        -Arguments @(
            "worktree"
            "add"
            "--force"
            "-b"
            $B32CompatibilityBranch
            $WorktreeRoot
            $Commit
        )

    $WorktreeCreated = $true
    $CompatibilityBranchCreated = $true

    if (
        -not [string]::IsNullOrWhiteSpace(
            $WorktreeResult.Text
        )
    ) {
        Write-Host $WorktreeResult.Text
    }

    $WorktreeBranch = (
        Invoke-B41Git `
            -WorkingDirectory $WorktreeRoot `
            -Arguments @(
                "branch"
                "--show-current"
            )
    ).Text

    if ($WorktreeBranch -ne $B32CompatibilityBranch) {
        throw (
            "Temporary worktree has incorrect branch identity: " +
            "'$WorktreeBranch'."
        )
    }

    $WorktreeCommit = (
        Invoke-B41Git `
            -WorkingDirectory $WorktreeRoot `
            -Arguments @(
                "rev-parse"
                "HEAD"
            )
    ).Text

    if ($WorktreeCommit -ne $Commit) {
        throw (
            "Temporary worktree commit mismatch: " +
            "expected='$Commit', actual='$WorktreeCommit'."
        )
    }

    Write-Host "Worktree: $WorktreeRoot"
    Write-Host "Branch:   $WorktreeBranch"
    Write-Host "Commit:   $WorktreeCommit"

    Write-Host ""
    Write-Host "=== Execute unchanged B3.2 controlled build ==="

    $WorktreeBuildScript = Join-Path `
        $WorktreeRoot `
        "tools\scripts\B3.2_Build.ps1"

    & $WorktreeBuildScript `
        -Profile $Profile `
        -RepoRoot $WorktreeRoot `
        -IdfPath $ResolvedIdfPath `
        -HardwareCompatibility $HardwareCompatibility

    if ($LASTEXITCODE -ne 0) {
        throw (
            "B3.2 controlled build returned exit code " +
            "$LASTEXITCODE."
        )
    }

    $EvidenceDirectory = Join-Path `
        $WorktreeRoot `
        "docs\evidence\logs\B3.2"

    $ResultFile = Get-ChildItem `
        -LiteralPath $EvidenceDirectory `
        -Filter "B3.2_${Profile}_build_result_*.json" `
        -File `
        -ErrorAction Stop |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1

    if ($null -eq $ResultFile) {
        throw "B3.2 build result JSON was not produced."
    }

    $BuildResult = (
        Get-Content `
            -LiteralPath $ResultFile.FullName `
            -Raw |
        ConvertFrom-Json
    )

    if ([string]$BuildResult.status -ne "PASS") {
        throw "B3.2 build result status is not PASS."
    }

    if ([string]$BuildResult.profile -ne $Profile) {
        throw (
            "B3.2 build result profile mismatch: " +
            "'$($BuildResult.profile)'."
        )
    }

    if (
        [string]$BuildResult.repository.commit -ne
        $Commit
    ) {
        throw (
            "B3.2 build result commit mismatch: " +
            "'$($BuildResult.repository.commit)'."
        )
    }

    $CompileCommandsPath = Join-Path `
        $WorktreeRoot `
        "build\b3.2\$Profile\compile_commands.json"

    if (
        -not (
            Test-Path `
                -LiteralPath $CompileCommandsPath `
                -PathType Leaf
        )
    ) {
        throw (
            "Profile build did not produce " +
            "compile_commands.json."
        )
    }

    $BuildPassed = $true

    Write-Host ""
    Write-Host "=== Copy profile artifacts and evidence ==="

    $ArtifactRoot = Copy-B41BuildEvidence `
        -WorktreeRoot $WorktreeRoot `
        -OriginalRepositoryRoot $ResolvedRepoRoot `
        -ProfileName $Profile

    $Provenance = [ordered]@{
        schema_version = 1
        work_package = "B4.1"
        operation = "profile-build-wrapper"
        status = "PASS"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        profile = $Profile
        source = [ordered]@{
            repository = $ResolvedRepoRoot
            commit = $Commit
            github_actions = $env:GITHUB_ACTIONS
            github_event_name = $env:GITHUB_EVENT_NAME
            github_ref = $env:GITHUB_REF
            github_head_ref = $env:GITHUB_HEAD_REF
            github_base_ref = $env:GITHUB_BASE_REF
            github_sha = $env:GITHUB_SHA
        }
        compatibility = [ordered]@{
            branch = $B32CompatibilityBranch
            worktree = $WorktreeRoot
            b32_result = $ResultFile.FullName
        }
        toolchain = [ordered]@{
            idf_path = $ResolvedIdfPath
            hardware_compatibility = $HardwareCompatibility
        }
        artifact_root = $ArtifactRoot
    }

    $ProvenancePath = Join-Path `
        $ArtifactRoot `
        "B4.1_profile_build_provenance.json"

    $Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

    [System.IO.File]::WriteAllText(
        $ProvenancePath,
        (
            $Provenance |
                ConvertTo-Json -Depth 12
        ) + "`n",
        $Utf8NoBom
    )

    if (
        -not (
            Test-Path `
                -LiteralPath $ProvenancePath `
                -PathType Leaf
        )
    ) {
        throw "Profile-build provenance was not created."
    }

    if (
        -not [string]::IsNullOrWhiteSpace(
            $env:GITHUB_OUTPUT
        )
    ) {
        [System.IO.File]::AppendAllText(
            $env:GITHUB_OUTPUT,
            "artifact_root=$ArtifactRoot`n",
            $Utf8NoBom
        )
    }

    Write-Host "Artifact root: $ArtifactRoot"
    Write-Host "Provenance:    $ProvenancePath"
}
catch {
    Write-Host ""
    Write-Host "=== Preserve partial failure evidence ==="

    try {
        $ArtifactRoot = Copy-B41BuildEvidence `
            -WorktreeRoot $WorktreeRoot `
            -OriginalRepositoryRoot $ResolvedRepoRoot `
            -ProfileName $Profile

        Write-Host "Partial evidence: $ArtifactRoot"
    }
    catch {
        Write-Warning (
            "Unable to preserve partial build evidence: " +
            $_.Exception.Message
        )
    }

    throw
}
finally {
    Write-Host ""
    Write-Host "=== Remove isolated compatibility worktree ==="

    if ($WorktreeCreated) {
        try {
            Invoke-B41Git `
                -WorkingDirectory $ResolvedRepoRoot `
                -Arguments @(
                    "worktree"
                    "remove"
                    "--force"
                    $WorktreeRoot
                ) |
                Out-Null

            Write-Host "Worktree removed: $WorktreeRoot"
        }
        catch {
            Write-Warning (
                "Unable to remove temporary worktree: " +
                $_.Exception.Message
            )
        }
    }

    if ($CompatibilityBranchCreated) {
        try {
            Invoke-B41Git `
                -WorkingDirectory $ResolvedRepoRoot `
                -Arguments @(
                    "branch"
                    "--delete"
                    "--force"
                    $B32CompatibilityBranch
                ) |
                Out-Null

            Write-Host (
                "Compatibility branch removed: " +
                $B32CompatibilityBranch
            )
        }
        catch {
            Write-Warning (
                "Unable to remove compatibility branch: " +
                $_.Exception.Message
            )
        }
    }
}

if (-not $BuildPassed) {
    throw "B4.1 profile build did not reach PASS."
}

Write-Host ""
Write-Host (
    "PASS: B4.1 $Profile profile build completed " +
    "through the unchanged B3.2 contract."
)
