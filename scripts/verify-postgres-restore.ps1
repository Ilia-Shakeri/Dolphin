[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupRoot,

    [Parameter(Mandatory = $true)]
    [string]$BackupFile,

    [Parameter(Mandatory = $true)]
    [string]$TargetHost,

    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 65535)]
    [int]$TargetPort,

    [Parameter(Mandatory = $true)]
    [string]$DatabaseUser,

    [string]$MaintenanceDatabase = "postgres",

    [string]$PostgresBin = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$backupNamePattern = "^dolphin-pg-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}[.]dump$"

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
    $sentinelPath = Join-Path $resolved ".dolphin-backup-root"
    if (-not (Test-Path -LiteralPath $sentinelPath)) {
        throw "BackupRoot sentinel is missing."
    }
    $sentinelItem = Get-Item -LiteralPath $sentinelPath -Force
    if (-not (Test-Path -LiteralPath $sentinelPath -PathType Leaf) -or
        ($sentinelItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        (Get-Content -LiteralPath $sentinelPath -Raw).Trim() -cne "DOLPHIN_BACKUP_ROOT_V1") {
        throw "BackupRoot sentinel value is invalid."
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

function Assert-NonEmpty {
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

$resolvedBackupRoot = Get-ValidatedBackupRoot -Path $BackupRoot
$targetAddress = $null
if (-not [Net.IPAddress]::TryParse($TargetHost, [ref]$targetAddress) -or -not [Net.IPAddress]::IsLoopback($targetAddress)) {
    throw "TargetHost must be a loopback IP literal."
}
if ($TargetPort -le 1024 -or $TargetPort -eq 5432) {
    throw "TargetPort must be a high disposable port and cannot be 5432."
}
Assert-NonEmpty -Name "DatabaseUser" -Value $DatabaseUser
Assert-NonEmpty -Name "MaintenanceDatabase" -Value $MaintenanceDatabase
if ($MaintenanceDatabase.Contains("=") -or $MaintenanceDatabase.Contains("://")) {
    throw "MaintenanceDatabase must be a plain database name, not a connection string."
}

if (-not (Test-Path -LiteralPath $BackupFile -PathType Leaf)) {
    throw "BackupFile must be an existing file."
}
$resolvedBackupFile = (Resolve-Path -LiteralPath $BackupFile).Path
$backupItem = Get-Item -LiteralPath $resolvedBackupFile -Force
if (($backupItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "BackupFile cannot be a link."
}
if (-not (Test-SamePath -Left (Split-Path $resolvedBackupFile -Parent) -Right $resolvedBackupRoot)) {
    throw "BackupFile must be directly inside BackupRoot."
}
$backupLeaf = Split-Path $resolvedBackupFile -Leaf
if ($backupLeaf -notmatch $backupNamePattern) {
    throw "BackupFile name does not match the Dolphin backup pattern."
}
$checksumPath = "$resolvedBackupFile.sha256"
if (-not (Test-Path -LiteralPath $checksumPath -PathType Leaf)) {
    throw "Backup checksum sidecar is missing."
}
$resolvedChecksumPath = (Resolve-Path -LiteralPath $checksumPath).Path
$checksumItem = Get-Item -LiteralPath $resolvedChecksumPath -Force
if (($checksumItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "Backup checksum cannot be a link."
}
if (-not (Test-SamePath -Left (Split-Path $resolvedChecksumPath -Parent) -Right $resolvedBackupRoot)) {
    throw "Backup checksum must be directly inside BackupRoot."
}
$checksumText = (Get-Content -LiteralPath $resolvedChecksumPath -Raw).Trim()
$sidecarPattern = "^(?<hash>[0-9a-fA-F]{64})  $([Regex]::Escape($backupLeaf))$"
if ($checksumText -notmatch $sidecarPattern) {
    throw "Backup checksum sidecar format is invalid."
}
$expectedHash = $Matches["hash"].ToLowerInvariant()
$actualHash = (Get-FileHash -LiteralPath $resolvedBackupFile -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -cne $expectedHash) {
    throw "Backup checksum verification failed."
}

$pgRestore = Get-PostgresTool -Name "pg_restore" -BinPath $PostgresBin
$psql = Get-PostgresTool -Name "psql" -BinPath $PostgresBin
$createDb = Get-PostgresTool -Name "createdb" -BinPath $PostgresBin
$dropDb = Get-PostgresTool -Name "dropdb" -BinPath $PostgresBin

& $pgRestore "--list" $resolvedBackupFile | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL backup archive verification failed."
}

$runToken = [Guid]::NewGuid().ToString("N")
$databaseName = "dolphin_restore_verify_$runToken"
$databaseNamePattern = "^dolphin_restore_verify_[0-9a-f]{32}$"
if ($databaseName -notmatch $databaseNamePattern) {
    throw "Generated restore database name is unsafe."
}
$connectionArguments = @(
    "--host=$TargetHost",
    "--port=$TargetPort",
    "--username=$DatabaseUser",
    "--no-password"
)
$created = $false
$verified = $false
try {
    $existenceQuery = "SELECT 1 FROM pg_database WHERE datname = '$databaseName';"
    $existingOutput = & $psql @connectionArguments "--dbname=$MaintenanceDatabase" "--tuples-only" "--no-align" "--set=ON_ERROR_STOP=1" "--command=$existenceQuery"
    if ($LASTEXITCODE -ne 0) {
        throw "Disposable target existence check failed."
    }
    if ((($existingOutput | ForEach-Object { [string]$_ }) -join "").Trim()) {
        throw "Disposable target database already exists."
    }

    & $createDb @connectionArguments "--maintenance-db=$MaintenanceDatabase" $databaseName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Disposable target database creation failed."
    }
    $created = $true

    & $pgRestore @connectionArguments "--dbname=$databaseName" "--no-owner" "--no-privileges" "--exit-on-error" $resolvedBackupFile | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Disposable database restore failed."
    }

    $verificationSql = Join-Path $PSScriptRoot "verify-postgres-schema.sql"
    if (-not (Test-Path -LiteralPath $verificationSql -PathType Leaf)) {
        throw "Restore schema contract is missing."
    }
    $verificationSqlItem = Get-Item -LiteralPath $verificationSql -Force
    if (($verificationSqlItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Restore schema contract cannot be a link."
    }
    $verificationOutput = & $psql @connectionArguments "--dbname=$databaseName" "--tuples-only" "--no-align" "--set=ON_ERROR_STOP=1" "--file=$verificationSql"
    if ($LASTEXITCODE -ne 0 -or (($verificationOutput | ForEach-Object { [string]$_ }) -join "").Trim() -ne "1") {
        throw "Restored Dolphin schema verification failed."
    }
    $verified = $true
} finally {
    if ($created) {
        $expectedDatabaseName = "dolphin_restore_verify_$runToken"
        if ($databaseName -cne $expectedDatabaseName -or $databaseName -notmatch $databaseNamePattern) {
            throw "Unsafe disposable database cleanup target."
        }
        & $dropDb @connectionArguments "--maintenance-db=$MaintenanceDatabase" "--force" $databaseName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Disposable restore database cleanup failed."
        }
    }
}

if (-not $verified) {
    throw "Disposable restore verification did not complete."
}
Write-Output "Disposable restore verification passed."
