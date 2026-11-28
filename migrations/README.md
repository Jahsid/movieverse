# Stage 1F schema baseline

Revision `0001_stage_1f` freezes the five application tables and their PostgreSQL constraints, indexes and server defaults. From the repository root on Windows:

```powershell
.\.venv-watchlist\Scripts\python.exe -m pip install -r requirements-migrations.txt
.\.venv-watchlist\Scripts\python.exe -m alembic history
.\.venv-watchlist\Scripts\python.exe -m alembic upgrade head --sql
.\.venv-watchlist\Scripts\python.exe -m alembic downgrade 0001_stage_1f:base --sql
```

Both SQL previews write to stdout without opening a connection. The downgrade drops all five application tables and deletes the baseline ledger entry. Existing database adoption requires a separate schema comparison, backup review and approval.

## Stage 1G-F loader preflight

Install the existing migration requirements in the loader environment. Run `python -m alembic heads` offline to inspect the expected revision. Before opening a CSV or creating a job, the loader reads PostgreSQL catalogs and checks for one compatible public ledger row at that head and matching table definitions. Failure exits with status 1. Confirm the database target, review the schema and backup, and arrange the appropriate migration or adoption separately. A matching version string alone cannot repair schema drift. Schedule ingestion separately from schema changes.

## Stage 1G-D ingestion metadata

Head revision `0002_ingestion_metadata` adds eight nullable columns without defaults or backfills. Preview only its SQL with `python -m alembic upgrade 0001_stage_1f:0002_ingestion_metadata --sql` and `python -m alembic downgrade 0002_ingestion_metadata:0001_stage_1f --sql`. Downgrading to the baseline drops the eight columns and any values stored in them. It preserves the original job columns and rows.

The updated ORM expects the new columns when reading whole job objects. The loader checks that the approved schema is already present. Plan schema upgrade before using the updated model on a populated database. Stage 1G-E populates these fields for new ingestion attempts. Revision `0002_ingestion_metadata` is the current head. Upgrade adds eight nullable columns without backfilling. Downgrade removes those columns and any values subsequently stored in them.

The private test block below exercises both fresh and adopted schemas through head, repeated upgrade, downgrade to baseline and re-upgrade. It checks original job values, NULL metadata and final rollback cleanup. Baseline adoption remains restricted to the exact Stage 1F schema and explicit baseline stamp authorization.

## Stage 1G-C verification and adoption rehearsal

The comparison in `scripts/baseline_verification.py` is pinned to the public schema of revision `0001_stage_1f`. It reads PostgreSQL catalogs for table and column definitions, keys, constraints, indexes, sequence defaults, ownership and generator settings. It compares the ledger definition and its exact revision if present. Generated sequence values and application rows are outside schema comparison. This is a strict application schema check; database-wide grants, roles, other schemas and historical SQL execution are outside its scope.

Only the dedicated, otherwise idle local test database and role are supported. In a new private PowerShell session at the repository root, run this block to authorize the fixture-only rehearsal. Use the local test role password at the hidden prompt. The migration cases also verify persisted success and failure metadata at the migrated head. The tests require an empty public schema, build their fixtures inside an outer transaction, and check cleanup after rollback. The explicit Alembic adoption tag is supplied only for the simulated legacy fixture and the tested rejection paths.

```powershell
$previousDatabaseUrl = $env:DATABASE_URL
$testCredential = [pscredential]::new('movieverse_itest', (Read-Host 'Local movieverse_itest password' -AsSecureString))
try {
    $encodedPassword = [uri]::EscapeDataString($testCredential.GetNetworkCredential().Password)
    $env:DATABASE_URL = 'postgresql+psycopg://127.0.0.1:1/unused'
    $env:MOVIEVERSE_TEST_DATABASE_URL = "postgresql+psycopg://movieverse_itest:${encodedPassword}@127.0.0.1:5432/movieverse_itest"
    $env:MOVIEVERSE_RUN_POSTGRES_INTEGRATION = '1'
    .\.venv-watchlist\Scripts\python.exe -m pytest -q tests/test_loader_revision.py tests/test_migration_baseline.py tests/test_postgres_integration.py
} finally {
    Remove-Item Env:MOVIEVERSE_TEST_DATABASE_URL, Env:MOVIEVERSE_RUN_POSTGRES_INTEGRATION -ErrorAction SilentlyContinue
    if ($null -eq $previousDatabaseUrl) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    } else {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
    Remove-Variable encodedPassword, testCredential, previousDatabaseUrl -ErrorAction SilentlyContinue
}
```

For a separate, intentionally prepared local baseline fixture, the same private environment supports `python -m scripts.baseline_verification`. This opens a repeatable-read, read-only transaction and reports whether the matching baseline already has a ledger. An empty database or a partially matching schema fails verification. The comparison has no stamp option. Existing application database adoption remains outside the rehearsal.

## Historical watchlist schema repair

> **Current check (2026-11-27):** An approved read-only inspection of the configured PostgreSQL database found `watchlist.updated_at` present and non-null with a current-time default, and `status` non-null with a `PLANNED` default. All five ORM tables and inspected constraints match. The SQL file's execution history is unverified because no migration ledger was found. **Do not apply the migration to this target based on the old audit below.** Recheck the exact target before any future migration. See [Stage 0C Part 1B findings](../docs/progress.md#stage-0c-part-1b--approved-read-only-postgresql-schema-verification-2026-11-27).

Earlier loaders used `create_all()` to initialize missing tables. Part 1G-F retired that initialization path.

The earlier read-only schema audit found that Render's `watchlist` table lacked
`updated_at`, and that `status` is nullable with no database default. The
model expects `updated_at` as a non-null `TIMESTAMP WITHOUT TIME ZONE` with a
current-time server default, and `status` as non-null with a `PLANNED` server
default. `added_at` is nullable in both model and database. The audit found
zero watchlist rows at that inspection time; the migration still includes backfills
to preserve records if rows are added before it runs.

Review the [SQL migration](20261125_watchlist_updated_at.sql) before applying
it. It is transactional and additive. The `updated_at` backfill uses each row's
`added_at` when present, or the current time otherwise. Existing non-null
statuses are left untouched. No movies, users, or ratings are changed.

From the repository root, with `DATABASE_URL` set to a PostgreSQL URI in the
PowerShell session, inspect before and after applying the migration:

```powershell
.venv-watchlist\Scripts\python.exe -m scripts.schema_audit
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f .\migrations\20261125_watchlist_updated_at.sql
.venv-watchlist\Scripts\python.exe -m scripts.schema_audit
```

The SQLAlchemy URL may use `postgresql+psycopg://`; `psql` requires a normal
`postgresql://` URI. Do not paste credentials into source files or logs.

After application, verify GET, POST, PATCH, and DELETE using an existing test
user and movie pair that is not already on that user's watchlist. Only delete
the item created for this check. Then run:

```powershell
.venv-watchlist\Scripts\python.exe -m pytest tests/test_watchlist.py -v
.venv-watchlist\Scripts\python.exe -m pytest -q
```
