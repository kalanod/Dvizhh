param(
    [string]$PostgresImage = 'dvizh-postgres:latest',
    [string]$MinioImage = 'dvizh-minio:latest'
)

$ErrorActionPreference = 'Stop'
$testPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $testPython)) { throw 'Run uv sync --locked in backend first.' }
$suffix = [guid]::NewGuid().ToString('N')
$testDatabaseId = $null
$testStorageId = $null
$previousEnvironment = @{}
foreach ($name in @('DATABASE_URL', 'TEST_DATABASE_URL', 'TEST_MINIO_ENDPOINT')) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
Push-Location $PSScriptRoot
try {
    $testDatabaseId = docker run --detach --rm --name "dvizh-media-test-db-$suffix" `
        --env POSTGRES_DB=dvizh_media_test --env POSTGRES_USER=media_test `
        --env POSTGRES_PASSWORD=media-test-password --env RECSYS_READER_PASSWORD=media-test-reader `
        --publish '127.0.0.1::5432' $PostgresImage
    if ($LASTEXITCODE -ne 0 -or $testDatabaseId -notmatch '^[a-f0-9]{64}$') {
        $testDatabaseId = $null
        throw 'Could not start test PostgreSQL.'
    }
    $testStorageId = docker run --detach --rm --name "dvizh-media-test-store-$suffix" `
        --env MINIO_ROOT_USER=media_test --env MINIO_ROOT_PASSWORD=media-test-password `
        --publish '127.0.0.1::9000' $MinioImage server /data --console-address ':9001'
    if ($LASTEXITCODE -ne 0 -or $testStorageId -notmatch '^[a-f0-9]{64}$') {
        $testStorageId = $null
        throw 'Could not start test MinIO.'
    }
    $mapping = docker port $testDatabaseId 5432/tcp
    if ($LASTEXITCODE -ne 0 -or $mapping -notmatch '^127\.0\.0\.1:(\d+)$') {
        throw 'Unexpected test database port.'
    }
    $databasePort = $Matches[1]
    $mapping = docker port $testStorageId 9000/tcp
    if ($LASTEXITCODE -ne 0 -or $mapping -notmatch '^127\.0\.0\.1:(\d+)$') {
        throw 'Unexpected test storage port.'
    }
    $storagePort = $Matches[1]
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        docker exec $testDatabaseId pg_isready -h 127.0.0.1 -U media_test -d dvizh_media_test *> $null
        $databaseReady = $LASTEXITCODE -eq 0
        curl.exe --noproxy 127.0.0.1 --silent --fail --max-time 1 "http://127.0.0.1:$storagePort/minio/health/ready" *> $null
        if ($databaseReady -and $LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Test services did not become ready.' }
    $env:DATABASE_URL = "postgresql+asyncpg://media_test:media-test-password@127.0.0.1:$databasePort/dvizh_media_test"
    $env:TEST_DATABASE_URL = $env:DATABASE_URL
    $env:TEST_MINIO_ENDPOINT = "127.0.0.1:$storagePort"
    & $testPython -c "import os; from minio import Minio; c=Minio(os.environ['TEST_MINIO_ENDPOINT'],access_key='media_test',secret_key='media-test-password',secure=False); c.make_bucket('media-test')"
    if ($LASTEXITCODE -ne 0) { throw 'Could not initialize test bucket.' }
    & $testPython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Test migrations failed.' }
    & $testPython -m alembic check
    if ($LASTEXITCODE -ne 0) { throw 'Models and migrations do not match.' }
    & $testPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    & $testPython -m ruff check src tests alembic
    if ($LASTEXITCODE -ne 0) { throw 'Lint failed.' }
}
finally {
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
    }
    foreach ($containerId in @($testStorageId, $testDatabaseId)) {
        if ($containerId) { docker stop $containerId | Out-Null }
    }
    Pop-Location
}
