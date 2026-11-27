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
and add `-vv -s` for detailed output. The current suite has 68 collected and
passing cases with one existing Starlette TestClient/httpx deprecation warning.
