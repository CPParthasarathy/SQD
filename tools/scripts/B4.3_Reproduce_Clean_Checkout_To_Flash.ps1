[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$SourceCommit,

    [ValidateSet("debug", "validation")]
    [string]$Profile = "validation",

    [ValidatePattern('^COM\d+$')]
    [string]$Port,

    [ValidateRange(5, 300)]
    [int]$MonitorSeconds = 20,

    [ValidateSet(2)]
    [int]$PassCount = 2,

    [string]$RepositoryUrl = "https://github.com/CPParthasarathy/SQD.git",

    [string]$CleanroomRoot = "D:\SQD_Cleanroom\B4.3",

    [string]$EvidenceRoot = "D:\OneDrive\SQD_B4_3_Evidence",

    [string]$IdfPath = "D:\esp\v6.0.2\esp-idf",

    [switch]$ConfirmHardwareOperations,

    [switch]$KeepCleanrooms,

    [switch]$PlanOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:B43ParentBaseline = "196c46e5b90b568f8639a061e4dc5370db57c091"
$script:B43IdfCommit = "7101770dc6db2667b3c477cc31365dd1acd6db4e"
$script:B43IdfVersion = "v6.0.2"
$script:B43PythonVersion = "Python 3.11.15"
$script:B43Target = "esp32s3"
$script:B43HardwareCompatibility = "heltec-wifi-lora-32-v3.2-htit-wb32laf"
$script:B43CompatibilityBranch = "feat/b3.2-controlled-tooling"
$script:B43RequiredSerialMarkers = @(
    "B1.2 minimal firmware started",
    "Heartbeat:",
    "SQD_META schema=1"
)
$script:B43ForbiddenSerialPatterns = @(
    "Guru Meditation Error",
    "Brownout detector was triggered",
    "invalid header",
    "partition table error",
    "abort()"
)
$script:B43RequiredMetadataKeys = @(
    "product_version",
    "git_commit",
    "git_commit_short",
    "git_dirty",
    "source_timestamp_utc",
    "build_timestamp_utc",
    "build_profile",
    "target",
    "idf_version",
    "compiler_version",
    "hardware_compatibility",
    "secure_version",
    "elf_sha256"
)

function Write-B43Section {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Title
    )

    Write-Host ""
    Write-Host "============================================================"
    Write-Host $Title
    Write-Host "============================================================"
}

function Get-B43Timestamp {
    [CmdletBinding()]
    param()

    Get-Date -Format "yyyyMMdd_HHmmss"
}

function Assert-B43File {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Description file is missing: $Path"
    }

    (Resolve-Path -LiteralPath $Path).Path
}

function Assert-B43Directory {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Description directory is missing: $Path"
    }

    (Resolve-Path -LiteralPath $Path).Path
}

function New-B43Directory {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    (Resolve-Path -LiteralPath $Path).Path
}

function Write-B43TextFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Content,

        [Parameter(Mandatory)]
        [string]$Path
    )

    New-B43Directory -Path (Split-Path -Parent $Path) | Out-Null
    $Encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $Encoding)
    $Path
}

function Write-B43JsonFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$InputObject,

        [Parameter(Mandatory)]
        [string]$Path,

        [ValidateRange(2, 100)]
        [int]$Depth = 20
    )

    $Json = $InputObject | ConvertTo-Json -Depth $Depth
    Write-B43TextFile -Content ($Json + "`n") -Path $Path
}

function Get-B43GitExecutable {
    [CmdletBinding()]
    param()

    $Preferred = "D:\Programs\Git\cmd\git.exe"

    if (Test-Path -LiteralPath $Preferred -PathType Leaf) {
        return (Resolve-Path -LiteralPath $Preferred).Path
    }

    (Get-Command git.exe -ErrorAction Stop).Source
}

function Invoke-B43CapturedProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,

        [string[]]$ArgumentList = @(),

        [Parameter(Mandatory)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory)]
        [string]$TranscriptPath,

        [Parameter(Mandatory)]
        [string]$Operation
    )

    Assert-B43File -Path $FilePath -Description "$Operation executable" | Out-Null
    Assert-B43Directory -Path $WorkingDirectory -Description "$Operation working" | Out-Null

    $TranscriptDirectory = Split-Path -Parent $TranscriptPath
    New-B43Directory -Path $TranscriptDirectory | Out-Null

    $StdoutPath = Join-Path $TranscriptDirectory ([System.IO.Path]::GetRandomFileName())
    $StderrPath = Join-Path $TranscriptDirectory ([System.IO.Path]::GetRandomFileName())
    $StartedUtc = [DateTime]::UtcNow

    try {
        $Process = Start-Process `
            -FilePath $FilePath `
            -ArgumentList $ArgumentList `
            -WorkingDirectory $WorkingDirectory `
            -RedirectStandardOutput $StdoutPath `
            -RedirectStandardError $StderrPath `
            -NoNewWindow `
            -Wait `
            -PassThru

        $EndedUtc = [DateTime]::UtcNow
        $Stdout = if (Test-Path -LiteralPath $StdoutPath) {
            Get-Content -LiteralPath $StdoutPath -Raw
        }
        else {
            ""
        }
        $Stderr = if (Test-Path -LiteralPath $StderrPath) {
            Get-Content -LiteralPath $StderrPath -Raw
        }
        else {
            ""
        }

        $Header = @(
            "Operation: $Operation"
            "Started UTC: $($StartedUtc.ToString('o'))"
            "Ended UTC: $($EndedUtc.ToString('o'))"
            "Exit code: $($Process.ExitCode)"
            "Executable: $FilePath"
            "Arguments: $($ArgumentList -join ' ')"
            "Working directory: $WorkingDirectory"
            ""
            "--- STDOUT ---"
            $Stdout
            "--- STDERR ---"
            $Stderr
        ) -join [Environment]::NewLine

        Write-B43TextFile `
            -Content ($Header + [Environment]::NewLine) `
            -Path $TranscriptPath | Out-Null

        if ($Process.ExitCode -ne 0) {
            throw "$Operation failed with exit code $($Process.ExitCode). Transcript: $TranscriptPath"
        }

        [PSCustomObject]@{
            Operation = $Operation
            ExitCode = [int]$Process.ExitCode
            DurationSeconds = [math]::Round(($EndedUtc - $StartedUtc).TotalSeconds, 3)
            Transcript = $TranscriptPath
            Stdout = $Stdout
            Stderr = $Stderr
        }
    }
    finally {
        Remove-Item -LiteralPath $StdoutPath, $StderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-B43Git {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $GitExe = Get-B43GitExecutable
    $PreviousPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"
        $Output = @(& $GitExe -C $WorkingDirectory @Arguments 2>&1)
        $ExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousPreference
    }

    $Text = ($Output -join [Environment]::NewLine).Trim()

    if ($ExitCode -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $ExitCode.`n$Text"
    }

    $Text
}

function Get-B43ControlledPython {
    [CmdletBinding()]
    param()

    $Python = Join-Path `
        $env:USERPROFILE `
        ".espressif\python_env\idf6.0_py3.11_env\Scripts\python.exe"

    Assert-B43File -Path $Python -Description "Controlled Python"
}

function Get-B43PowerShellExecutable {
    [CmdletBinding()]
    param()

    $Command = Get-Command powershell.exe -ErrorAction Stop
    $Command.Source
}

function Get-B43FileRecord {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$Role,

        [Parameter(Mandatory)]
        [string]$EvidenceDirectory
    )

    $ResolvedPath = Assert-B43File -Path $Path -Description $Role
    $ResolvedEvidence = Assert-B43Directory -Path $EvidenceDirectory -Description "Evidence"

    if (-not $ResolvedPath.StartsWith(
        $ResolvedEvidence + "\",
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Evidence file is outside the pass evidence directory: $ResolvedPath"
    }

    $Item = Get-Item -LiteralPath $ResolvedPath
    $RelativePath = $ResolvedPath.Substring($ResolvedEvidence.Length).TrimStart("\")
    $Hash = (Get-FileHash -LiteralPath $ResolvedPath -Algorithm SHA256).Hash.ToLowerInvariant()

    [PSCustomObject]@{
        role = $Role
        path = $RelativePath.Replace("\", "/")
        size_bytes = [int64]$Item.Length
        sha256 = $Hash
    }
}

function Copy-B43EvidenceFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SourcePath,

        [Parameter(Mandatory)]
        [string]$DestinationName,

        [Parameter(Mandatory)]
        [string]$Role,

        [Parameter(Mandatory)]
        [string]$EvidenceDirectory
    )

    $ResolvedSource = Assert-B43File -Path $SourcePath -Description $Role
    $DestinationPath = Join-Path $EvidenceDirectory $DestinationName
    Copy-Item -LiteralPath $ResolvedSource -Destination $DestinationPath -Force
    Get-B43FileRecord -Path $DestinationPath -Role $Role -EvidenceDirectory $EvidenceDirectory
}

function Get-B43NewestFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Directory,

        [Parameter(Mandatory)]
        [string]$Filter,

        [Parameter(Mandatory)]
        [datetime]$NotBeforeUtc,

        [Parameter(Mandatory)]
        [string]$Description
    )

    $File = Get-ChildItem `
        -LiteralPath $Directory `
        -Filter $Filter `
        -File `
        -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTimeUtc -ge $NotBeforeUtc.AddSeconds(-2) } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1

    if ($null -eq $File) {
        throw "No new $Description matched '$Filter' in $Directory."
    }

    $File
}

function Resolve-B43SerialPort {
    [CmdletBinding()]
    param(
        [string]$RequestedPort
    )

    $Ports = @(
        Get-CimInstance Win32_SerialPort -ErrorAction SilentlyContinue |
        Sort-Object DeviceID |
        ForEach-Object {
            [PSCustomObject]@{
                Port = [string]$_.DeviceID
                Name = [string]$_.Name
                Description = [string]$_.Description
                PnpDeviceId = [string]$_.PNPDeviceID
            }
        }
    )

    $Candidates = @(
        $Ports | Where-Object {
            $_.Name -match '(?i)CP210x|Silicon Labs' -or
            $_.Description -match '(?i)CP210x|Silicon Labs'
        }
    )

    if (-not [string]::IsNullOrWhiteSpace($RequestedPort)) {
        $Normalized = $RequestedPort.Trim().ToUpperInvariant()
        $Match = @($Candidates | Where-Object { $_.Port.ToUpperInvariant() -eq $Normalized })

        if ($Match.Count -ne 1) {
            $Available = if ($Candidates.Count -eq 0) { "none" } else { $Candidates.Port -join ", " }
            throw "Requested CP210x serial port '$Normalized' was not uniquely detected. Available: $Available."
        }

        return $Match[0]
    }

    if ($Candidates.Count -ne 1) {
        $Available = if ($Candidates.Count -eq 0) { "none" } else { $Candidates.Port -join ", " }
        throw "Exactly one CP210x serial interface is required when -Port is omitted. Detected: $Available."
    }

    $Candidates[0]
}

function Assert-B43Toolchain {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ResolvedIdfPath,

        [Parameter(Mandatory)]
        [string]$PythonExe
    )

    $IdfCommit = Invoke-B43Git -WorkingDirectory $ResolvedIdfPath -Arguments @("rev-parse", "HEAD")
    $IdfDescription = Invoke-B43Git -WorkingDirectory $ResolvedIdfPath -Arguments @("describe", "--tags", "--always")
    $PythonVersion = (& $PythonExe --version 2>&1 | Out-String).Trim()

    if ($IdfCommit -ne $script:B43IdfCommit) {
        throw "ESP-IDF commit mismatch. Expected $($script:B43IdfCommit); detected $IdfCommit."
    }

    if ($IdfDescription -ne $script:B43IdfVersion) {
        throw "ESP-IDF version mismatch. Expected $($script:B43IdfVersion); detected $IdfDescription."
    }

    if ($PythonVersion -ne $script:B43PythonVersion) {
        throw "Python version mismatch. Expected $($script:B43PythonVersion); detected $PythonVersion."
    }

    [PSCustomObject]@{
        esp_idf_version = $IdfDescription
        esp_idf_commit = $IdfCommit
        python_version = $PythonVersion
        target = $script:B43Target
    }
}

function Invoke-B43ChildPowerShell {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ScriptPath,

        [string[]]$ScriptArguments = @(),

        [Parameter(Mandatory)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory)]
        [string]$TranscriptPath,

        [Parameter(Mandatory)]
        [string]$Operation
    )

    $PowerShellExe = Get-B43PowerShellExecutable
    $Arguments = @(
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $ScriptPath
    ) + $ScriptArguments

    Invoke-B43CapturedProcess `
        -FilePath $PowerShellExe `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -TranscriptPath $TranscriptPath `
        -Operation $Operation
}

function Invoke-B43WorkstationVerification {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ActiveRepository,

        [Parameter(Mandatory)]
        [string]$EvidenceDirectory,

        [Parameter(Mandatory)]
        [string]$Timestamp
    )

    $ScriptPath = Join-Path $ActiveRepository "tools\scripts\B1.3_Verify_Workstation.ps1"
    $B13EvidenceDirectory = Join-Path $ActiveRepository "docs\evidence\logs\B1.3"
    $Before = @(
        Get-ChildItem -LiteralPath $B13EvidenceDirectory -File -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
    )
    $TranscriptPath = Join-Path $EvidenceDirectory "workstation_verification_${Timestamp}.txt"

    try {
        $Result = Invoke-B43ChildPowerShell `
            -ScriptPath $ScriptPath `
            -ScriptArguments @("-SkipBoardCheck") `
            -WorkingDirectory $ActiveRepository `
            -TranscriptPath $TranscriptPath `
            -Operation "B1.3 workstation verification"

        $Records = New-Object System.Collections.Generic.List[object]
        $Records.Add((Get-B43FileRecord -Path $TranscriptPath -Role "workstation-verification" -EvidenceDirectory $EvidenceDirectory))

        $After = @(
            Get-ChildItem -LiteralPath $B13EvidenceDirectory -File -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty FullName
        )
        $NewFiles = @($After | Where-Object { $Before -notcontains $_ })

        foreach ($NewFile in $NewFiles) {
            $Name = "workstation_" + [System.IO.Path]::GetFileName($NewFile)
            $Records.Add((Copy-B43EvidenceFile `
                -SourcePath $NewFile `
                -DestinationName $Name `
                -Role "workstation-verification" `
                -EvidenceDirectory $EvidenceDirectory))
        }

        [PSCustomObject]@{
            Result = $Result
            Records = [object[]]$Records.ToArray()
            GeneratedFiles = $NewFiles
        }
    }
    finally {
        $Current = @(
            Get-ChildItem -LiteralPath $B13EvidenceDirectory -File -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty FullName
        )
        $Generated = @($Current | Where-Object { $Before -notcontains $_ })
        if ($Generated.Count -gt 0) {
            Remove-Item -LiteralPath $Generated -Force
        }
    }
}

function Invoke-B43HardwareIdentity {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$PythonExe,

        [Parameter(Mandatory)]
        [psobject]$ResolvedPort,

        [Parameter(Mandatory)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory)]
        [string]$EvidenceDirectory,

        [Parameter(Mandatory)]
        [string]$Timestamp
    )

    $ChipTranscript = Join-Path $EvidenceDirectory "hardware_chip_id_${Timestamp}.txt"
    $FlashTranscript = Join-Path $EvidenceDirectory "hardware_flash_id_${Timestamp}.txt"

    $ChipResult = Invoke-B43CapturedProcess `
        -FilePath $PythonExe `
        -ArgumentList @(
            "-m", "esptool",
            "-p", $ResolvedPort.Port,
            "-b", "115200",
            "--chip", "esp32s3",
            "chip-id"
        ) `
        -WorkingDirectory $WorkingDirectory `
        -TranscriptPath $ChipTranscript `
        -Operation "ESP32-S3 chip identity"

    $FlashResult = Invoke-B43CapturedProcess `
        -FilePath $PythonExe `
        -ArgumentList @(
            "-m", "esptool",
            "-p", $ResolvedPort.Port,
            "-b", "115200",
            "--chip", "esp32s3",
            "flash-id"
        ) `
        -WorkingDirectory $WorkingDirectory `
        -TranscriptPath $FlashTranscript `
        -Operation "ESP32-S3 flash identity"

    $ChipText = @($ChipResult.Stdout, $ChipResult.Stderr) -join [Environment]::NewLine
    $FlashText = @($FlashResult.Stdout, $FlashResult.Stderr) -join [Environment]::NewLine

    if ($ChipText -notmatch '(?im)Connected to\s+ESP32-S3') {
        throw "esptool did not identify an ESP32-S3 on $($ResolvedPort.Port)."
    }

    $FlashMatch = [regex]::Match(
        $FlashText,
        '(?im)(?:Detected flash size|Flash size):\s*(8MB)'
    )
    if (-not $FlashMatch.Success) {
        throw "esptool did not identify the required 8 MB flash device."
    }

    [PSCustomObject]@{
        Status = "PASS"
        Chip = "ESP32-S3"
        FlashSize = [string]$FlashMatch.Groups[1].Value
        ChipTranscript = $ChipTranscript
        FlashTranscript = $FlashTranscript
    }
}

function Get-B43FirmwareMetadata {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$TranscriptPath
    )

    $Text = Get-Content -LiteralPath $TranscriptPath -Raw
    $Metadata = [ordered]@{}

    foreach ($Match in [regex]::Matches($Text, '(?m)SQD_META\s+([a-z0-9_]+)=([^\r\n]+)')) {
        $Key = [string]$Match.Groups[1].Value
        $Value = ([string]$Match.Groups[2].Value).Trim()
        $Metadata[$Key] = $Value
    }

    foreach ($Key in $script:B43RequiredMetadataKeys) {
        if (-not $Metadata.Contains($Key) -or [string]::IsNullOrWhiteSpace([string]$Metadata[$Key])) {
            throw "Serial metadata is missing required key '$Key'."
        }
    }

    $Metadata
}

function Assert-B43SerialEvidence {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$TranscriptPath,

        [Parameter(Mandatory)]
        [string]$ExpectedCommit,

        [Parameter(Mandatory)]
        [string]$ExpectedProfile
    )

    $Text = Get-Content -LiteralPath $TranscriptPath -Raw
    $MarkerResults = [ordered]@{}

    foreach ($Marker in $script:B43RequiredSerialMarkers) {
        $Detected = $Text.Contains($Marker)
        $MarkerResults[$Marker] = $Detected
        if (-not $Detected) {
            throw "Required serial marker was not detected: $Marker"
        }
    }

    foreach ($Pattern in $script:B43ForbiddenSerialPatterns) {
        if ($Text -match [regex]::Escape($Pattern)) {
            throw "Forbidden serial marker was detected: $Pattern"
        }
    }

    $FatalRegex = '(?im)Guru Meditation Error|panic(?:''ed)?|Brownout detector was triggered|invalid header|partition table error|abort\(\)'
    $FatalCount = [regex]::Matches($Text, $FatalRegex).Count
    $HeartbeatCount = [regex]::Matches($Text, 'B1\.2:\s+Heartbeat:\s+\d+').Count

    if ($HeartbeatCount -lt 1) {
        throw "Serial transcript contains no heartbeat records."
    }

    if ($FatalCount -ne 0) {
        throw "Serial transcript contains $FatalCount fatal marker(s)."
    }

    $Metadata = Get-B43FirmwareMetadata -TranscriptPath $TranscriptPath
    $Expected = [ordered]@{
        git_commit = $ExpectedCommit
        git_dirty = "false"
        build_profile = $ExpectedProfile
        target = $script:B43Target
        idf_version = $script:B43IdfVersion
        hardware_compatibility = $script:B43HardwareCompatibility
    }

    foreach ($Entry in $Expected.GetEnumerator()) {
        if ([string]$Metadata[$Entry.Key] -ne [string]$Entry.Value) {
            throw "Firmware metadata mismatch for $($Entry.Key). Expected '$($Entry.Value)'; detected '$($Metadata[$Entry.Key])'."
        }
    }

    if ([string]$Metadata.elf_sha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw "Firmware metadata elf_sha256 is invalid."
    }

    [PSCustomObject]@{
        Status = "PASS"
        FatalMarkers = $FatalCount
        HeartbeatRecords = $HeartbeatCount
        RequiredMarkers = $MarkerResults
        Metadata = $Metadata
    }
}

function Write-B43Checksums {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object[]]$Records,

        [Parameter(Mandatory)]
        [string]$EvidenceDirectory
    )

    $Lines = @(
        $Records |
        Sort-Object path |
        ForEach-Object { "$($_.sha256)  $($_.path)" }
    )
    $Path = Join-Path $EvidenceDirectory "SHA256SUMS.txt"
    Write-B43TextFile -Content (($Lines -join "`n") + "`n") -Path $Path
}

function New-B43PassManifest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$PassId,

        [Parameter(Mandatory)]
        [string]$ManifestPath,

        [Parameter(Mandatory)]
        [string]$PassRoot,

        [Parameter(Mandatory)]
        [string]$CloneRoot,

        [Parameter(Mandatory)]
        [psobject]$Toolchain,

        [Parameter(Mandatory)]
        [string]$BuildDirectory,

        [Parameter(Mandatory)]
        [string]$ApplicationSha256,

        [Parameter(Mandatory)]
        [psobject]$Device,

        [Parameter(Mandatory)]
        [psobject]$DeviceIdentity,

        [Parameter(Mandatory)]
        [psobject]$Monitor,

        [Parameter(Mandatory)]
        [string]$PassEvidenceDirectory,

        [Parameter(Mandatory)]
        [object[]]$EvidenceRecords,

        [Parameter(Mandatory)]
        [bool]$TrackedTreeCleanAfter
    )

    $Manifest = [ordered]@{
        schema_version = 1
        work_package = "B4.3"
        operation = "clean-checkout-to-flash-reproduction"
        status = "PASS"
        pass_id = $PassId
        timestamp_local = (Get-Date).ToString("o")
        source = [ordered]@{
            repository = $RepositoryUrl
            parent_baseline = $script:B43ParentBaseline
            commit = $SourceCommit.ToLowerInvariant()
            branch = $script:B43CompatibilityBranch
        }
        cleanroom = [ordered]@{
            root = $PassRoot
            clone_root = $CloneRoot
            clone_created = $true
            existing_directory_reused = $false
            existing_build_reused = $false
            tracked_tree_clean_before = $true
            tracked_tree_clean_after = $TrackedTreeCleanAfter
        }
        toolchain = [ordered]@{
            esp_idf_version = $Toolchain.esp_idf_version
            esp_idf_commit = $Toolchain.esp_idf_commit
            python_version = $Toolchain.python_version
            target = $Toolchain.target
        }
        build = [ordered]@{
            profile = $Profile
            status = "PASS"
            directory = $BuildDirectory
            application_sha256 = $ApplicationSha256.ToLowerInvariant()
        }
        device = [ordered]@{
            status = "PASS"
            port = $Device.Port
            name = $Device.Name
            pnp_device_id = $Device.PnpDeviceId
            hardware_compatibility = $script:B43HardwareCompatibility
            chip = $DeviceIdentity.Chip
            flash_size = $DeviceIdentity.FlashSize
            erase_status = "PASS"
            flash_status = "PASS"
        }
        monitor = [ordered]@{
            status = $Monitor.Status
            fatal_markers = $Monitor.FatalMarkers
            heartbeat_records = $Monitor.HeartbeatRecords
            required_markers = $Monitor.RequiredMarkers
            metadata = $Monitor.Metadata
        }
        evidence = [ordered]@{
            root = $PassEvidenceDirectory
            checksums = "SHA256SUMS.txt"
            files = $EvidenceRecords
        }
    }

    Write-B43JsonFile -InputObject $Manifest -Path $ManifestPath -Depth 30 | Out-Null
    $ManifestPath
}

function Invoke-B43Pass {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [int]$PassNumber,

        [Parameter(Mandatory)]
        [string]$ActiveRepository,

        [Parameter(Mandatory)]
        [psobject]$Toolchain,

        [Parameter(Mandatory)]
        [psobject]$ResolvedPort,

        [Parameter(Mandatory)]
        [string]$RunEvidenceRoot
    )

    $Timestamp = Get-B43Timestamp
    $PassId = "pass-{0:D2}-{1}" -f $PassNumber, $Timestamp
    $Unique = [guid]::NewGuid().ToString("N").Substring(0, 8)
    $PassRoot = Join-Path $CleanroomRoot "${PassId}_${Unique}"
    $CloneRoot = Join-Path $PassRoot "clone"
    $PassEvidenceDirectory = Join-Path $RunEvidenceRoot $PassId
    $ManifestPath = Join-Path $RunEvidenceRoot "B4.3_reproduction_manifest_${PassId}.json"

    if (Test-Path -LiteralPath $PassRoot) {
        throw "Refusing to reuse existing cleanroom pass directory: $PassRoot"
    }
    if (Test-Path -LiteralPath $PassEvidenceDirectory) {
        throw "Refusing to reuse existing evidence directory: $PassEvidenceDirectory"
    }

    New-B43Directory -Path $PassRoot | Out-Null
    New-B43Directory -Path $PassEvidenceDirectory | Out-Null

    $EvidenceRecords = New-Object System.Collections.Generic.List[object]

    try {
        Write-B43Section -Title "B4.3 REPRODUCTION $PassId"

        $CloneTranscript = Join-Path $PassEvidenceDirectory "clean_clone_${Timestamp}.txt"
        $GitExe = Get-B43GitExecutable
        $CloneResult = Invoke-B43CapturedProcess `
            -FilePath $GitExe `
            -ArgumentList @("clone", "--no-checkout", "--origin", "origin", $RepositoryUrl, $CloneRoot) `
            -WorkingDirectory $PassRoot `
            -TranscriptPath $CloneTranscript `
            -Operation "B4.3 clean Git clone"
        $EvidenceRecords.Add((Get-B43FileRecord -Path $CloneTranscript -Role "clean-clone-identity" -EvidenceDirectory $PassEvidenceDirectory))

        Invoke-B43Git -WorkingDirectory $CloneRoot -Arguments @("checkout", "--detach", $SourceCommit) | Out-Null
        Invoke-B43Git -WorkingDirectory $CloneRoot -Arguments @("branch", "-f", $script:B43CompatibilityBranch, $SourceCommit) | Out-Null
        Invoke-B43Git -WorkingDirectory $CloneRoot -Arguments @("switch", $script:B43CompatibilityBranch) | Out-Null

        $CloneCommit = Invoke-B43Git -WorkingDirectory $CloneRoot -Arguments @("rev-parse", "HEAD")
        $CloneRemote = Invoke-B43Git -WorkingDirectory $CloneRoot -Arguments @("remote", "get-url", "origin")
        $TrackedBefore = Invoke-B43Git -WorkingDirectory $CloneRoot -Arguments @("status", "--porcelain", "--untracked-files=no")
        $AncestorOutput = @(& $GitExe -C $CloneRoot merge-base --is-ancestor $script:B43ParentBaseline $CloneCommit 2>&1)
        $AncestorExitCode = $LASTEXITCODE

        if ($CloneCommit -ne $SourceCommit.ToLowerInvariant()) {
            throw "Clean clone commit mismatch. Expected $SourceCommit; detected $CloneCommit."
        }
        if ($CloneRemote -ne $RepositoryUrl) {
            throw "Clean clone remote mismatch. Expected $RepositoryUrl; detected $CloneRemote."
        }
        if (-not [string]::IsNullOrWhiteSpace($TrackedBefore)) {
            throw "Clean clone contains tracked changes before verification: $TrackedBefore"
        }
        foreach ($ForbiddenBuildPath in @(
            (Join-Path $CloneRoot "build"),
            (Join-Path $CloneRoot "build\b3.2\$Profile")
        )) {
            if (Test-Path -LiteralPath $ForbiddenBuildPath) {
                throw "Fresh clone unexpectedly contains an existing build path: $ForbiddenBuildPath"
            }
        }
        if ($AncestorExitCode -ne 0) {
            throw "Source commit does not descend from B4.2 parent baseline. $($AncestorOutput -join ' ')"
        }

        $IdentityPath = Join-Path $PassEvidenceDirectory "clean_clone_identity_${Timestamp}.txt"
        $IdentityText = @(
            "Repository: $CloneRemote"
            "Parent baseline: $($script:B43ParentBaseline)"
            "Source commit: $CloneCommit"
            "Compatibility branch: $($script:B43CompatibilityBranch)"
            "Clone root: $CloneRoot"
            "Clone created: true"
            "Existing directory reused: false"
            "Tracked tree clean before: true"
        ) -join [Environment]::NewLine
        Write-B43TextFile -Content ($IdentityText + "`n") -Path $IdentityPath | Out-Null
        $EvidenceRecords.Add((Get-B43FileRecord -Path $IdentityPath -Role "clean-clone-identity" -EvidenceDirectory $PassEvidenceDirectory))

        $Workstation = Invoke-B43WorkstationVerification `
            -ActiveRepository $ActiveRepository `
            -EvidenceDirectory $PassEvidenceDirectory `
            -Timestamp $Timestamp
        foreach ($Record in $Workstation.Records) {
            $EvidenceRecords.Add($Record)
        }

        $ToolchainGuardStart = [DateTime]::UtcNow
        $ToolchainTranscript = Join-Path $PassEvidenceDirectory "toolchain_guard_${Timestamp}.txt"
        $env:SQD_B33_EXPECTED_BRANCH = $script:B43CompatibilityBranch
        try {
            Invoke-B43ChildPowerShell `
                -ScriptPath (Join-Path $CloneRoot "tools\scripts\B3.3_ToolchainGuard.ps1") `
                -ScriptArguments @("-RepoRoot", $CloneRoot, "-IdfPath", $IdfPath) `
                -WorkingDirectory $CloneRoot `
                -TranscriptPath $ToolchainTranscript `
                -Operation "B3.3 toolchain guard" | Out-Null
        }
        finally {
            Remove-Item Env:SQD_B33_EXPECTED_BRANCH -ErrorAction SilentlyContinue
        }
        $EvidenceRecords.Add((Get-B43FileRecord -Path $ToolchainTranscript -Role "toolchain-identity" -EvidenceDirectory $PassEvidenceDirectory))

        $B33Evidence = Join-Path $CloneRoot "docs\evidence\logs\B3.3"
        $ToolchainResultFile = Get-B43NewestFile `
            -Directory $B33Evidence `
            -Filter "B3.3_toolchain_guard_result_*.json" `
            -NotBeforeUtc $ToolchainGuardStart `
            -Description "B3.3 toolchain result"
        $EvidenceRecords.Add((Copy-B43EvidenceFile `
            -SourcePath $ToolchainResultFile.FullName `
            -DestinationName "toolchain_identity_${Timestamp}.json" `
            -Role "toolchain-identity" `
            -EvidenceDirectory $PassEvidenceDirectory))

        $HostTranscript = Join-Path $PassEvidenceDirectory "host_tests_${Timestamp}.txt"
        Invoke-B43CapturedProcess `
            -FilePath (Get-B43ControlledPython) `
            -ArgumentList @("-B", (Join-Path $CloneRoot "tools\ci\run_host_tests.py")) `
            -WorkingDirectory $CloneRoot `
            -TranscriptPath $HostTranscript `
            -Operation "B4.1 host tests" | Out-Null
        $EvidenceRecords.Add((Get-B43FileRecord -Path $HostTranscript -Role "host-tests" -EvidenceDirectory $PassEvidenceDirectory))

        $B42Transcript = Join-Path $PassEvidenceDirectory "b4_2_contract_${Timestamp}.txt"
        Invoke-B43CapturedProcess `
            -FilePath (Get-B43ControlledPython) `
            -ArgumentList @("-B", (Join-Path $CloneRoot "tools\ci\verify_b4_2.py"), "--repo-root", $CloneRoot, "--contract-only") `
            -WorkingDirectory $CloneRoot `
            -TranscriptPath $B42Transcript `
            -Operation "B4.2 repository contract" | Out-Null
        $EvidenceRecords.Add((Get-B43FileRecord -Path $B42Transcript -Role "b4.2-contract" -EvidenceDirectory $PassEvidenceDirectory))

        $BuildStart = [DateTime]::UtcNow
        $BuildTranscript = Join-Path $PassEvidenceDirectory "controlled_build_${Timestamp}.txt"
        Invoke-B43ChildPowerShell `
            -ScriptPath (Join-Path $CloneRoot "tools\scripts\B3.2_Build.ps1") `
            -ScriptArguments @(
                "-Profile", $Profile,
                "-RepoRoot", $CloneRoot,
                "-IdfPath", $IdfPath,
                "-HardwareCompatibility", $script:B43HardwareCompatibility
            ) `
            -WorkingDirectory $CloneRoot `
            -TranscriptPath $BuildTranscript `
            -Operation "B3.2 controlled $Profile build" | Out-Null
        $EvidenceRecords.Add((Get-B43FileRecord -Path $BuildTranscript -Role "controlled-build" -EvidenceDirectory $PassEvidenceDirectory))

        $B32Evidence = Join-Path $CloneRoot "docs\evidence\logs\B3.2"
        $BuildResultFile = Get-B43NewestFile `
            -Directory $B32Evidence `
            -Filter "B3.2_${Profile}_build_result_*.json" `
            -NotBeforeUtc $BuildStart `
            -Description "$Profile build result"
        $BuildResult = Get-Content -LiteralPath $BuildResultFile.FullName -Raw | ConvertFrom-Json
        if ([string]$BuildResult.status -ne "PASS") {
            throw "B3.2 build result is not PASS."
        }
        $ApplicationSha256 = [string]$BuildResult.application_binary.sha256
        $BuildDirectory = [string]$BuildResult.build.directory
        if ($ApplicationSha256 -notmatch '^[0-9a-fA-F]{64}$') {
            throw "B3.2 application SHA-256 is invalid."
        }
        $EvidenceRecords.Add((Copy-B43EvidenceFile `
            -SourcePath $BuildResultFile.FullName `
            -DestinationName "controlled_build_result_${Timestamp}.json" `
            -Role "controlled-build" `
            -EvidenceDirectory $PassEvidenceDirectory))

        $DeviceIdentity = Invoke-B43HardwareIdentity `
            -PythonExe (Get-B43ControlledPython) `
            -ResolvedPort $ResolvedPort `
            -WorkingDirectory $CloneRoot `
            -EvidenceDirectory $PassEvidenceDirectory `
            -Timestamp $Timestamp
        $EvidenceRecords.Add((Get-B43FileRecord `
            -Path $DeviceIdentity.ChipTranscript `
            -Role "erase-flash" `
            -EvidenceDirectory $PassEvidenceDirectory))
        $EvidenceRecords.Add((Get-B43FileRecord `
            -Path $DeviceIdentity.FlashTranscript `
            -Role "erase-flash" `
            -EvidenceDirectory $PassEvidenceDirectory))

        $EraseStart = [DateTime]::UtcNow
        $EraseTranscript = Join-Path $PassEvidenceDirectory "erase_flash_erase_${Timestamp}.txt"
        Invoke-B43ChildPowerShell `
            -ScriptPath (Join-Path $CloneRoot "tools\scripts\B3.2_Erase.ps1") `
            -ScriptArguments @(
                "-Port", $ResolvedPort.Port,
                "-ConfirmErase",
                "-RepoRoot", $CloneRoot,
                "-IdfPath", $IdfPath,
                "-HardwareCompatibility", $script:B43HardwareCompatibility
            ) `
            -WorkingDirectory $CloneRoot `
            -TranscriptPath $EraseTranscript `
            -Operation "B3.2 controlled flash erase" | Out-Null
        $EvidenceRecords.Add((Get-B43FileRecord -Path $EraseTranscript -Role "erase-flash" -EvidenceDirectory $PassEvidenceDirectory))
        $EraseResultFile = Get-B43NewestFile `
            -Directory $B32Evidence `
            -Filter "B3.2_erase_result_*.json" `
            -NotBeforeUtc $EraseStart `
            -Description "erase result"
        $EraseResult = Get-Content -LiteralPath $EraseResultFile.FullName -Raw | ConvertFrom-Json
        if ([string]$EraseResult.status -ne "PASS" -or -not [bool]$EraseResult.authorization.confirm_erase) {
            throw "Controlled erase evidence is not PASS with explicit authorization."
        }
        $EvidenceRecords.Add((Copy-B43EvidenceFile `
            -SourcePath $EraseResultFile.FullName `
            -DestinationName "erase_flash_erase_result_${Timestamp}.json" `
            -Role "erase-flash" `
            -EvidenceDirectory $PassEvidenceDirectory))

        $FlashStart = [DateTime]::UtcNow
        $FlashTranscript = Join-Path $PassEvidenceDirectory "erase_flash_program_${Timestamp}.txt"
        Invoke-B43ChildPowerShell `
            -ScriptPath (Join-Path $CloneRoot "tools\scripts\B3.2_Flash.ps1") `
            -ScriptArguments @(
                "-Profile", $Profile,
                "-Port", $ResolvedPort.Port,
                "-RepoRoot", $CloneRoot,
                "-IdfPath", $IdfPath,
                "-HardwareCompatibility", $script:B43HardwareCompatibility
            ) `
            -WorkingDirectory $CloneRoot `
            -TranscriptPath $FlashTranscript `
            -Operation "B3.2 controlled $Profile flash" | Out-Null
        $EvidenceRecords.Add((Get-B43FileRecord -Path $FlashTranscript -Role "erase-flash" -EvidenceDirectory $PassEvidenceDirectory))
        $FlashResultFile = Get-B43NewestFile `
            -Directory $B32Evidence `
            -Filter "B3.2_${Profile}_flash_result_*.json" `
            -NotBeforeUtc $FlashStart `
            -Description "$Profile flash result"
        $FlashResult = Get-Content -LiteralPath $FlashResultFile.FullName -Raw | ConvertFrom-Json
        if ([string]$FlashResult.status -ne "PASS") {
            throw "Controlled flash evidence is not PASS."
        }
        if ([string]$FlashResult.application_binary.sha256 -ne $ApplicationSha256) {
            throw "Flashed application SHA-256 does not match the clean build."
        }
        $EvidenceRecords.Add((Copy-B43EvidenceFile `
            -SourcePath $FlashResultFile.FullName `
            -DestinationName "erase_flash_program_result_${Timestamp}.json" `
            -Role "erase-flash" `
            -EvidenceDirectory $PassEvidenceDirectory))

        $MonitorStart = [DateTime]::UtcNow
        $MonitorCommandTranscript = Join-Path $PassEvidenceDirectory "serial_monitor_command_${Timestamp}.txt"
        Invoke-B43ChildPowerShell `
            -ScriptPath (Join-Path $CloneRoot "tools\scripts\B3.2_Monitor.ps1") `
            -ScriptArguments @(
                "-Profile", $Profile,
                "-Port", $ResolvedPort.Port,
                "-Baud", "115200",
                "-DurationSeconds", [string]$MonitorSeconds,
                "-RepoRoot", $CloneRoot,
                "-IdfPath", $IdfPath,
                "-HardwareCompatibility", $script:B43HardwareCompatibility
            ) `
            -WorkingDirectory $CloneRoot `
            -TranscriptPath $MonitorCommandTranscript `
            -Operation "B3.2 controlled $Profile monitor" | Out-Null
        $EvidenceRecords.Add((Get-B43FileRecord -Path $MonitorCommandTranscript -Role "serial-monitor" -EvidenceDirectory $PassEvidenceDirectory))

        $MonitorResultFile = Get-B43NewestFile `
            -Directory $B32Evidence `
            -Filter "B3.2_${Profile}_monitor_result_*.json" `
            -NotBeforeUtc $MonitorStart `
            -Description "$Profile monitor result"
        $MonitorResult = Get-Content -LiteralPath $MonitorResultFile.FullName -Raw | ConvertFrom-Json
        if ([string]$MonitorResult.status -ne "PASS") {
            throw "Controlled monitor result is not PASS."
        }
        $OriginalSerialTranscript = [string]$MonitorResult.monitor.transcript
        $SerialTranscriptRecord = Copy-B43EvidenceFile `
            -SourcePath $OriginalSerialTranscript `
            -DestinationName "serial_monitor_${Timestamp}.txt" `
            -Role "serial-monitor" `
            -EvidenceDirectory $PassEvidenceDirectory
        $EvidenceRecords.Add($SerialTranscriptRecord)

        $CopiedSerialTranscript = Join-Path $PassEvidenceDirectory $SerialTranscriptRecord.path
        $MonitorValidation = Assert-B43SerialEvidence `
            -TranscriptPath $CopiedSerialTranscript `
            -ExpectedCommit $SourceCommit.ToLowerInvariant() `
            -ExpectedProfile $Profile

        $MetadataPath = Join-Path $PassEvidenceDirectory "firmware_metadata_${Timestamp}.json"
        Write-B43JsonFile -InputObject $MonitorValidation.Metadata -Path $MetadataPath -Depth 10 | Out-Null
        $EvidenceRecords.Add((Get-B43FileRecord -Path $MetadataPath -Role "firmware-metadata" -EvidenceDirectory $PassEvidenceDirectory))

        $TrackedAfter = Invoke-B43Git -WorkingDirectory $CloneRoot -Arguments @("status", "--porcelain", "--untracked-files=no")
        $TrackedTreeCleanAfter = [string]::IsNullOrWhiteSpace($TrackedAfter)
        if (-not $TrackedTreeCleanAfter) {
            throw "Clean clone contains tracked changes after reproduction: $TrackedAfter"
        }

        $ResultsCsvPath = Join-Path $PassEvidenceDirectory "B4.3_gate_verification_results_${Timestamp}.csv"
        @(
            [PSCustomObject]@{ Check = "clean-clone"; Status = "PASS"; Details = $CloneRoot }
            [PSCustomObject]@{ Check = "workstation-verification"; Status = "PASS"; Details = "B1.3" }
            [PSCustomObject]@{ Check = "toolchain-identity"; Status = "PASS"; Details = $Toolchain.esp_idf_commit }
            [PSCustomObject]@{ Check = "host-tests"; Status = "PASS"; Details = "B4.1 host suite" }
            [PSCustomObject]@{ Check = "b4.2-contract"; Status = "PASS"; Details = "contract-only" }
            [PSCustomObject]@{ Check = "controlled-build"; Status = "PASS"; Details = $ApplicationSha256 }
            [PSCustomObject]@{ Check = "hardware-identity"; Status = "PASS"; Details = "$($DeviceIdentity.Chip); $($DeviceIdentity.FlashSize)" }
            [PSCustomObject]@{ Check = "erase-flash"; Status = "PASS"; Details = $ResolvedPort.Port }
            [PSCustomObject]@{ Check = "serial-monitor"; Status = "PASS"; Details = "Heartbeats=$($MonitorValidation.HeartbeatRecords)" }
            [PSCustomObject]@{ Check = "firmware-metadata"; Status = "PASS"; Details = $MonitorValidation.Metadata.git_commit }
        ) | Export-Csv -LiteralPath $ResultsCsvPath -NoTypeInformation -Encoding UTF8
        $EvidenceRecords.Add((Get-B43FileRecord -Path $ResultsCsvPath -Role "reproduction-results" -EvidenceDirectory $PassEvidenceDirectory))

        [object[]]$RecordArray = $EvidenceRecords.ToArray()
        Write-B43Checksums -Records $RecordArray -EvidenceDirectory $PassEvidenceDirectory | Out-Null

        New-B43PassManifest `
            -PassId $PassId `
            -ManifestPath $ManifestPath `
            -PassRoot $PassRoot `
            -CloneRoot $CloneRoot `
            -Toolchain $Toolchain `
            -BuildDirectory $BuildDirectory `
            -ApplicationSha256 $ApplicationSha256 `
            -Device $ResolvedPort `
            -DeviceIdentity $DeviceIdentity `
            -Monitor $MonitorValidation `
            -PassEvidenceDirectory $PassEvidenceDirectory `
            -EvidenceRecords $RecordArray `
            -TrackedTreeCleanAfter $TrackedTreeCleanAfter | Out-Null

        Write-Host "PASS: $PassId completed."
        Write-Host "Manifest: $ManifestPath"
        Write-Host "Evidence: $PassEvidenceDirectory"

        $ManifestPath
    }
    finally {
        if ((Test-Path -LiteralPath $PassRoot) -and (-not $KeepCleanrooms.IsPresent)) {
            Set-Location $ActiveRepository
            Remove-Item -LiteralPath $PassRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

$ActiveRepository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$ExpectedActiveRepository = "D:\OneDrive\SQD"
if (-not [string]::Equals(
    [System.IO.Path]::GetFullPath($ActiveRepository),
    [System.IO.Path]::GetFullPath($ExpectedActiveRepository),
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "B1.3 inherited verification requires active repository $ExpectedActiveRepository; detected $ActiveRepository."
}
$ResolvedIdfPath = Assert-B43Directory -Path $IdfPath -Description "ESP-IDF"
$PythonExe = Get-B43ControlledPython
$ContractPath = Assert-B43File `
    -Path (Join-Path $ActiveRepository "tools\ci\b4_3_reproduction_contract.json") `
    -Description "B4.3 contract"
$VerifierPath = Assert-B43File `
    -Path (Join-Path $ActiveRepository "tools\ci\verify_b4_3.py") `
    -Description "B4.3 verifier"

Write-B43Section -Title "B4.3 CLEAN CHECKOUT-TO-FLASH REPRODUCTION"
Write-Host "Active repository:  $ActiveRepository"
Write-Host "Repository URL:      $RepositoryUrl"
Write-Host "Source commit:       $SourceCommit"
Write-Host "Parent baseline:     $($script:B43ParentBaseline)"
Write-Host "Profile:             $Profile"
Write-Host "Pass count:          $PassCount"
Write-Host "ESP-IDF:             $ResolvedIdfPath"
Write-Host "Cleanroom root:      $CleanroomRoot"
Write-Host "Evidence root:       $EvidenceRoot"
Write-Host "Plan only:           $($PlanOnly.IsPresent)"
Write-Host "Hardware authorized: $($ConfirmHardwareOperations.IsPresent)"

$ExpectedRepositoryUrl = "https://github.com/CPParthasarathy/SQD.git"
if ($RepositoryUrl -ne $ExpectedRepositoryUrl) {
    throw "Repository URL mismatch. Expected $ExpectedRepositoryUrl; detected $RepositoryUrl."
}

$ActiveRoot = Invoke-B43Git -WorkingDirectory $ActiveRepository -Arguments @("rev-parse", "--show-toplevel")
if (-not [string]::Equals(
    [System.IO.Path]::GetFullPath($ActiveRoot),
    [System.IO.Path]::GetFullPath($ActiveRepository),
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "B4.3 script root is not the active Git repository root."
}

$ActiveCommit = Invoke-B43Git -WorkingDirectory $ActiveRepository -Arguments @("rev-parse", "HEAD")
$ActiveTrackedStatus = Invoke-B43Git -WorkingDirectory $ActiveRepository -Arguments @("status", "--porcelain", "--untracked-files=no")
if ($ActiveCommit -ne $SourceCommit.ToLowerInvariant()) {
    throw "Active repository HEAD must equal -SourceCommit. Expected $SourceCommit; detected $ActiveCommit."
}
if (-not [string]::IsNullOrWhiteSpace($ActiveTrackedStatus)) {
    throw "Active repository contains tracked changes. Commit or restore them before B4.3 reproduction."
}

$GitExe = Get-B43GitExecutable
$AncestorOutput = @(& $GitExe -C $ActiveRepository merge-base --is-ancestor $script:B43ParentBaseline $SourceCommit 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Source commit does not descend from the accepted B4.2 parent baseline. $($AncestorOutput -join ' ')"
}

$Toolchain = Assert-B43Toolchain -ResolvedIdfPath $ResolvedIdfPath -PythonExe $PythonExe

& $PythonExe -B $VerifierPath --repo-root $ActiveRepository --contract $ContractPath --contract-only
if ($LASTEXITCODE -ne 0) {
    throw "B4.3 repository contract verification failed."
}

if ($PlanOnly.IsPresent) {
    Write-Host ""
    Write-Host "PASS: B4.3 plan validation completed."
    Write-Host "No cleanroom, build, erase, flash, monitor or evidence operation was executed."
    return
}

if (-not $ConfirmHardwareOperations.IsPresent) {
    throw "Physical erase and flash are not authorized. Re-run with -ConfirmHardwareOperations."
}

$ResolvedPort = Resolve-B43SerialPort -RequestedPort $Port
Write-Host "Resolved serial port: $($ResolvedPort.Port) [$($ResolvedPort.Name)]"

New-B43Directory -Path $CleanroomRoot | Out-Null
New-B43Directory -Path $EvidenceRoot | Out-Null
$RunTimestamp = Get-B43Timestamp
$RunEvidenceRoot = Join-Path $EvidenceRoot "B4.3_${RunTimestamp}_$($SourceCommit.Substring(0, 12))"
if (Test-Path -LiteralPath $RunEvidenceRoot) {
    throw "Refusing to reuse existing B4.3 run evidence directory: $RunEvidenceRoot"
}
New-B43Directory -Path $RunEvidenceRoot | Out-Null

$ManifestPaths = New-Object System.Collections.Generic.List[string]
for ($PassNumber = 1; $PassNumber -le $PassCount; $PassNumber++) {
    $ManifestPaths.Add((Invoke-B43Pass `
        -PassNumber $PassNumber `
        -ActiveRepository $ActiveRepository `
        -Toolchain $Toolchain `
        -ResolvedPort $ResolvedPort `
        -RunEvidenceRoot $RunEvidenceRoot))
}

$VerifierArguments = @(
    "-B",
    $VerifierPath,
    "--repo-root",
    $ActiveRepository,
    "--contract",
    $ContractPath
)
foreach ($ManifestPath in $ManifestPaths) {
    $VerifierArguments += @("--manifest", $ManifestPath)
}

$VerificationTranscript = Join-Path $RunEvidenceRoot "B4.3_two_pass_verification_${RunTimestamp}.txt"
Invoke-B43CapturedProcess `
    -FilePath $PythonExe `
    -ArgumentList $VerifierArguments `
    -WorkingDirectory $ActiveRepository `
    -TranscriptPath $VerificationTranscript `
    -Operation "B4.3 complete repeatability verification" | Out-Null

$RunChecksumPath = Join-Path $RunEvidenceRoot "B4.3_RUN_SHA256SUMS_${RunTimestamp}.txt"
$RunChecksumFiles = @($ManifestPaths.ToArray()) + @($VerificationTranscript)
$RunChecksumLines = @(
    foreach ($RunFile in $RunChecksumFiles) {
        $ResolvedRunFile = Assert-B43File -Path $RunFile -Description "Run-level evidence"
        $RelativeRunPath = $ResolvedRunFile.Substring($RunEvidenceRoot.Length).TrimStart("\").Replace("\", "/")
        $RunHash = (Get-FileHash -LiteralPath $ResolvedRunFile -Algorithm SHA256).Hash.ToLowerInvariant()
        "$RunHash  $RelativeRunPath"
    }
)
Write-B43TextFile -Content (($RunChecksumLines -join "`n") + "`n") -Path $RunChecksumPath | Out-Null

Write-B43Section -Title "B4.3 REPRODUCTION PASSED"
Write-Host "Source commit: $SourceCommit"
Write-Host "Profile:       $Profile"
Write-Host "Serial port:   $($ResolvedPort.Port)"
Write-Host "Passes:        $PassCount"
Write-Host "Evidence root: $RunEvidenceRoot"
Write-Host "Verification:  $VerificationTranscript"
Write-Host "Run checksums: $RunChecksumPath"
foreach ($ManifestPath in $ManifestPaths) {
    Write-Host "Manifest:      $ManifestPath"
}
