# MovieVerse

MovieVerse is a Python movie discovery, recommendation, and analytics project. It has a FastAPI backend, PostgreSQL data store, Streamlit interface, MovieLens CSV ingestion pipeline, and offline collaborative, content-based, and hybrid recommendation experiments. The project is being developed incrementally as both a functional platform and an engineering learning portfolio.

## What works today

- Movie list, title search, and details; watchlist CRUD; analytics endpoints and Streamlit pages.
- A similar-movie API backed by item-based cosine KNN trained from database ratings when the API starts.
- CSV validation and PostgreSQL ingestion, plus offline content-based, hybrid, and temporal evaluation code.
- A read-only MovieLens dataset manifest with file hashes, sizes, CSV columns, and row counts.
- A read-only data quality report with accepted/rejected counts and rejection reasons.

Content-based and hybrid recommendations are **not** live API features. There is no saved model loader, deep-learning model, RAG system, or agent workflow yet. The API requires a working database to start. With no ratings or an ordinary model training failure, catalogue routes can still start while recommendations return 503; memory exhaustion stops startup. `/health` retains its static liveness response; `/ready` checks the database and trained recommendation model and returns 503 if either is unavailable.

## Repository guide

| Location | Purpose |
|---|---|
| `app/api/`, `app/services/`, `app/schemas/` | HTTP routes, use cases, and API contracts |
| `app/database/` | SQLAlchemy connection and models |
| `app/data_pipeline/`, `load_data.py` | MovieLens extraction, checks, transformation, and ingestion |
| `app/recommender/`, `evaluate_recommender.py` | Recommendation models and offline evaluation |
| `frontend/` | Streamlit UI and HTTP client |
| `data/raw/`, `migrations/`, `scripts/` | Inputs, schema repair, and operational checks |
| `tests/` and root `test_*.py` | Automated tests and some manual checks |

Generate and inspect raw-file metadata without a database connection:

```powershell
.venv-watchlist\Scripts\python.exe -m app.data_pipeline.manifest
```

To compare later, save a baseline outside Git with `--output $env:TEMP\movieverse-manifest.json`, then run the command with `--compare $env:TEMP\movieverse-manifest.json`. The CLI does not overwrite an existing output file. The documented source is MovieLens; the exact release version and source URL are unverified, so the manifest records them as `null`.

Inspect data quality as JSON without loading the database:

```powershell
.venv-watchlist\Scripts\python.exe -m app.data_pipeline.quality_report
```

The report uses the same movie and rating rules as fail-fast ingestion validation and checks valid rating movie IDs against the movie file. Its reason counts can overlap when a row has several errors; accepted plus rejected always equals total. User references and database state are not checked.

The detailed current-state inventory is in [docs/architecture/PROJECT_STRUCTURE.md](docs/architecture/PROJECT_STRUCTURE.md). The approved staged plan is in [ROADMAP.md](ROADMAP.md).

## Local development

Use Python on Windows from the repository root. These commands assume PowerShell and an isolated development PostgreSQL database.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Set `DATABASE_URL` in a local `.env` to a PostgreSQL connection string for the isolated database. `.env` is ignored by Git. Confirm the target before any write. The loader needs the existing Alembic tooling (`pip install -r requirements-migrations.txt`). Before importing either CSV it verifies the target's public schema and ledger against the configured migration head. Empty, unversioned or incompatible databases require separate migration review. See the [migration runbook](migrations/README.md).

```powershell
python load_data.py
uvicorn app.main:app --reload
```

In another terminal:

```powershell
streamlit run frontend/streamlit_app.py
```

The UI uses `MOVIEVERSE_API_URL` if set, otherwise `http://127.0.0.1:8000`. `MOVIEVERSE_DEMO_USER_ID` selects a demo profile and defaults to `1`; it is not authentication. API documentation is available at `/docs` while the API runs.

## Verification and safety

```powershell
python -m pytest
```

See [tests/README.md](tests/README.md) before running database-related checks. Most automated tests use isolated SQLite or mocks; they do not establish PostgreSQL migration compatibility. Root `test_*.py` smoke scripts may run work during pytest collection. Do not run the loader, manual database scripts, or [migrations](migrations/README.md) against a shared or production database as a test.

## Development records

- [ROADMAP.md](ROADMAP.md): objectives, acceptance gates, tools, and learning goals for Stages 0A–10.
- [docs/architecture/](docs/architecture/ARCHITECTURE_OVERVIEW.md): current architecture, data flow, file audit, debt, and structural proposals.
- [docs/decisions.md](docs/decisions.md): architectural decisions and open decisions.
- [docs/progress.md](docs/progress.md): implemented work and stage status.
- [docs/benchmarks.md](docs/benchmarks.md): measurement method and verified results only.
- [AGENTS.md](AGENTS.md): persistent contribution and safety instructions.

The project targets zero additional expenditure and a Windows Intel i3/8 GB development machine. Computationally intensive learning experiments may use free Google Colab resources when available; production behavior must remain independently maintainable.

### Ingestion job results

After schema verification, `python load_data.py` tracks extraction through commit. A successful run reports processed, inserted, updated, and unchanged movie and rating rows, separate derived-user counts, the manifest-compatible content fingerprint, and elapsed seconds. Failures exit with status 1. Use the job ID to look up persisted counts, UTC timing, file fingerprint when available, and the failure phase and code. See [ingestion job semantics](docs/architecture/ARCHITECTURE_OVERVIEW.md#ingestion-job-lifecycle).

For migration dependency setup, offline PostgreSQL SQL previews and the guarded local baseline test, see the [migration runbook](migrations/README.md).
