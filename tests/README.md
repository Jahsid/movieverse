# Backend test database

The automated API and model tests do not connect to Render. `tests/conftest.py`
sets a deliberately unreachable loopback `DATABASE_URL` before importing the app.
Its function-scoped `database` fixture creates a fresh in-memory SQLite schema
for each test and closes the session and engine afterward. Its `client` fixture
overrides FastAPI's `get_db` dependency for one test and restores earlier
overrides afterward. `tests/helpers.py` contains shared seed records, not a fixture.
`test_database.py` enables SQLite foreign-key checks explicitly.
`test_watchlist.py` uses an in-memory session double. The FastAPI lifespan test
also replaces its startup session with the isolated SQLite session and restores
the app state afterward.

The ingestion loader uses PostgreSQL `ON CONFLICT` SQL. The unit test checks its
PostgreSQL compilation and returned-row counting without connecting to a server.
A separate integration run against a disposable PostgreSQL database is still
needed to verify actual conflict handling, migrations, and connection behavior.
Never point these tests or manual database runners at the production Render database.
The root `test_pipeline.py`, `test_content_based.py`, and `test_hybrid.py` files
are manual checks guarded by `main()`. Pytest finds them by name but collects no
test functions from them and does not run their checks. Their direct `python`
commands still work. Database-dependent manual scripts are not part of this
isolated suite.

Run from the repository root in PowerShell:

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://127.0.0.1:1/unused'
$env:PYTHONDONTWRITEBYTECODE = '1'
.venv-watchlist\Scripts\python.exe -m pytest -p no:cacheprovider --collect-only -q
.venv-watchlist\Scripts\python.exe -m pytest -p no:cacheprovider -q
.venv-watchlist\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_ingestion.py -q
.venv-watchlist\Scripts\python.exe test_pipeline.py
.venv-watchlist\Scripts\python.exe test_hybrid.py
.venv-watchlist\Scripts\python.exe test_content_based.py
```

To debug one case, append its node ID, for example
`tests/test_database.py::test_foreign_keys_and_rollback`, to the pytest command
and add `-vv -s` for detailed output. The Stage 1C isolated baseline has 99
passing cases and one existing Starlette TestClient/httpx deprecation warning.
The optional PostgreSQL case skips unless explicitly enabled; its URL guard
tests run without connecting.

## Opt-in local PostgreSQL integration test

This check uses the existing PostgreSQL 16 service and **only** a new, empty
`movieverse_itest` database owned by a restricted `movieverse_itest` login. It
does not use `DATABASE_URL` or `.env`. Before provisioning, verify the service
is local, the inbound firewall blocks TCP 5432, and `pg_hba.conf` permits only
loopback hosts with `scram-sha-256`. Do not change server-wide settings for this
test. In your own PowerShell terminal, use the installed `psql` client; `-W`
prompts for the administrator password without placing it in shell history:

```powershell
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -X -W -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

At the `psql` prompt, first verify `\conninfo`, then run this read-only query.
Proceed only if the database, role, address, and port are exactly `postgres`,
`postgres`, `127.0.0.1`, and `5432`:

```sql
SELECT current_database(), current_user, inet_server_addr(), inet_server_port();
```

Check that neither test name already exists, then create the restricted login
and separate database. `\password` prompts privately for the test password;
never put a password literal in SQL or a command. Run each line separately:

```sql
SELECT rolname FROM pg_roles WHERE rolname = 'movieverse_itest';
SELECT datname FROM pg_database WHERE datname = 'movieverse_itest';
CREATE ROLE movieverse_itest LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 5;
\password movieverse_itest
CREATE DATABASE movieverse_itest OWNER movieverse_itest TEMPLATE template0;
REVOKE ALL ON DATABASE movieverse_itest FROM PUBLIC;
\q
```

Both existence queries must return zero rows before `CREATE`. Use `psql` as the
test role to verify the identity independently; enter its password at the
prompt and keep the resulting output free of credentials:

```powershell
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -X -W -h 127.0.0.1 -p 5432 -U movieverse_itest -d movieverse_itest -c "SELECT current_database(), current_user, inet_server_addr(), inet_server_port();"
```

Run tests from the repository root in the same PowerShell session. This prompts
for the test password and stores it only in process memory and the temporary
environment variable. Do not display the URL or paste it into chat:

```powershell
$pw = [pscredential]::new('movieverse_itest', (Read-Host 'Local test password' -AsSecureString)).GetNetworkCredential().Password
$env:MOVIEVERSE_TEST_DATABASE_URL = "postgresql+psycopg://movieverse_itest:$([uri]::EscapeDataString($pw))@127.0.0.1:5432/movieverse_itest"
Remove-Variable pw
$env:MOVIEVERSE_RUN_POSTGRES_INTEGRATION = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
.venv-watchlist\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_postgres_integration.py -q
Remove-Item Env:MOVIEVERSE_TEST_DATABASE_URL, Env:MOVIEVERSE_RUN_POSTGRES_INTEGRATION
```

The integration case checks URL and connected identity before DDL or DML,
requires an empty `public` schema, creates the ORM tables, inserts records,
checks the watchlist unique constraint, rolls back a failed and a successful
uncommitted write, then drops only its newly created tables. It fails closed if
the test database contains existing objects. A sudden process termination can
leave test tables behind; inspect and clean only the verified test database
before retrying. Regular pytest runs skip this one case and still use isolated
SQLite. This initial check does not validate the production database or the
entire ingestion pipeline.

When finished with the disposable database, connect as the administrator to
`postgres` at `127.0.0.1:5432` with `-W`, verify the four identity values again,
and run the following only after deciding the local test database is no longer
needed. `DROP DATABASE` requires all test connections to be closed:

```sql
DROP DATABASE movieverse_itest;
DROP ROLE movieverse_itest;
```
