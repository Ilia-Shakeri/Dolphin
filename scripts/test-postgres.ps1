[CmdletBinding()]
param(
    [string]$PostgresBin = "",
    [string]$PythonCommand = "python",
    [string]$BashCommand = "bash"
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
$contractDatabaseName = "contract_kariz_$runToken"
$migrationUser = "kariz_migration_$runToken"
$applicationUser = "kariz_app_$runToken"
$backupUser = "kariz_backup_$runToken"
$initPassword = "Initial!$runToken"
$migrationPassword = "Migration!$runToken"
$applicationPassword = "Application!$runToken"
$backupPassword = "Backup!$runToken"
$contractDumpPath = Join-Path $dataPath "contract-proof.dump"
$bootstrapPath = Join-Path $repoPath "scripts\bootstrap-postgres.sh"
$schemaProofPath = Join-Path $repoPath "scripts\verify-postgres-schema.sql"
$privilegeProofPath = Join-Path $repoPath "scripts\verify-postgres-privileges.sql"
$started = $false
$testVariables = @(
    "KARIZ_PG_TEST",
    "KARIZ_PG_TEST_TOKEN",
    "KARIZ_PG_TEST_HOST",
    "KARIZ_PG_TEST_PORT",
    "KARIZ_PG_TEST_NAME",
    "KARIZ_PG_TEST_USER",
    "KARIZ_PG_CONTRACT",
    "KARIZ_PG_CONTRACT_TOKEN",
    "KARIZ_PG_CONTRACT_HOST",
    "KARIZ_PG_CONTRACT_PORT",
    "KARIZ_PG_CONTRACT_NAME",
    "KARIZ_PG_CONTRACT_USER",
    "KARIZ_PG_CONTRACT_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_INIT_USER",
    "POSTGRES_INIT_PASSWORD",
    "POSTGRES_MIGRATION_USER",
    "POSTGRES_MIGRATION_PASSWORD",
    "POSTGRES_APP_USER",
    "POSTGRES_APP_PASSWORD",
    "POSTGRES_BACKUP_USER",
    "POSTGRES_BACKUP_PASSWORD",
    "PGPASSWORD"
)
$savedValues = @{}
$savedPath = [Environment]::GetEnvironmentVariable("PATH", "Process")

foreach ($name in $testVariables) {
    $savedValues[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

if ($PostgresBin) {
    $resolvedBin = (Resolve-Path -LiteralPath $PostgresBin).Path
    $initdb = Join-Path $resolvedBin "initdb.exe"
    $pgCtl = Join-Path $resolvedBin "pg_ctl.exe"
    $psql = Join-Path $resolvedBin "psql.exe"
    $createdb = Join-Path $resolvedBin "createdb.exe"
    $pgDump = Join-Path $resolvedBin "pg_dump.exe"
} else {
    $initdb = (Get-Command initdb -ErrorAction Stop).Source
    $pgCtl = (Get-Command pg_ctl -ErrorAction Stop).Source
    $psql = (Get-Command psql -ErrorAction Stop).Source
    $createdb = (Get-Command createdb -ErrorAction Stop).Source
    $pgDump = (Get-Command pg_dump -ErrorAction Stop).Source
    $resolvedBin = Split-Path -Parent $psql
}
$bash = (Get-Command $BashCommand -ErrorAction Stop).Source

foreach ($tool in @($initdb, $pgCtl, $psql, $createdb, $pgDump, $bash, $bootstrapPath, $schemaProofPath, $privilegeProofPath)) {
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
        throw "Required isolated PostgreSQL proof tool or script not found."
    }
}

function Invoke-ContractSql {
    param(
        [Parameter(Mandatory = $true)][string]$User,
        [Parameter(Mandatory = $true)][string]$Password,
        [Parameter(Mandatory = $true)][string]$Sql,
        [bool]$ShouldPass = $true
    )

    $previousPassword = [Environment]::GetEnvironmentVariable("PGPASSWORD", "Process")
    try {
        $env:PGPASSWORD = $Password
        & $psql `
            --host=127.0.0.1 `
            --port=$port `
            --username=$User `
            --dbname=$contractDatabaseName `
            --no-password `
            --quiet `
            --set=ON_ERROR_STOP=1 `
            --output=NUL `
            --command=$Sql
        $passed = $LASTEXITCODE -eq 0
    } finally {
        [Environment]::SetEnvironmentVariable("PGPASSWORD", $previousPassword, "Process")
    }
    if ($passed -ne $ShouldPass) {
        throw "PostgreSQL privilege probe returned an unexpected result."
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
    $env:PATH = "$resolvedBin;$savedPath"

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

    & $createdb `
        --host=127.0.0.1 `
        --port=$port `
        --username=$databaseUser `
        --no-password `
        $contractDatabaseName
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL contract database creation failed." }

    $env:POSTGRES_HOST = "127.0.0.1"
    $env:POSTGRES_PORT = [string]$port
    $env:POSTGRES_DB = $contractDatabaseName
    $env:POSTGRES_INIT_USER = $databaseUser
    $env:POSTGRES_INIT_PASSWORD = $initPassword
    $env:POSTGRES_MIGRATION_USER = $migrationUser
    $env:POSTGRES_MIGRATION_PASSWORD = $migrationPassword
    $env:POSTGRES_APP_USER = $applicationUser
    $env:POSTGRES_APP_PASSWORD = $applicationPassword
    $env:POSTGRES_BACKUP_USER = $backupUser
    $env:POSTGRES_BACKUP_PASSWORD = $backupPassword

    & $bash $bootstrapPath
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL pre-migration role bootstrap failed." }

    $env:KARIZ_PG_CONTRACT = "1"
    $env:KARIZ_PG_CONTRACT_TOKEN = $runToken
    $env:KARIZ_PG_CONTRACT_HOST = "127.0.0.1"
    $env:KARIZ_PG_CONTRACT_PORT = [string]$port
    $env:KARIZ_PG_CONTRACT_NAME = $contractDatabaseName
    $env:KARIZ_PG_CONTRACT_USER = $migrationUser
    $env:KARIZ_PG_CONTRACT_PASSWORD = $migrationPassword

    & $PythonCommand $managePath migrate --noinput --settings=config.postgres_contract_settings
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL contract migrations failed." }

    Invoke-ContractSql `
        -User $migrationUser `
        -Password $migrationPassword `
        -Sql "CREATE FUNCTION public.kariz_contract_probe() RETURNS integer LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'"

    & $bash $bootstrapPath
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL post-migration privilege finalizer failed." }

    $previousPassword = [Environment]::GetEnvironmentVariable("PGPASSWORD", "Process")
    try {
        $env:PGPASSWORD = $migrationPassword
        & $psql `
            --host=127.0.0.1 `
            --port=$port `
            --username=$migrationUser `
            --dbname=$contractDatabaseName `
            --no-password `
            --quiet `
            --set=ON_ERROR_STOP=1 `
            --output=NUL `
            --file=$schemaProofPath
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL schema proof failed." }

        $env:PGPASSWORD = $initPassword
        & $psql `
            --host=127.0.0.1 `
            --port=$port `
            --username=$databaseUser `
            --dbname=$contractDatabaseName `
            --no-password `
            --quiet `
            --set=ON_ERROR_STOP=1 `
            --set="app_user=$applicationUser" `
            --set="backup_user=$backupUser" `
            --set="migration_user=$migrationUser" `
            --output=NUL `
            --file=$privilegeProofPath
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL exact privilege proof failed." }
    } finally {
        [Environment]::SetEnvironmentVariable("PGPASSWORD", $previousPassword, "Process")
    }

    Invoke-ContractSql `
        -User $migrationUser `
        -Password $migrationPassword `
        -Sql "CREATE TABLE public.kariz_future_table (id integer); CREATE SEQUENCE public.kariz_future_sequence; CREATE FUNCTION public.kariz_future_probe() RETURNS integer LANGUAGE sql AS 'SELECT 1'"

    $sessionKey = "acl$runToken"
    Invoke-ContractSql `
        -User $applicationUser `
        -Password $applicationPassword `
        -Sql "INSERT INTO django_session (session_key, session_data, expire_date) VALUES ('$sessionKey', '', CURRENT_TIMESTAMP + INTERVAL '1 hour'); UPDATE django_session SET session_data = 'x' WHERE session_key = '$sessionKey'; DELETE FROM django_session WHERE session_key = '$sessionKey'; SELECT COUNT(*) FROM django_migrations"
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "UPDATE auditlog_activitylog SET operation = operation WHERE FALSE" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "DELETE FROM sales_interaction WHERE FALSE" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "CREATE TABLE public.kariz_forbidden_table (id integer)" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "SELECT public.kariz_contract_probe()" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "SELECT * FROM public.kariz_future_table" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "SELECT public.kariz_future_probe()" -ShouldPass $false

    Invoke-ContractSql -User $backupUser -Password $backupPassword -Sql "SELECT * FROM public.kariz_future_table"
    Invoke-ContractSql -User $backupUser -Password $backupPassword -Sql "INSERT INTO django_session (session_key, session_data, expire_date) VALUES ('backup-denied', '', CURRENT_TIMESTAMP)" -ShouldPass $false
    Invoke-ContractSql -User $backupUser -Password $backupPassword -Sql "CREATE TABLE public.kariz_backup_forbidden (id integer)" -ShouldPass $false
    Invoke-ContractSql -User $backupUser -Password $backupPassword -Sql "SELECT public.kariz_future_probe()" -ShouldPass $false

    $previousPassword = [Environment]::GetEnvironmentVariable("PGPASSWORD", "Process")
    try {
        $env:PGPASSWORD = $backupPassword
        & $pgDump `
            --host=127.0.0.1 `
            --port=$port `
            --username=$backupUser `
            --dbname=$contractDatabaseName `
            --no-password `
            --format=custom `
            --file=$contractDumpPath
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $contractDumpPath -PathType Leaf)) {
            throw "PostgreSQL backup-role dump proof failed."
        }
    } finally {
        [Environment]::SetEnvironmentVariable("PGPASSWORD", $previousPassword, "Process")
    }

    Invoke-ContractSql `
        -User $databaseUser `
        -Password $initPassword `
        -Sql "CREATE TABLE public.kariz_rollback_probe (id integer); CREATE TABLE public.kariz_unsafe_owner (id integer); ALTER TABLE public.kariz_unsafe_owner OWNER TO $applicationUser"
    & $bash $bootstrapPath
    if ($LASTEXITCODE -eq 0) { throw "PostgreSQL rollback injection did not fail closed." }

    $previousPassword = [Environment]::GetEnvironmentVariable("PGPASSWORD", "Process")
    try {
        $env:PGPASSWORD = $initPassword
        $ownerOutput = & $psql `
            --host=127.0.0.1 `
            --port=$port `
            --username=$databaseUser `
            --dbname=$contractDatabaseName `
            --no-password `
            --quiet `
            --tuples-only `
            --no-align `
            --set=ON_ERROR_STOP=1 `
            --command="SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = 'public.kariz_rollback_probe'::regclass"
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL rollback owner proof failed." }
        $rollbackOwner = ($ownerOutput | Out-String).Trim()
        if ($rollbackOwner -ne $databaseUser) {
            throw "PostgreSQL owner changes did not roll back after injected failure."
        }
    } finally {
        [Environment]::SetEnvironmentVariable("PGPASSWORD", $previousPassword, "Process")
    }

    $rogueRole = "kariz_rogue_$runToken"
    Invoke-ContractSql `
        -User $databaseUser `
        -Password $initPassword `
        -Sql "CREATE ROLE $rogueRole LOGIN; GRANT $applicationUser TO $rogueRole"
    & $bash $bootstrapPath
    if ($LASTEXITCODE -eq 0) {
        throw "PostgreSQL reverse role-membership injection did not fail closed."
    }

    $previousPassword = [Environment]::GetEnvironmentVariable("PGPASSWORD", "Process")
    try {
        $env:PGPASSWORD = $initPassword
        & $psql `
            --host=127.0.0.1 `
            --port=$port `
            --username=$databaseUser `
            --dbname=$contractDatabaseName `
            --no-password `
            --quiet `
            --set=ON_ERROR_STOP=1 `
            --set="app_user=$applicationUser" `
            --set="backup_user=$backupUser" `
            --set="migration_user=$migrationUser" `
            --output=NUL `
            --file=$privilegeProofPath
        if ($LASTEXITCODE -eq 0) {
            throw "PostgreSQL privilege proof accepted reverse role membership."
        }
    } finally {
        [Environment]::SetEnvironmentVariable("PGPASSWORD", $previousPassword, "Process")
    }
    Invoke-ContractSql `
        -User $databaseUser `
        -Password $initPassword `
        -Sql "REVOKE $applicationUser FROM $rogueRole; DROP ROLE $rogueRole"
} finally {
    if ($started) {
        & $pgCtl -D $dataPath -m fast -w stop
    }

    foreach ($name in $testVariables) {
        [Environment]::SetEnvironmentVariable($name, $savedValues[$name], "Process")
    }
    [Environment]::SetEnvironmentVariable("PATH", $savedPath, "Process")

    if ($dataPath.StartsWith($safePrefix, [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $dataPath -Leaf) -eq "kariz-pgtest-$runToken") {
        if (Test-Path -LiteralPath $dataPath) {
            Remove-Item -LiteralPath $dataPath -Recurse -Force
        }
    } else {
        throw "Unsafe PostgreSQL test cleanup path."
    }
}
