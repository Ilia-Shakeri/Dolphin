[CmdletBinding()]
param(
    [string]$PostgresBin = "",
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
$runToken = [Guid]::NewGuid().ToString("N")
$repoPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$managePath = Join-Path $repoPath "manage.py"
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$dataPath = [IO.Path]::GetFullPath((Join-Path $tempRoot "kariz-pgtest-$runToken"))
$safePrefix = [IO.Path]::GetFullPath((Join-Path $tempRoot "kariz-pgtest-"))
$logPath = Join-Path $dataPath "postgres.log"
$databaseName = "test_kariz_$runToken"
$databaseUser = "kariz_test_admin"
$started = $false
$testVariables = @(
    "KARIZ_PG_TEST",
    "KARIZ_PG_TEST_TOKEN",
    "KARIZ_PG_TEST_HOST",
    "KARIZ_PG_TEST_PORT",
    "KARIZ_PG_TEST_NAME",
    "KARIZ_PG_TEST_USER"
)
$savedValues = @{}

foreach ($name in $testVariables) {
    $savedValues[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

if ($PostgresBin) {
    $resolvedBin = (Resolve-Path -LiteralPath $PostgresBin).Path
    $initdb = Join-Path $resolvedBin "initdb.exe"
    $pgCtl = Join-Path $resolvedBin "pg_ctl.exe"
} else {
    $initdb = (Get-Command initdb -ErrorAction Stop).Source
    $pgCtl = (Get-Command pg_ctl -ErrorAction Stop).Source
}

foreach ($tool in @($initdb, $pgCtl)) {
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
        throw "Required PostgreSQL tool not found."
    }
}

$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = ([Net.IPEndPoint]$listener.LocalEndpoint).Port
$listener.Stop()
if ($port -eq 5432 -or $port -le 1024) {
    throw "Safe high test port was not found."
}
if (-not $dataPath.StartsWith($safePrefix, [StringComparison]::OrdinalIgnoreCase) -or (Split-Path $dataPath -Leaf) -ne "kariz-pgtest-$runToken") {
    throw "Unsafe PostgreSQL test data path."
}

try {
    New-Item -ItemType Directory -Path $dataPath | Out-Null
    & $initdb -D $dataPath -U $databaseUser -A trust --no-locale --encoding=UTF8
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL test cluster init failed."
    }

    & $pgCtl -D $dataPath -l $logPath -o "-p $port -h 127.0.0.1" -w start
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL test cluster start failed."
    }
    $started = $true

    $env:KARIZ_PG_TEST = "1"
    $env:KARIZ_PG_TEST_TOKEN = $runToken
    $env:KARIZ_PG_TEST_HOST = "127.0.0.1"
    $env:KARIZ_PG_TEST_PORT = [string]$port
    $env:KARIZ_PG_TEST_NAME = $databaseName
    $env:KARIZ_PG_TEST_USER = $databaseUser

    & $PythonCommand $managePath check --settings=config.postgres_test_settings
    if ($LASTEXITCODE -ne 0) { throw "Django check failed." }
    & $PythonCommand $managePath makemigrations --check --dry-run --settings=config.postgres_test_settings
    if ($LASTEXITCODE -ne 0) { throw "Migration drift check failed." }
    & $PythonCommand $managePath test --settings=config.postgres_test_settings --noinput -v 1
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL tests failed." }
} finally {
    if ($started) {
        & $pgCtl -D $dataPath -m fast -w stop
    }

    foreach ($name in $testVariables) {
        [Environment]::SetEnvironmentVariable($name, $savedValues[$name], "Process")
    }

    if ($dataPath.StartsWith($safePrefix, [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $dataPath -Leaf) -eq "kariz-pgtest-$runToken") {
        if (Test-Path -LiteralPath $dataPath) {
            Remove-Item -LiteralPath $dataPath -Recurse -Force
        }
    } else {
        throw "Unsafe PostgreSQL test cleanup path."
    }
}
