# Repository Guidelines

## Project Structure & Module Organization

MovieVerse is a Python movie recommendation service. `app/main.py` starts the FastAPI API; `app/api/` defines routes, `app/services/` holds application logic, `app/database/` manages SQLAlchemy models and sessions, and `app/schemas/` contains response models. Data ingestion lives in `app/data_pipeline/`, while collaborative, content-based, and hybrid recommenders live in `app/recommender/`. `frontend/streamlit_app.py` is the Streamlit interface. MovieLens CSV inputs are in `data/raw/`. The `tests/` directory and root-level `test_*.py` files contain tests and standalone checks.

## Build, Test, and Development Commands

From the repository root, create a virtual environment and install dependencies with `python -m venv .venv` and `pip install -r requirements.txt`. Set `DATABASE_URL` in a local `.env` file to a PostgreSQL connection string. Run `python load_data.py` to create tables and ingest `data/raw/` CSV files before starting the API: startup trains a model from stored ratings and requires data to exist. Use `uvicorn app.main:app --reload` for the API and `streamlit run frontend/streamlit_app.py` for the UI; the UI expects the API at `http://127.0.0.1:8000`. Run `python -m pytest` for collected tests. Root-level scripts such as `python test_pipeline.py` can be run individually for manual checks.

## Coding Style & Naming Conventions

Use four spaces for Python indentation. Follow the existing `snake_case` convention for modules, functions, and variables, and `PascalCase` for classes. Keep request handling in `app/api/`, business logic in `app/services/`, and model code in `app/recommender/`. Add type hints where practical and keep imports grouped by standard library, third-party packages, and local modules. No formatter or linter is configured; keep changes consistent with neighboring code.

## Testing Guidelines

`pytest` is listed in `requirements.txt`, but several existing `test_*.py` files are executable checks rather than isolated pytest cases. For new automated tests, use `test_*.py` names and `test_*` functions, and cover changed behavior and edge cases. Database-dependent checks require `DATABASE_URL` and loaded data. There is no documented coverage threshold.

## Commit & Pull Request Guidelines

Recent commits use short imperative subjects, sometimes prefixed with `feat:` (for example, `feat: Recommendation API`). Keep commits focused and describe the behavior changed. In pull requests, summarize the change, list verification commands and results, link relevant issues, and include screenshots for Streamlit UI changes.

## Security & Configuration

Keep credentials in `.env`, which is ignored by Git. Do not commit database URLs containing passwords or generated model artifacts.
