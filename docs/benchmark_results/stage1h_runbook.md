# Stage 1H guarded benchmark runbook

This runbook is for a deliberate private rerun against the dedicated, restricted local `movieverse_itest` PostgreSQL database. It is not needed to inspect the preserved results. It never reads `.env`, and the runner refuses any URL other than the loopback test host/database/role. It sets `DATABASE_URL` to an unusable loopback sentinel and passes no database URL or password as a process argument. The `psql -W` checks and benchmark each request the local password interactively; benchmark entry uses a hidden PowerShell secure prompt.

Run from the repository root. `psql` must be available on PATH. The run is sequential and uses only the guarded database; each configuration starts with an empty public schema and the runner initializes/cleans it under its advisory lock.

```powershell
$rawHashes = @{
    'movies.csv'  = '5a5f32dd9bb3797b8e728a1b98958789d2b13f294a69fdfbc5727f8a9611aa07'
    'ratings.csv' = 'aa289ca83157595d0df6aea1be6a4ded676ddc4385472e8313a8ed9805352646'
}
function Assert-RawHashes([string]$Phase) {
    foreach ($name in $rawHashes.Keys) {
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path '.\data\raw' $name)).Hash.ToLowerInvariant()
        if ($actual -ne $rawHashes[$name]) { throw "$Phase raw-file hash mismatch: $name" }
    }
    Write-Output "$Phase raw-file hashes match baseline."
}

$identityQuery = "SELECT current_database() || '|' || current_user || '|' || host(inet_server_addr()) || '|' || inet_server_port() || '|' || (SELECT count(*)::text FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind IN ('r','p','v','m','S','f'));"
$expectedIdentity = 'movieverse_itest|movieverse_itest|127.0.0.1|5432|0'
Assert-RawHashes 'Pre-run'
$before = & psql -h 127.0.0.1 -p 5432 -U movieverse_itest -d movieverse_itest -W -X -A -t -v ON_ERROR_STOP=1 -c $identityQuery
$psqlExit = $LASTEXITCODE
if ($psqlExit -ne 0 -or ($before -join '').Trim() -ne $expectedIdentity) {
    throw 'Preflight failed: verify local identity and an empty public schema.'
}

$envNames = @('DATABASE_URL','MOVIEVERSE_TEST_DATABASE_URL','MOVIEVERSE_RUN_POSTGRES_INTEGRATION','PYTHONDONTWRITEBYTECODE')
$oldEnv = @{}
foreach ($name in $envNames) { $oldEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$resultDirectory = Join-Path ([IO.Path]::GetTempPath()) ('movieverse-matrix-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $resultDirectory | Out-Null
$resultPath = Join-Path $resultDirectory 'matrix.jsonl'
$started = $false
try {
    $env:DATABASE_URL = 'postgresql+psycopg://127.0.0.1:1/unused'
    $credential = [pscredential]::new('movieverse_itest', (Read-Host 'Local movieverse_itest password' -AsSecureString))
    $encodedPassword = [uri]::EscapeDataString($credential.GetNetworkCredential().Password)
    $env:MOVIEVERSE_TEST_DATABASE_URL = "postgresql+psycopg://movieverse_itest:${encodedPassword}@127.0.0.1:5432/movieverse_itest"
    $env:MOVIEVERSE_RUN_POSTGRES_INTEGRATION = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    Remove-Variable credential, encodedPassword

    $orders = @{
        '1-small' = @(250,1000,2000); '1-medium' = @(1000,2000,250); '1-full' = @(2000,250,1000)
        '2-small' = @(1000,2000,250); '2-medium' = @(2000,250,1000); '2-full' = @(250,1000,2000)
        '3-small' = @(2000,250,1000); '3-medium' = @(250,1000,2000); '3-full' = @(1000,2000,250)
    }
    foreach ($repetition in @(1,2,3)) {
        foreach ($size in @('small','medium','full')) {
            foreach ($batch in $orders["$repetition-$size"]) {
                Write-Output "Running repetition $repetition, $size, batch $batch."
                $started = $true
                & .\.venv-watchlist\Scripts\python.exe -m scripts.benchmark_scenarios `
                    --size $size --batch-size $batch --repetitions 1 --repetition-start $repetition `
                    --seed 2026 --source .\data\raw --results $resultPath
                if ($LASTEXITCODE -ne 0) { throw "Benchmark failed for $repetition/$size/$batch; keep the JSONL and sanitized error." }
            }
        }
    }
}
finally {
    try {
        if ($started) {
            $after = & psql -h 127.0.0.1 -p 5432 -U movieverse_itest -d movieverse_itest -W -X -A -t -v ON_ERROR_STOP=1 -c $identityQuery
            $psqlExit = $LASTEXITCODE
            if ($psqlExit -ne 0 -or ($after -join '').Trim() -ne $expectedIdentity) {
                throw 'Post-run local identity or empty-schema check failed.'
            }
            Assert-RawHashes 'Post-run'
        }
    }
    finally {
        foreach ($name in $envNames) {
            if ($null -eq $oldEnv[$name]) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
            else { Set-Item "Env:$name" $oldEnv[$name] }
        }
        Remove-Variable oldEnv, envNames -ErrorAction SilentlyContinue
    }
}

$records = @(Get-Content -LiteralPath $resultPath | ForEach-Object { $_ | ConvertFrom-Json })
if ($records.Count -ne 81) { throw "Expected 81 JSONL records, found $($records.Count). Preserve and inspect $resultPath." }
$duplicates = @($records | Group-Object dataset_size,batch_size,scenario,repetition | Where-Object Count -ne 1)
if ($duplicates.Count) { throw 'Duplicate benchmark configuration IDs found.' }
$records | Select-Object dataset_size,batch_size,repetition,scenario,content_fingerprint,
    processed_records,inserted_records,updated_records,unchanged_records,
    ingestion_duration_seconds,processed_records_per_second,peak_process_working_set_mib |
    Format-Table -AutoSize
Write-Output "Results preserved at $resultPath"
```

Completed configuration groups append as JSONL. If interrupted, preserve the file. Before resuming, validate completed groups and run the same identity/empty-schema preflight; do not delete database objects manually. Use `--repetition-start` to keep identifiers unique and skip complete groups rather than append duplicates. The checked-in result is at [stage1h_postgresql_matrix.jsonl](stage1h_postgresql_matrix.jsonl).
