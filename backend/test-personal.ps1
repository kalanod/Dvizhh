param([string]$PostgresImage = 'dvizh-postgres:latest')

$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$testPython = Join-Path $projectDirectory '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $testPython)) {
    throw 'Run uv sync --locked in backend first (Python 3.12 is required).'
}
$testContainerName = 'dvizh-scenarios-test-' + [guid]::NewGuid().ToString('N')
$testContainerId = $null
$previousDatabaseUrl = $env:DATABASE_URL
$previousTestDatabaseUrl = $env:TEST_DATABASE_URL
Push-Location $projectDirectory
try {
    $testContainerId = docker run --detach --rm --name $testContainerName `
        --env POSTGRES_DB=dvizh_scenarios_test --env POSTGRES_USER=scenarios `
        --env POSTGRES_PASSWORD=scenarios --env RECSYS_READER_PASSWORD=scenarios-reader `
        --publish '127.0.0.1::5432' $PostgresImage
    if ($LASTEXITCODE -ne 0 -or $testContainerId -notmatch '^[a-f0-9]{64}$') {
        $testContainerId = $null
        throw 'Could not start disposable PostgreSQL.'
    }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        docker exec $testContainerId pg_isready -h 127.0.0.1 -U scenarios -d dvizh_scenarios_test *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'PostgreSQL did not become ready.' }
    $testPortMapping = docker port $testContainerId 5432/tcp
    if ($LASTEXITCODE -ne 0 -or $testPortMapping -notmatch '^127\.0\.0\.1:(\d+)$') {
        throw 'Unexpected test port mapping.'
    }
    $env:DATABASE_URL = "postgresql+asyncpg://scenarios:scenarios@127.0.0.1:$($Matches[1])/dvizh_scenarios_test"
    $env:TEST_DATABASE_URL = $env:DATABASE_URL
    & $testPython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Test migrations failed.' }
    & $testPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
}
finally {
    [Environment]::SetEnvironmentVariable('DATABASE_URL', $previousDatabaseUrl, 'Process')
    [Environment]::SetEnvironmentVariable('TEST_DATABASE_URL', $previousTestDatabaseUrl, 'Process')
    if ($testContainerId) {
        docker stop $testContainerId | Out-Null
    }
    Pop-Location
}
