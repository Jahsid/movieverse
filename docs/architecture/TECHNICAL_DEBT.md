# Technical debt and test architecture

## Verification performed

Read-only source/reference inspection plus `.venv-watchlist\Scripts\python.exe -m pytest -p no:cacheprovider -q` on 2026-11-25: **63 passed, 0 failed, 0 skipped, 1 warning, 34.75 s**. The warning is a Starlette TestClient deprecation concerning `httpx`. This is the current executed result; the earlier 60-test figure is historical. The configured Render database, migrations, manual DB runners, API server and Streamlit server were not run. Tests do not establish production schema correctness.

## Test files and isolation

| File | Covered behavior | Isolation / production access | Gaps |
|---|---|---|---|
| `tests/test_analytics.py` | Overview, genre/rating distributions, rankings, watchlist stats, empties, invalid parameters, docs, lifespan | Dummy database URL at import; in-memory SQLite/StaticPool, overridden dependency | PostgreSQL aggregation/dialect behavior |
| `tests/test_database.py` | FK and uniqueness, rollback, session close, watchlist persistence | SQLite with FK pragma; imports fixtures from analytics tests | Real PostgreSQL schema/migration contract |
| `tests/test_frontend_integration.py` | API client, page rendering/search/paging/recommendation/watchlist actions, backend unavailable | Monkeypatched requests and TestClient with SQLite; Streamlit AppTest | Browser-level visual/accessibility behavior |
| `tests/test_ingestion.py` | CSV extraction/validation, invalid/duplicate data, mocked batch insert and rollback | Temporary CSVs, mocked PostgreSQL insert/returning | Live PostgreSQL batch/idempotency behavior |
| `tests/test_movies.py` | List/search/detail, pagination and invalid requests | TestClient, SQLite fixtures | Large-catalogue performance |
| `tests/test_recommender_quality.py` | KNN/content/hybrid recommendations, sparse/unknown-user cases | Synthetic pandas data | Evaluation metrics and offline CLI |
| `tests/test_watchlist.py` | CRUD, status and ID validation, docs, error paths | Fake in-memory Session/TestClient; SQLite integration also in database/front-end tests | Live schema and DB error parity |
| `tests/test_recommendations.py` | Guarded manual KNN smoke, no pytest cases | Opens configured DB only when explicitly run as script | Misleading placement/name |
| Root `test_pipeline.py` | Prints ETL stages at import | Reads local raw CSV during pytest collection | No assertions; collection side effects |
| Root `test_content_based.py` | Fits content model/prints sample at import | Reads local raw CSV during pytest collection | No assertions; collection side effects |
| Root `test_hybrid.py` | Hybrid arithmetic assertions at import | Synthetic data; pytest collection side effects | Overlaps automated recommender cases |
| Root `test_hybrid_service.py` | Guarded manual DB hybrid runner | Configured DB only if explicitly run | No automated assertion or isolation |

The tests are safe for the configured production database **as currently collected**: database API tests override the session, ingestion uses mocks, and manual database runners are main-guarded. The suite does read raw CSVs at collection time. Do not run `load_data.py` or the manual DB scripts against production for testing. `tests/test_analytics.py` acts as a shared fixture source for other tests, causing test-module coupling.

## Confirmed problems

| Evidence | Impact | Scope / recommendation |
|---|---|---|
| `app/recommender/model.py` defines a second `evaluate_multi_seed_model` and calls `precision_recall_at_k` without importing/defining it. `evaluation.py` defines the intended metric and a separate evaluator. | That unused evaluator raises `NameError` once it reaches a qualifying user. | P1: remove or repair after explicit caller check; add targeted evaluation test. The serving KNN class is not affected by this missing symbol. |
| Only the KNN similar route is registered; content and hybrid have no API route. | Frontend can expose similarity only. | Document as current product scope; add routes only in a future phase. |
| Recommendation endpoint has no `response_model`. | OpenAPI and output validation do not describe its payload. | P1: define response schema with contract tests. |
| Lifespan loads every rating into pandas and trains KNN before `yield`; it raises if ratings are empty. | Startup work and memory grow with data; empty DB prevents API startup. | P1: measure and decide initialization strategy; do not change blindly. |
| `/health` returns a static success object without checking dependencies. | A response does not prove DB/model readiness. | P1: document semantics or introduce a separate readiness endpoint later. |
| `_genre_counts` selects all movie genres and splits them in Python; overview calls it too. | Repeated full catalogue scan for Home/Insights. | P2: benchmark, then consider database-side aggregation/caching. |
| `hybrid_service` normalizes component scores, then `calculate_hybrid_scores` normalizes its inputs again. | Repeated CPU work; normalization intent is harder to follow. | P2: retain displayed component scores but calculate final scores once after tests. |
| `README.md`, `app/schemas/rating.py`, and `app/utils/logger.py` are empty. | Missing project guidance; placeholder files create ambiguity. | P2/P3: fill README; investigate placeholder external use before removal. |
| Root manual `test_*.py` scripts do work at import time and are collected by pytest despite having no test functions. | Slower collection and noisy test semantics. | P2: move/rename or convert to isolated assertions after updating commands. |
| `load_data.py` uses `create_all`, while a separate SQL migration handles watchlist evolution. | `create_all` will not reconcile existing tables. | P0 operational: audit deployed schema before changing it; maintain migrations. |

## Potential risks requiring evidence

| Observation | Why it is a risk, not a confirmed failure | Verification |
|---|---|---|
| Prior watchlist runbook records missing `updated_at` in Render. | Current deployed schema was not queried; migration application is unknown. | Run read-only `scripts/schema_audit.py` with an authorized non-destructive connection and compare migration ledger/change record. |
| SQLite fixtures stand in for PostgreSQL. | SQL dialect, timestamp defaults, constraints and batch insert may differ. | Add isolated disposable PostgreSQL integration database, never Render production. |
| `evaluate_recommender.py` reads the movie CSV at import and performs large offline experiments in `main`. | Memory/runtime cost depends on dataset and environment. | Time offline runs on a non-production copy. |
| `plotly` and `python-multipart` are listed but have no direct source reference. | Could be transitive, deployment, or future requirements. | Dependency inventory before removal. |
| No pinned package versions. | Future installs can change behavior. | Generate tested lock/constraints workflow. |
| No CORS middleware. | Cross-origin browser clients would need configuration; Streamlit's server-side `requests` path does not. | Reassess only if adding browser-based client. |
| Frontend API client checks top-level JSON object, while pages validate selected fields individually. | Unexpected nested shapes may result in a page error or partial display. | Schema-driven client contract tests. |
| Discover genre/year filters operate on one fetched page. | Users could interpret filtered page as full-catalogue results. | Add server-side filters in a future backend phase or make UI scope explicit. |

## Security and operational observations

`.env` is ignored and its values were not read or printed. No credential literal was found in inspected source. `.gitignore` covers virtual environments and generated model pickles. The watchlist migration is additive and must be preserved; its actual application remains unverified. `get_db` closes request sessions, lifespan closes its startup session, and ingestion rolls back on errors. Analytics maps SQLAlchemy errors consistently; other routes vary. There are no ORM `relationship()` declarations, so no relationship-driven N+1 behavior was observed; recommendation metadata is fetched in one query and watchlist list joins movies. `print` is used in startup, ETL and manual scripts; there is no central structured logging. Several functions lack type hints, especially older pipeline/evaluation code.

## File cleanup evidence

| File | Current purpose | Evidence of usage | Issue | Recommendation |
|---|---|---|---|---|
| `app/schemas/rating.py` | Empty placeholder | No source reference found | No contract | Potential removal only after external import check |
| `app/utils/logger.py` and `app/utils/__init__.py` | Empty utility package | No application import found | No logging implementation | Investigate external use, then consider removal of placeholder package |
| `README.md` | Empty | Repository root convention only | No setup/readme guidance | Fill, not delete |
| `app/recommender/model.py` duplicate evaluator | Offline metric helper | No caller found; separate active evaluator in `evaluation.py` | Broken missing symbol and duplicate logic | Repair or remove function after tests |
| `test_hybrid.py` | Import-time arithmetic assertions | Collected by pytest; overlaps `tests/test_recommender_quality.py` | Redundant/manual test shape | Fold unique cases into tests, then consider removal |
| `tests/test_recommendations.py` | Manual DB KNN smoke | Guarded script, no pytest cases | Misnamed inside tests | Move to manual checks after command update |
| `test_pipeline.py`, `test_content_based.py` | Manual output checks | CLI and pytest import-time execution | Collection side effects | Rename/move or convert to pytest cases |
| `check_database.py`, `explore_data.py` | Manual diagnostics | Explicit CLI execution | Root clutter/import side effects | Optional move to `scripts/` |

No raw data, migration, local secret, or model artifact is proposed for deletion. Empty `models/` is an uncertain planned artifact location and should be preserved until persistence plans are clarified.
