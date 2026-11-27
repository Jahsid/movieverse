# MovieVerse development instructions

## Objectives and scope

Build a reliable, maintainable movie recommendation and AI platform **and** use it to learn and demonstrate Data Engineering, ML Engineering, Deep Learning, AI Engineering, Generative AI, Agentic AI, and Forward Deployed Engineering. Follow the approved stages in [ROADMAP.md](ROADMAP.md). A technology can be valuable as a documented learning experiment even when the serving application does not need it.

Keep production features and learning experiments separate. An experiment becomes a serving feature only after its quality, cost, memory, latency, safety, and maintenance impact are measured and reviewed. Preserve working behavior and existing API contracts unless a change is explicitly approved.

## Current architecture and file organization

MovieVerse is a modular Python application. `app/main.py` starts FastAPI and currently trains collaborative KNN from stored ratings during startup. `app/api/` owns HTTP routes; `app/services/` owns use cases and database operations; `app/schemas/` owns API contracts; `app/database/` owns SQLAlchemy models and sessions; `app/data_pipeline/` owns CSV extraction, validation, and transformation; `app/recommender/` owns recommendation algorithms and offline evaluation. `frontend/` is the Streamlit client. `data/raw/` contains MovieLens inputs. `tests/` contains automated tests with shared fixtures in `tests/conftest.py`; some root `test_*.py` files are guarded manual checks that collect no pytest cases. See [docs/architecture/ARCHITECTURE_OVERVIEW.md](docs/architecture/ARCHITECTURE_OVERVIEW.md) for verified behavior and [docs/architecture/REFACTORING_ROADMAP.md](docs/architecture/REFACTORING_ROADMAP.md) for possible structural changes.

Add modules when a stage needs them. Do not create empty packages, duplicate an existing module, move files merely to match a target tree, or introduce a framework without a concrete use case. Keep notebooks and heavyweight experiments outside request-serving paths.

## Coding and dependency standards

Use four-space indentation, `snake_case` for modules/functions/variables, `PascalCase` for classes, practical type hints, and imports grouped as standard library, third party, and local. Keep route handling thin, business decisions in services, and model training/evaluation separate from HTTP code. Match neighboring style; no formatter or linter is configured today.

Prefer existing libraries and standard-library solutions. Before adding a dependency, document its purpose, license, free local option, Windows compatibility, memory/disk impact, and why existing tools are insufficient. Keep optional ML, deep-learning, and AI dependencies out of the core install where practical. Record tested versions and reproducible installation instructions when dependency changes are made. Do not silently introduce paid APIs or services.

## Testing and database safety

Add meaningful automated tests for changed behavior, edge cases, and public contracts. Name new automated files `test_*.py` and test functions `test_*`. No coverage threshold is currently configured. Run targeted tests and the collected suite when safe; report commands, results, skips, and limits honestly. Isolate tests from the configured PostgreSQL database. SQLite and mocks do not prove PostgreSQL compatibility, so use a disposable PostgreSQL database for dialect or migration integration checks when that stage requires it. Root smoke scripts, such as `python test_pipeline.py`, can be run individually but are not a substitute for assertions.

Treat every configured database as potentially important. Inspect connection targets before database work. Do not run `load_data.py`, schema writes, migrations, cleanup, or destructive tests against a shared or production database. Review migrations and backups before schema changes. A read-only schema audit does not authorize a migration. Keep credentials in local `.env` or environment variables; never print, commit, paste, or log secrets or password-bearing URLs. Keep generated data, model artifacts, and private user data out of Git unless explicitly reviewed.

## Incremental, zero-budget-first workflow

Develop primarily on Windows with an Intel i3-1115G4 and 8 GB RAM. Measure memory and runtime before selecting heavier designs. Use small samples locally and Google Colab for computationally intensive experiments when available; free Colab resources are variable, so core behavior must not depend on a particular GPU or paid tier. Prefer open-source tools and free local execution. Use Airflow, Kafka, PySpark, dbt, LangGraph, and MCP in bounded learning stages; do not make them required serving infrastructure without evidence.

For every future implementation task, explain:

1. What problem is being solved?
2. Why is the implementation necessary?
3. How does the solution work?
4. Why were these tools selected?
5. What alternatives exist?
6. Which files changed, and why?
7. How can the feature be executed and tested independently?
8. Which technical interview questions relate to the implementation?
9. What measurable evidence could support a resume bullet?

Mark projected achievements as **targets** until implemented and measured. Never fabricate benchmark values or claim a test, deployment, or integration was completed without evidence. Record measured results and methods in [docs/benchmarks.md](docs/benchmarks.md), decisions in [docs/decisions.md](docs/decisions.md), and stage status in [docs/progress.md](docs/progress.md). Update the README and architecture documents when behavior or structure changes; avoid copying the same detailed content into multiple files.

Seek approval before major architectural changes: splitting services, replacing the database, introducing required orchestration or model-serving infrastructure, changing public contracts, or adding a paid dependency. Implement only the approved stage and stop at its boundary. Do not commit or push without authorization.

## Local commands and collaboration

From the repository root, use `python -m venv .venv`, then `pip install -r requirements.txt` in that environment. Set `DATABASE_URL` in a local `.env` for an **isolated development PostgreSQL database**. After verifying the target and schema, `python load_data.py` creates missing tables and ingests `data/raw/`; it does not upgrade existing tables. Start the API with `uvicorn app.main:app --reload` and UI with `streamlit run frontend/streamlit_app.py`. The UI defaults to `http://127.0.0.1:8000`. Run `python -m pytest` for collected tests. See [tests/README.md](tests/README.md) for test isolation and [migrations/README.md](migrations/README.md) for migration cautions.

Keep changes and commits focused. Use short imperative commit subjects; a `feat:` prefix is acceptable for features. For pull requests, describe behavior, verification and limitations; link issues when present and include screenshots for Streamlit changes. Do not change or delete user data or generated artifacts as part of routine cleanup.
