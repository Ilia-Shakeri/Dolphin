[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupRoot,

    [Parameter(Mandatory = $true)]
    [string]$DatabaseHost,

    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 65535)]
    [int]$DatabasePort,

    [Parameter(Mandatory = $true)]
    [string]$DatabaseName,

    [Parameter(Mandatory = $true)]
    [string]$DatabaseUser,

    [string]$PostgresBin = "",

    [ValidateRange(0, 3650)]
    [int]$RetentionDays = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$backupNamePattern = "^(?:frooshbin|kariz)-pg-(?<timestamp>[0-9]{8}T[0-9]{6}Z)-(?<token>[0-9a-f]{32})[.]dump$"
$checksumNamePattern = "^(?:frooshbin|kariz)-pg-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}[.]dump[.]sha256$"

function Test-SamePath {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )

    $comparison = if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        [StringComparison]::OrdinalIgnoreCase
    } else {
        [StringComparison]::Ordinal
    }
    return [string]::Equals(
        [IO.Path]::GetFullPath($Left),
        [IO.Path]::GetFullPath($Right),
        $comparison
    )
}

function Get-ValidatedBackupRoot {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "BackupRoot must be an existing directory."
    }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $rootItem = Get-Item -LiteralPath $resolved -Force
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "BackupRoot cannot be a link or reparse point."
    }
    $trimCharacters = [char[]]@([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $volumeRoot = [IO.Path]::GetPathRoot($resolved)
    if ($resolved.TrimEnd($trimCharacters) -eq $volumeRoot.TrimEnd($trimCharacters)) {
        throw "BackupRoot cannot be a filesystem root."
    }
    $sentinels = @(
        @{ Path = (Join-Path $resolved ".frooshbin-backup-root"); Value = "FROOSHBIN_BACKUP_ROOT_V1" },
        @{ Path = (Join-Path $resolved ".kariz-backup-root"); Value = "KARIZ_BACKUP_ROOT_V1" }
    )
    $present = @($sentinels | Where-Object { Test-Path -LiteralPath $_.Path })
    if ($present.Count -eq 0) {
        throw "BackupRoot sentinel is missing."
    }
    foreach ($sentinel in $present) {
        $sentinelItem = Get-Item -LiteralPath $sentinel.Path -Force
        if (-not (Test-Path -LiteralPath $sentinel.Path -PathType Leaf) -or
            ($sentinelItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
            (Get-Content -LiteralPath $sentinel.Path -Raw).Trim() -cne $sentinel.Value) {
            throw "BackupRoot sentinel value is invalid."
        }
    }
    return $resolved
}

function Get-PostgresTool {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$BinPath
    )

    if (-not [string]::IsNullOrWhiteSpace($BinPath)) {
        if (-not (Test-Path -LiteralPath $BinPath -PathType Container)) {
            throw "PostgresBin must be an existing directory."
        }
        $resolvedBin = (Resolve-Path -LiteralPath $BinPath).Path
        foreach ($leaf in @("$Name.exe", $Name)) {
            $candidate = Join-Path $resolvedBin $leaf
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return $candidate
            }
        }
        throw "Required PostgreSQL tool is missing from PostgresBin."
    }
    return (Get-Command $Name -CommandType Application -ErrorAction Stop).Source
}

function Assert-DatabaseValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowEmptyString()][string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name must not be empty."
    }
    if ($Value -match "[`r`n]") {
        throw "$Name contains an unsafe line break."
    }
}

function Invoke-ExactRetention {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][int]$Days,
        [Parameter(Mandatory = $true)][string]$CurrentBackup
    )

    if ($Days -eq 0) {
        return
    }
    $cutoff = [DateTime]::UtcNow.AddDays(-$Days)
    foreach ($candidate in Get-ChildItem -LiteralPath $Root -File) {
        if ($candidate.Name -notmatch $backupNamePattern) {
            continue
        }
        if (Test-SamePath -Left $candidate.FullName -Right $CurrentBackup) {
            continue
        }
        if (($candidate.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            continue
        }
        $timestamp = [DateTime]::ParseExact(
            $Matches["timestamp"],
            "yyyyMMddTHHmmssZ",
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
        )
        if ($timestamp -ge $cutoff) {
            continue
        }
        if (-not (Test-SamePath -Left (Split-Path $candidate.FullName -Parent) -Right $Root)) {
            throw "Retention candidate escaped BackupRoot."
        }
        $checksumName = "$($candidate.Name).sha256"
        if ($checksumName -notmatch $checksumNamePattern) {
            throw "Retention checksum name is unsafe."
        }
        $checksumPath = Join-Path $Root $checksumName
        if (-not (Test-Path -LiteralPath $checksumPath -PathType Leaf)) {
            continue
        }
        $checksumItem = Get-Item -LiteralPath $checksumPath -Force
        if (($checksumItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            continue
        }
        if (-not (Test-SamePath -Left (Split-Path $checksumPath -Parent) -Right $Root)) {
            throw "Retention checksum escaped BackupRoot."
        }
        $checksumText = (Get-Content -LiteralPath $checksumPath -Raw).Trim()
        $pairPattern = "^(?<hash>[0-9a-fA-F]{64})  $([Regex]::Escape($candidate.Name))$"
        $checksumMatch = [Regex]::Match($checksumText, $pairPattern)
        if (-not $checksumMatch.Success) {
            continue
        }
        $expectedHash = $checksumMatch.Groups["hash"].Value.ToLowerInvariant()
        $candidateHash = (Get-FileHash -LiteralPath $candidate.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($candidateHash -cne $expectedHash) {
            continue
        }
        Remove-Item -LiteralPath $candidate.FullName
        Remove-Item -LiteralPath $checksumPath
    }
}

$resolvedBackupRoot = Get-ValidatedBackupRoot -Path $BackupRoot
Assert-DatabaseValue -Name "DatabaseHost" -Value $DatabaseHost
Assert-DatabaseValue -Name "DatabaseName" -Value $DatabaseName
Assert-DatabaseValue -Name "DatabaseUser" -Value $DatabaseUser
if ($DatabaseName.Contains("=") -or $DatabaseName.Contains("://")) {
    throw "DatabaseName must be a plain database name, not a connection string."
}

$runToken = [Guid]::NewGuid().ToString("N")
$timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ", [Globalization.CultureInfo]::InvariantCulture)
$backupName = "frooshbin-pg-$timestamp-$runToken.dump"
if ($backupName -notmatch $backupNamePattern) {
    throw "Generated backup name is unsafe."
}
$finalDumpPath = Join-Path $resolvedBackupRoot $backupName
$finalChecksumPath = "$finalDumpPath.sha256"
$tempDumpPath = Join-Path $resolvedBackupRoot ".$backupName.tmp"
$tempChecksumPath = Join-Path $resolvedBackupRoot ".$backupName.sha256.tmp"
foreach ($path in @($finalDumpPath, $finalChecksumPath, $tempDumpPath, $tempChecksumPath)) {
    if (Test-Path -LiteralPath $path) {
        throw "Generated backup path already exists."
    }
    if (-not (Test-SamePath -Left (Split-Path $path -Parent) -Right $resolvedBackupRoot)) {
        throw "Generated backup path escaped BackupRoot."
    }
}

$pgDump = Get-PostgresTool -Name "pg_dump" -BinPath $PostgresBin
$pgRestore = Get-PostgresTool -Name "pg_restore" -BinPath $PostgresBin
$published = $false
try {
    & $pgDump "--format=custom" "--file=$tempDumpPath" "--host=$DatabaseHost" "--port=$DatabasePort" "--username=$DatabaseUser" "--dbname=$DatabaseName" "--no-password"
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL backup command failed."
    }
    if (-not (Test-Path -LiteralPath $tempDumpPath -PathType Leaf) -or (Get-Item -LiteralPath $tempDumpPath).Length -le 0) {
        throw "PostgreSQL backup output is empty."
    }

    & $pgRestore "--list" $tempDumpPath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL backup archive verification failed."
    }

    $hash = (Get-FileHash -LiteralPath $tempDumpPath -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText(
        $tempChecksumPath,
        "$hash  $backupName`n",
        [Text.Encoding]::ASCII
    )
    Move-Item -LiteralPath $tempDumpPath -Destination $finalDumpPath
    Move-Item -LiteralPath $tempChecksumPath -Destination $finalChecksumPath
    $published = $true
} finally {
    foreach ($path in @($tempDumpPath, $tempChecksumPath)) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Remove-Item -LiteralPath $path
        }
    }
    if (-not $published) {
        foreach ($path in @($finalDumpPath, $finalChecksumPath)) {
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                Remove-Item -LiteralPath $path
            }
        }
    }
}

Invoke-ExactRetention -Root $resolvedBackupRoot -Days $RetentionDays -CurrentBackup $finalDumpPath
[PSCustomObject]@{
    BackupFile = $finalDumpPath
    ChecksumFile = $finalChecksumPath
}
