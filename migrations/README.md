# Watchlist schema repair

> **Current check (2026-11-27):** An approved read-only inspection of the configured PostgreSQL database found `watchlist.updated_at` present and non-null with a current-time default, and `status` non-null with a `PLANNED` default. All five ORM tables and inspected constraints match. The SQL file's execution history is unverified because no migration ledger was found. **Do not apply the migration to this target based on the old audit below.** Recheck the exact target before any future migration. See [Stage 0C Part 1B findings](../docs/progress.md#stage-0c-part-1b--approved-read-only-postgresql-schema-verification-2026-11-27).

The application uses `Base.metadata.create_all()` in `load_data.py`. That creates
missing tables but does not add columns or alter constraints on existing tables.
There is no Alembic migration setup in this repository.

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
