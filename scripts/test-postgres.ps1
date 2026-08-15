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
$restoreDatabaseName = "restore_kariz_$runToken"
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
$restoreDatabaseCreated = $false
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
    "KARIZ_PG_RESTORE",
    "KARIZ_PG_RESTORE_TOKEN",
    "KARIZ_PG_RESTORE_HOST",
    "KARIZ_PG_RESTORE_PORT",
    "KARIZ_PG_RESTORE_NAME",
    "KARIZ_PG_RESTORE_USER",
    "KARIZ_PG_RESTORE_PASSWORD",
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
    $pgRestore = Join-Path $resolvedBin "pg_restore.exe"
} else {
    $initdb = (Get-Command initdb -ErrorAction Stop).Source
    $pgCtl = (Get-Command pg_ctl -ErrorAction Stop).Source
    $psql = (Get-Command psql -ErrorAction Stop).Source
    $createdb = (Get-Command createdb -ErrorAction Stop).Source
    $pgDump = (Get-Command pg_dump -ErrorAction Stop).Source
    $pgRestore = (Get-Command pg_restore -ErrorAction Stop).Source
    $resolvedBin = Split-Path -Parent $psql
}
$bash = (Get-Command $BashCommand -ErrorAction Stop).Source

foreach ($tool in @($initdb, $pgCtl, $psql, $createdb, $pgDump, $pgRestore, $bash, $bootstrapPath, $schemaProofPath, $privilegeProofPath)) {
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
        throw "Required isolated PostgreSQL proof tool or script not found."
    }
}

function Invoke-ContractSql {
    param(
        [Parameter(Mandatory = $true)][string]$User,
        [Parameter(Mandatory = $true)][string]$Password,
        [Parameter(Mandatory = $true)][string]$Sql,
        [string]$Database = "",
        [bool]$ShouldPass = $true
    )

    if (-not $Database) { $Database = $contractDatabaseName }
    $previousPassword = [Environment]::GetEnvironmentVariable("PGPASSWORD", "Process")
    try {
        $env:PGPASSWORD = $Password
        & $psql `
            --host=127.0.0.1 `
            --port=$port `
            --username=$User `
            --dbname=$Database `
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

function Assert-EphemeralDatabaseName {
    <#
        Only this run's disposable databases may ever be created or dropped.
        The name must carry this run's random token, so a stale token, a typo,
        or an operator-supplied name is refused instead of being destroyed.
    #>
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Name)

    if ($Name -notmatch '^(test|contract|restore)_kariz_[a-f0-9]{32}$') {
        throw "Refusing to touch a database that is not an ephemeral Kariz proof database."
    }
    if (-not $Name.EndsWith($runToken, [StringComparison]::Ordinal)) {
        throw "Refusing to touch an ephemeral database from a different harness run."
    }
}

function Get-ScalarSql {
    <#
        Run one read-only query and return the single value it produced.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$User,
        [Parameter(Mandatory = $true)][string]$Password,
        [Parameter(Mandatory = $true)][string]$Database,
        [Parameter(Mandatory = $true)][string]$Sql
    )

    $previousPassword = [Environment]::GetEnvironmentVariable("PGPASSWORD", "Process")
    try {
        $env:PGPASSWORD = $Password
        $output = & $psql `
            --host=127.0.0.1 `
            --port=$port `
            --username=$User `
            --dbname=$Database `
            --no-password `
            --quiet `
            --tuples-only `
            --no-align `
            --set=ON_ERROR_STOP=1 `
            --command=$Sql
        if ($LASTEXITCODE -ne 0) {
            throw "PostgreSQL read-only probe failed."
        }
    } finally {
        [Environment]::SetEnvironmentVariable("PGPASSWORD", $previousPassword, "Process")
    }
    return ($output | Out-String).Trim()
}

function Assert-ScalarSql {
    param(
        [Parameter(Mandatory = $true)][string]$User,
        [Parameter(Mandatory = $true)][string]$Password,
        [Parameter(Mandatory = $true)][string]$Database,
        [Parameter(Mandatory = $true)][string]$Sql,
        [Parameter(Mandatory = $true)][string]$Expected,
        [Parameter(Mandatory = $true)][string]$Because
    )

    $actual = Get-ScalarSql -User $User -Password $Password -Database $Database -Sql $Sql
    if ($actual -ne $Expected) {
        throw "$Because (expected '$Expected', got '$actual')."
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
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "UPDATE communications_inboundsms SET processing_state = processing_state WHERE FALSE" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "DELETE FROM communications_inboundsms WHERE FALSE" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "DELETE FROM sales_interaction WHERE FALSE" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "UPDATE sales_postalstatushistory SET reason = reason WHERE FALSE" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "DELETE FROM sales_salesdocument WHERE FALSE" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "DELETE FROM sales_productcategory WHERE FALSE" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "UPDATE aftersales_aftersaleshistory SET reason = reason WHERE FALSE" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "DELETE FROM aftersales_aftersalesrequest WHERE FALSE" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "CREATE TABLE public.kariz_forbidden_table (id integer)" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "SELECT public.kariz_contract_probe()" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "SELECT * FROM public.kariz_future_table" -ShouldPass $false
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword -Sql "SELECT public.kariz_future_probe()" -ShouldPass $false

    Invoke-ContractSql -User $backupUser -Password $backupPassword -Sql "SELECT * FROM public.kariz_future_table"
    Invoke-ContractSql -User $backupUser -Password $backupPassword -Sql "INSERT INTO django_session (session_key, session_data, expire_date) VALUES ('backup-denied', '', CURRENT_TIMESTAMP)" -ShouldPass $false
    Invoke-ContractSql -User $backupUser -Password $backupPassword -Sql "CREATE TABLE public.kariz_backup_forbidden (id integer)" -ShouldPass $false
    Invoke-ContractSql -User $backupUser -Password $backupPassword -Sql "SELECT public.kariz_future_probe()" -ShouldPass $false

    # Deterministic synthetic rows across related Tier-A models, written before
    # the dump so the archive carries them and the restore can be checked for
    # real content rather than only for a zero exit status.
    $sentinelSource = @'
from accounts.models import User
from sales.services import create_customer_with_phone

admin = User.objects.create_user(
    username="restore_sentinel_admin",
    password="Sentinel-Restore-Proof-741!",
    role=User.Role.PLATFORM_ADMIN,
)
customer = create_customer_with_phone(
    actor=admin,
    full_name="RESTORE SENTINEL CUSTOMER",
    phone="09120000001",
    city="SentinelCity",
)
print("SENTINEL_OK")
'@
    $sentinelOutput = & $PythonCommand $managePath shell --settings=config.postgres_contract_settings -c $sentinelSource
    if ($LASTEXITCODE -ne 0 -or (($sentinelOutput | Out-String) -notmatch "SENTINEL_OK")) {
        throw "PostgreSQL restore sentinel data creation failed."
    }

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

    # ---- Native restore proof -------------------------------------------------
    # The dump above is only half of a recovery guarantee. Restore the archive
    # with pg_restore into a second, separately named ephemeral database and
    # prove the result is a usable application database.
    Assert-EphemeralDatabaseName -Name $restoreDatabaseName
    if ($restoreDatabaseName -in @("postgres", "template0", "template1", $contractDatabaseName, $databaseName)) {
        throw "Restore target must be a new, separate database."
    }

    & $createdb `
        --host=127.0.0.1 `
        --port=$port `
        --username=$databaseUser `
        --owner=$migrationUser `
        --no-password `
        $restoreDatabaseName
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL restore database creation failed." }
    $restoreDatabaseCreated = $true

    $previousPassword = [Environment]::GetEnvironmentVariable("PGPASSWORD", "Process")
    try {
        $env:PGPASSWORD = $migrationPassword
        & $pgRestore `
            --host=127.0.0.1 `
            --port=$port `
            --username=$migrationUser `
            --dbname=$restoreDatabaseName `
            --no-password `
            --exit-on-error `
            --single-transaction `
            $contractDumpPath
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL native pg_restore failed." }

        # Schema contract must hold in the restored database exactly as it does
        # in the source database.
        & $psql `
            --host=127.0.0.1 `
            --port=$port `
            --username=$migrationUser `
            --dbname=$restoreDatabaseName `
            --no-password `
            --quiet `
            --set=ON_ERROR_STOP=1 `
            --output=NUL `
            --file=$schemaProofPath
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL restored-schema proof failed." }
    } finally {
        [Environment]::SetEnvironmentVariable("PGPASSWORD", $previousPassword, "Process")
    }

    $sourceMigrations = Get-ScalarSql -User $migrationUser -Password $migrationPassword `
        -Database $contractDatabaseName `
        -Sql "SELECT COUNT(*)||':'||COALESCE(MD5(STRING_AGG(app||'/'||name, ',' ORDER BY app, name)), '') FROM django_migrations"
    Assert-ScalarSql -User $migrationUser -Password $migrationPassword `
        -Database $restoreDatabaseName `
        -Sql "SELECT COUNT(*)||':'||COALESCE(MD5(STRING_AGG(app||'/'||name, ',' ORDER BY app, name)), '') FROM django_migrations" `
        -Expected $sourceMigrations `
        -Because "Restored migration state does not match the source database"

    Assert-ScalarSql -User $migrationUser -Password $migrationPassword `
        -Database $restoreDatabaseName `
        -Sql "SELECT city FROM sales_customer WHERE full_name = 'RESTORE SENTINEL CUSTOMER'" `
        -Expected "SentinelCity" `
        -Because "Restored sentinel customer row is missing or altered"
    Assert-ScalarSql -User $migrationUser -Password $migrationPassword `
        -Database $restoreDatabaseName `
        -Sql "SELECT p.normalized_phone FROM sales_customerphone p JOIN sales_customer c ON c.id = p.customer_id WHERE c.full_name = 'RESTORE SENTINEL CUSTOMER'" `
        -Expected "+989120000001" `
        -Because "Restored sentinel relationship across customer and phone is broken"
    Assert-ScalarSql -User $migrationUser -Password $migrationPassword `
        -Database $restoreDatabaseName `
        -Sql "SELECT COUNT(*) FROM accounts_user WHERE username = 'restore_sentinel_admin'" `
        -Expected "1" `
        -Because "Restored sentinel user row is missing"

    # The runtime login must be able to use the restored database without any
    # added privilege, including through the ORM.
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword `
        -Sql "SELECT COUNT(*) FROM sales_customer" -Database $restoreDatabaseName
    $restoreSessionKey = "restore$runToken"
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword `
        -Database $restoreDatabaseName `
        -Sql "INSERT INTO django_session (session_key, session_data, expire_date) VALUES ('$restoreSessionKey', '', CURRENT_TIMESTAMP + INTERVAL '1 hour'); UPDATE django_session SET session_data = 'x' WHERE session_key = '$restoreSessionKey'; DELETE FROM django_session WHERE session_key = '$restoreSessionKey'"
    Invoke-ContractSql -User $applicationUser -Password $applicationPassword `
        -Database $restoreDatabaseName `
        -Sql "CREATE TABLE public.kariz_restore_forbidden (id integer)" -ShouldPass $false

    $env:KARIZ_PG_RESTORE = "1"
    $env:KARIZ_PG_RESTORE_TOKEN = $runToken
    $env:KARIZ_PG_RESTORE_HOST = "127.0.0.1"
    $env:KARIZ_PG_RESTORE_PORT = [string]$port
    $env:KARIZ_PG_RESTORE_NAME = $restoreDatabaseName
    $env:KARIZ_PG_RESTORE_USER = $applicationUser
    $env:KARIZ_PG_RESTORE_PASSWORD = $applicationPassword
    & $PythonCommand $managePath showmigrations --settings=config.postgres_restore_settings | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Application role could not read the restored database through Django."
    }

    # Restore must not quietly promote the runtime login.
    Assert-ScalarSql -User $databaseUser -Password $initPassword -Database $restoreDatabaseName `
        -Sql "SELECT rolsuper::text||rolcreatedb::text||rolcreaterole::text||rolbypassrls::text FROM pg_roles WHERE rolname = '$applicationUser'" `
        -Expected "falsefalsefalsefalse" `
        -Because "Application role gained cluster privileges through restore"
    Assert-ScalarSql -User $databaseUser -Password $initPassword -Database $restoreDatabaseName `
        -Sql "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = '$restoreDatabaseName'" `
        -Expected $migrationUser `
        -Because "Restored database owner is not the migration role"
    Assert-ScalarSql -User $databaseUser -Password $initPassword -Database $restoreDatabaseName `
        -Sql "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'public'" `
        -Expected $migrationUser `
        -Because "Restored public schema owner is not the migration role"
    Assert-ScalarSql -User $databaseUser -Password $initPassword -Database $restoreDatabaseName `
        -Sql "SELECT COUNT(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid JOIN pg_roles g ON g.oid = m.member WHERE g.rolname = '$applicationUser'" `
        -Expected "0" `
        -Because "Application role inherited another role through restore"

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
    if ($started -and $restoreDatabaseCreated) {
        # Drop only this run's restore database, and only after the name passes
        # the same ephemeral-name guard used to create it.
        try {
            Assert-EphemeralDatabaseName -Name $restoreDatabaseName
            $previousPassword = [Environment]::GetEnvironmentVariable("PGPASSWORD", "Process")
            try {
                $env:PGPASSWORD = $initPassword
                & $psql `
                    --host=127.0.0.1 `
                    --port=$port `
                    --username=$databaseUser `
                    --dbname=postgres `
                    --no-password `
                    --quiet `
                    --set=ON_ERROR_STOP=1 `
                    --output=NUL `
                    --command="DROP DATABASE IF EXISTS $restoreDatabaseName WITH (FORCE)"
            } finally {
                [Environment]::SetEnvironmentVariable("PGPASSWORD", $previousPassword, "Process")
            }
        } catch {
            Write-Warning "Restore database cleanup was refused or failed; the temporary cluster is removed below."
        }
    }

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
