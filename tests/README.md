# Backend test database

The automated API and model tests do not connect to Render. `test_analytics.py`
sets a deliberately unreachable `DATABASE_URL` before importing the app, then
overrides FastAPI's `get_db` dependency with a fresh in-memory SQLite engine for
each test. `test_database.py` enables SQLite foreign-key checks explicitly.
`test_watchlist.py` uses an in-memory session double. The FastAPI lifespan test
also replaces its startup session with the isolated SQLite session and restores
the app state afterward.

The ingestion loader uses PostgreSQL `ON CONFLICT` SQL. The unit test checks its
PostgreSQL compilation and returned-row counting without connecting to a server.
A separate integration run against a disposable PostgreSQL database is still
needed to verify actual conflict handling, migrations, and connection behavior.
Never point these tests at the production Render database.

Run from the repository root in PowerShell:

```powershell
python -m compileall app tests
.venv-watchlist\Scripts\python.exe -m pytest -v
.venv-watchlist\Scripts\python.exe -m pytest tests/test_ingestion.py -v
```
