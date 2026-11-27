# File usage audit

Classification describes observed use, including CLI and pytest collection. `ACTIVE` does not mean part of the serving API. `PARTIALLY USED` means some defined behavior is not referenced. `DUPLICATE` denotes overlapping behavior even when a file is executed. `UNUSED` requires no meaningful reference or execution path found. All paths are relative to the repository root. “Caller” lists principal entry points rather than every transitive import. Inspected current worktree source, static references (`rg`), router registration, CLI guards, tests, config references, and artifact loading paths.

This table records the 2026-11-25 application audit. Stage 0B later populated `README.md` and added planning/evidence documents; see [docs/progress.md](../progress.md). No application-file classification changed in Stage 0B.

## Application and API files

| File | Purpose; main definitions | Principal imports/calls | Called by / execution | Status | Recommendation |
|---|---|---|---|---|---|
| `app/main.py` | FastAPI app, `lifespan`, `/`, `/health`; router registration | SessionLocal, Rating, pandas, MovieRecommender, four routers | `uvicorn app.main:app`; TestClient | ACTIVE | Improve startup/readiness observability |
| `app/api/movies.py` | List, search, detail endpoints | movie_service, movie schemas, `get_db` | `app/main.py` | ACTIVE | Keep |
| `app/api/recommendations.py` | Similar-movie endpoint, model readiness and movie checks | recommendation_service, Movie, `get_db` | `app/main.py` | ACTIVE | Add response schema in future |
| `app/api/watchlist.py` | CRUD routes, query validation | watchlist_service, watchlist schemas, `get_db` | `app/main.py` | ACTIVE | Keep |
| `app/api/analytics.py` | Six statistics routes and SQL error adapter | analytics_service, analytics schemas, `get_db` | `app/main.py` | ACTIVE | Keep; align error policy |
| `app/api/__init__.py` | Empty package marker | Python package import machinery | API imports | ACTIVE | Keep |

## Database, schemas, services

| File | Purpose; main definitions | Principal imports/calls | Called by / execution | Status | Recommendation |
|---|---|---|---|---|---|
| `app/database/connection.py` | Engine, `SessionLocal`, `Base`, `get_db` | dotenv, SQLAlchemy, `DATABASE_URL` | App, routes, scripts, tests | ACTIVE | Keep; document configuration |
| `app/database/models.py` | `Movie`, `User`, `Rating`, `Watchlist`, `IngestionJob` | `Base`, SQLAlchemy columns/FKs | Services, app, CLI, tests | ACTIVE | Keep; verify deployed schema separately |
| `app/database/__init__.py` | Empty package marker | Package machinery | Database imports | ACTIVE | Keep |
| `app/schemas/movie.py` | `MovieResponse`, `MovieListResponse` | Pydantic | Movie routes | ACTIVE | Keep |
| `app/schemas/watchlist.py` | `WatchlistStatus`, create/update/item/list models | Pydantic | Watchlist routes/service | ACTIVE | Keep |
| `app/schemas/analytics.py` | Overview/genre/rating/ranked-movie/watchlist analytics models | Pydantic | Analytics routes | ACTIVE | Keep |
| `app/schemas/rating.py` | Empty placeholder; no classes/functions | None | No reference found | UNUSED | Consider removal after confirming no external import |
| `app/schemas/__init__.py` | Empty package marker | Package machinery | Schema imports | ACTIVE | Keep |
| `app/services/movie_service.py` | `get_movies`, `get_movie_by_id`, `search_movies` | ORM Movie, SQLAlchemy queries | Movie routes, tests | ACTIVE | Keep |
| `app/services/recommendation_service.py` | `get_similar_movies`: enrich KNN IDs in one query | Movie ORM, MovieRecommender | Recommendation route | ACTIVE | Keep |
| `app/services/watchlist_service.py` | CRUD, `_item`, `_record`, `_commit` | Watchlist/User/Movie, HTTPException | Watchlist routes, tests | ACTIVE | Improve HTTP/service separation |
| `app/services/analytics_service.py` | Six aggregations, `_genre_counts`, `_rated_movies` | ORM and SQLAlchemy aggregates, Counter | Analytics routes, tests | ACTIVE | Investigate full genre scan at scale |
| `app/services/ingestion_service.py` | `insert_in_batches`, `load_movie_data` | PostgreSQL `insert`, ORM models | `load_data.py`, ingestion tests | ACTIVE | Keep; clarify job semantics |
| `app/services/__init__.py` | Empty package marker | Package machinery | Service imports | ACTIVE | Keep |

## Pipeline and recommendation files

| File | Purpose; main definitions | Principal imports/calls | Called by / execution | Status | Recommendation |
|---|---|---|---|---|---|
| `app/data_pipeline/extractor.py` | `extract_movies`, `extract_ratings` | pandas CSV reader | `load_data.py`, manual checks, tests | ACTIVE | Keep |
| `app/data_pipeline/validator.py` | `_valid_positive_ids`, `validate_movies`, `validate_ratings` | pandas/NumPy validation | `load_data.py`, manual checks, tests | ACTIVE | Keep |
| `app/data_pipeline/transformer.py` | `transform_movies`, `transform_ratings` | pandas conversions/year extraction | `load_data.py`, manual checks, tests | ACTIVE | Keep |
| `app/data_pipeline/__init__.py` | Empty package marker | Package machinery | Pipeline imports | ACTIVE | Keep |
| `app/recommender/model.py` | `MovieRecommender` KNN and a second `evaluate_multi_seed_model` | pandas, SciPy CSR, sklearn NN | App startup, evaluation, tests | PARTIALLY USED | Retain KNN; investigate broken duplicate evaluator |
| `app/recommender/content_based.py` | `ContentBasedRecommender`: genre TF-IDF and user profile | pandas, sklearn | Offline evaluation/manual checks/tests; no API | ACTIVE | Keep as offline algorithm |
| `app/recommender/hybrid.py` | `normalize_scores`, `calculate_hybrid_scores`, `calculate_popularity_scores` | pandas/NumPy | Hybrid service/evaluation/tests | ACTIVE | Review repeated normalization |
| `app/recommender/hybrid_service.py` | `recommend_hybrid_for_user` | KNN, content, hybrid scoring | Offline evaluation/manual check/tests; no API | ACTIVE | Keep; simplify scoring after tests |
| `app/recommender/evaluation.py` | Precision/recall, random, popularity, temporal, rolling evaluations | KNN/content/hybrid, pandas/NumPy | `evaluate_recommender.py`, tests indirectly | ACTIVE | Consider splitting by experiment later |
| `app/recommender/__init__.py` | Empty package marker | Package machinery | Recommender imports | ACTIVE | Keep |
| `app/utils/logger.py` | Empty placeholder | None | No reference found | UNUSED | Consider removal after external-use check |
| `app/utils/__init__.py` | Empty package marker for otherwise empty utility package | Package machinery | No application import found | UNCERTAIN | Investigate together with `logger.py` |
| `app/__init__.py` | Empty package marker | Package machinery | All `app.*` imports | ACTIVE | Keep |

## Frontend files

| File | Purpose; main definitions | Principal imports/calls | Called by / execution | Status | Recommendation |
|---|---|---|---|---|---|
| `frontend/streamlit_app.py` | Entry point, five-page navigation/state | Streamlit, pages, styles | `streamlit run`, AppTest | ACTIVE | Keep |
| `frontend/pages.py` | Home, Discover, For You, My Watchlist, Insights; search/detail/CRUD/charts | api_client, components, config, pandas/Streamlit | `streamlit_app.py`, tests | ACTIVE | Improve response validation and split only if growth warrants |
| `frontend/api_client.py` | `APIError`, `request`, GET/POST/PATCH/DELETE; timeout and error mapping | requests, env base URL | `pages.py`, tests | ACTIVE | Keep |
| `frontend/components.py` | Section, empty state, statistic, poster fallback, movie cards/grid | Streamlit, movie dictionaries | `pages.py` | ACTIVE | Keep; real posters await metadata source |
| `frontend/config.py` | `demo_user_id` setting | Environment lookup | `pages.py` | ACTIVE | Keep; document demo setting |
| `frontend/styles.py` | Theme CSS and `inject_theme` | Streamlit | `streamlit_app.py` | ACTIVE | Keep |
| `frontend/__init__.py` | Empty package marker | Package machinery | Frontend imports/tests | ACTIVE | Keep |

## Root scripts, tests, configuration, data, operations

| File | Purpose; main definitions | Principal imports/calls | Called by / execution | Status | Recommendation |
|---|---|---|---|---|---|
| `load_data.py` | Create tables, CSV-to-PostgreSQL ingestion `main` | Pipeline, ingestion_service, connection/models | Explicit CLI per AGENTS.md | ACTIVE | Keep; later move to `scripts/` only with command updates |
| `evaluate_recommender.py` | Offline evaluation CLI `main`; top-level CSV read | Evaluation functions, DB ratings, pandas | Explicit CLI | ACTIVE | Improve import side effects; keep experiments |
| `check_database.py` | Counts/sample read-only DB check at import | DB engine/SQL | Explicit CLI | ACTIVE | Move to manual scripts optionally; guard execution |
| `explore_data.py` | CSV exploration prints at import | pandas, raw CSV | Explicit CLI | ACTIVE | Optional manual-scripts move; guard execution |
| `test_pipeline.py` | ETL smoke output at import | Extract/validate/transform, CSV | Explicit CLI and pytest collection | ACTIVE | Convert to assertions or rename as manual check |
| `test_content_based.py` | Content model smoke with sample inputs at import | Content model, raw movies | Explicit CLI and pytest collection | ACTIVE | Convert or rename; avoid collection side effects |
| `test_hybrid.py` | Synthetic hybrid assertions at import | Hybrid scoring | Explicit CLI and pytest collection | DUPLICATE | Fold unique cases into automated tests, then consider removal |
| `test_hybrid_service.py` | DB-dependent hybrid smoke `main` | DB ratings, KNN/content/hybrid | Explicit CLI only; guarded main | ACTIVE | Keep as manual runner or move after command updates |
| `tests/test_analytics.py` | Analytics API fixtures and cases | TestClient, SQLite StaticPool | pytest; fixture imports from other tests | ACTIVE | Extract shared fixtures later |
| `tests/test_database.py` | FK, unique, rollback, session checks | SQLite fixture, ORM | pytest | ACTIVE | Keep; add isolated PostgreSQL contract tests if needed |
| `tests/test_frontend_integration.py` | API client, Streamlit AppTest and UI actions | mocked HTTP/TestClient, SQLite | pytest | ACTIVE | Keep |
| `tests/test_ingestion.py` | CSV validation and ingestion error/idempotency behavior | tmp CSV, mocks, PostgreSQL insert compilation | pytest | ACTIVE | Keep; live PG not exercised |
| `tests/test_movies.py` | Movie routes, search, pagination, errors | TestClient, SQLite fixtures | pytest | ACTIVE | Keep |
| `tests/test_recommendations.py` | Guarded manual database KNN runner; no `test_*` functions | DB session, MovieRecommender | Explicit CLI only | PARTIALLY USED | Rename/move to manual checks after command update |
| `tests/test_recommender_quality.py` | Synthetic KNN/content/hybrid behavior | pandas, recommenders | pytest | ACTIVE | Add evaluation metric tests |
| `tests/test_watchlist.py` | Watchlist CRUD, validation and docs | fake Session, TestClient | pytest | ACTIVE | Keep; SQLite integration also covered elsewhere |
| `tests/README.md` | Test isolation instructions | None | Developer documentation | ACTIVE | Keep updated |
| `tests/__init__.py` | Empty package marker | Package machinery | Test imports | ACTIVE | Keep while fixtures imported across modules |
| `scripts/schema_audit.py` | Read-only PostgreSQL schema comparison CLI | SQLAlchemy, dotenv, ORM metadata | Explicit operational CLI | ACTIVE | Keep; use before migrations |
| `migrations/20261125_watchlist_updated_at.sql` | Add/backfill `updated_at` and status constraints | PostgreSQL SQL | Runbook/manual execution; not app import | ACTIVE | Preserve; confirm application separately |
| `migrations/README.md` | Migration instructions | SQL file, schema audit | Operational documentation | ACTIVE | Keep |
| `data/raw/movies.csv` | MovieLens movie source rows | pandas in ETL/evaluation | `load_data.py`, offline scripts | ACTIVE | Preserve user/source data |
| `data/raw/ratings.csv` | MovieLens rating source rows | pandas in ETL/manual checks | `load_data.py`, offline scripts | ACTIVE | Preserve user/source data |
| `models/` | Empty artifact directory, no file to classify | None | No loader or save path found | UNCERTAIN | Preserve directory; investigate planned persistence |
| `.gitignore` | Excludes secrets and generated files | Git | Git workflows | ACTIVE | Keep |
| `.env` | Local runtime configuration; values not inspected | dotenv in connection and schema audit | Runtime/operational use | ACTIVE | Preserve, never commit |
| `.vscode/settings.json` | Python terminal env-file setting | VS Code | Local editor | ACTIVE | Keep local/ignored |
| `requirements.txt` | Direct package dependency list | pip | Environment setup | ACTIVE | Review unused/unpinned dependencies |
| `README.md` | Empty at the audit; populated in Stage 0B | Developer entry point | Repository readers | ACTIVE after Stage 0B | Maintain setup and architecture links |
| `AGENTS.md` | Repository instructions | None | Codex/developer workflow | ACTIVE | Keep |

## Test safety and evidence limits

The executed `pytest` run collected 63 passing tests. The API/database test fixtures use in-memory SQLite, dependency overrides, fake sessions, or mocked PostgreSQL insert behavior; Streamlit tests mock HTTP. Root-level `test_pipeline.py` and `test_content_based.py` execute CSV work at pytest import/collection time, and `test_hybrid.py` runs assertions then. Guarded database manual runners are not invoked by pytest. No test in this suite was observed issuing destructive SQL to the configured Render database. This does **not** verify PostgreSQL behavior or production schema. The audit did not execute `load_data.py`, database manual runners, or migrations.
