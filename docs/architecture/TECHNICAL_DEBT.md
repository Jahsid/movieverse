# Technical debt and test architecture

> **Audit snapshot:** Findings and the 63-test run below are dated 2026-11-25. Stage 0B populated `README.md` and created development planning documents; no application debt or runtime behavior was changed in Stage 0B. See [progress](../progress.md) for current stage status.

## Verification performed

Read-only source/reference inspection plus `.venv-watchlist\Scripts\python.exe -m pytest -p no:cacheprovider -q` on 2026-11-25: **63 passed, 0 failed, 0 skipped, 1 warning, 34.75 s**. The warning is a Starlette TestClient deprecation concerning `httpx`. This is the most recent result recorded by that audit, not a Stage 0B test run; the earlier 60-test figure is historical. The configured Render database, migrations, manual DB runners, API server and Streamlit server were not run. Tests do not establish production schema correctness.

## Test files and isolation

| File | Covered behavior | Isolation / production access | Gaps |
|---|---|---|---|
| `tests/test_analytics.py` | Overview, genre/rating distributions, rankings, watchlist stats, empties, invalid parameters, docs, lifespan | Shared in-memory SQLite/StaticPool fixtures in `tests/conftest.py`; overridden dependency | PostgreSQL aggregation/dialect behavior |
| `tests/test_database.py` | FK and uniqueness, rollback, session close, watchlist persistence | Shared SQLite fixture with local FK pragma | Real PostgreSQL schema/migration contract |
| `tests/test_frontend_integration.py` | API client, page rendering/search/paging/recommendation/watchlist actions, backend unavailable | Monkeypatched requests and TestClient with SQLite; Streamlit AppTest | Browser-level visual/accessibility behavior |
| `tests/test_ingestion.py` | CSV extraction/validation, invalid/duplicate data, mocked batch insert and rollback | Temporary CSVs, mocked PostgreSQL insert/returning | Live PostgreSQL batch/idempotency behavior |
| `tests/test_movies.py` | List/search/detail, pagination and invalid requests | TestClient, SQLite fixtures | Large-catalogue performance |
| `tests/test_recommender_quality.py` | KNN/content/hybrid recommendations, sparse/unknown-user cases | Synthetic pandas data | Evaluation metrics and offline CLI |
| `tests/test_watchlist.py` | CRUD, status and ID validation, docs, error paths | Fake in-memory Session/TestClient; SQLite integration also in database/front-end tests | Live schema and DB error parity |
| `tests/test_recommendations.py` | Guarded manual KNN smoke, no pytest cases | Opens configured DB only when explicitly run as script | Misleading placement/name |
| Root `test_pipeline.py` | Manual ETL smoke output | Reads local raw CSV only when explicitly run | No automated assertions |
| Root `test_content_based.py` | Manual content model smoke output | Fits model only when explicitly run | No automated assertions |
| Root `test_hybrid.py` | Manual hybrid arithmetic assertions | Synthetic data; assertions run only when explicitly invoked | Overlaps automated recommender cases |
| Root `test_hybrid_service.py` | Guarded manual DB hybrid runner | Configured DB only if explicitly run | No automated assertion or isolation |

Stage 0C Part 2C moved shared function-scoped SQLite and TestClient fixtures to `tests/conftest.py`, and shared seed data to `tests/helpers.py`. The test configuration points `DATABASE_URL` at an unreachable loopback address before test modules import the application. Root manual checks no longer read CSVs, train models, print results, or assert during pytest collection. Database API tests override the session, ingestion uses mocks, and manual database runners remain main-guarded. Do not run `load_data.py` or database-dependent manual runners against production for testing. SQLite tests do not establish PostgreSQL dialect parity.

## Confirmed problems

| Evidence | Impact | Scope / recommendation |
|---|---|---|
| **Resolved in Stage 0C Part 2A:** `app/recommender/model.py` defined a second `evaluate_multi_seed_model` that called `precision_recall_at_k` without importing/defining it. The defect was reproduced on in-memory ratings. | The unused copy raised `NameError` for a qualifying user. | Removed the unreferenced copy; `evaluation.py` remains authoritative. `tests/test_evaluation.py` covers its retained behavior. The serving KNN class was not changed. |
| Only the KNN similar route is registered; content and hybrid have no API route. | Frontend can expose similarity only. | Document as current product scope; add routes only in a future phase. |
| **Resolved in Stage 0C Part 2B:** the recommendation endpoint previously had no `response_model`. | OpenAPI and output validation did not describe its payload. | Added `SimilarMoviesResponse` and contract tests while preserving the existing JSON and HTTP error behavior. |
| **Partly resolved in Stage 0C Part 2D:** lifespan still loads all ratings and trains KNN before `yield`, but empty ratings or training failure allow catalogue routes to start with recommendations unavailable. | Startup time and memory still grow with data. | Measure before choosing persisted artifacts or lazy loading; database query failure still stops startup. |
| **Resolved in Stage 0C Part 2D:** `/health` remains static liveness; `/ready` checks a live database query and trained model flag. | Deployment checks can distinguish a running process from full serving readiness. | Connection establishment has no new hard timeout; evaluate with an isolated deployment before relying on a strict probe deadline. |
| `_genre_counts` selects all movie genres and splits them in Python; overview calls it too. | Repeated full catalogue scan for Home/Insights. | P2: benchmark, then consider database-side aggregation/caching. |
| `hybrid_service` normalizes component scores, then `calculate_hybrid_scores` normalizes its inputs again. | Repeated CPU work; normalization intent is harder to follow. | P2: retain displayed component scores but calculate final scores once after tests. |
| At audit time, `README.md`, `app/schemas/rating.py`, and `app/utils/logger.py` were empty. Stage 0B populated `README.md`; the placeholders remain. | Placeholder files create ambiguity. | P3: investigate placeholder external use before removal. |
| **Resolved in Stage 0C Part 2C:** three root manual `test_*.py` scripts did work at import time despite having no pytest test functions. | Collection read CSVs, trained a model and ran assertions. | Added `main()` guards, preserving direct commands and existing manual assertions. A future move or conversion is optional. |
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
| `README.md` | Populated in Stage 0B | Repository entry point | Keep setup and architecture links current | Maintain, not delete |
| `app/recommender/model.py` duplicate evaluator | Removed in Stage 0C Part 2A | No internal caller was found; the CLI imports `evaluation.py` | Previously raised `NameError` | Retained evaluator is covered by `tests/test_evaluation.py` |
| `test_hybrid.py` | Guarded manual arithmetic assertions | Runs only by direct command; overlaps `tests/test_recommender_quality.py` | Redundant/manual test shape | Fold unique cases into tests only if useful |
| `tests/test_recommendations.py` | Manual DB KNN smoke | Guarded script, no pytest cases | Misnamed inside tests | Move to manual checks after command update |
| `test_pipeline.py`, `test_content_based.py` | Guarded manual output checks | Direct CLI; pytest collection no longer executes their work | No automated assertions | Optional conversion to pytest cases |
| `check_database.py`, `explore_data.py` | Manual diagnostics | Explicit CLI execution | Root clutter/import side effects | Optional move to `scripts/` |

No raw data, migration, local secret, or model artifact is proposed for deletion. Empty `models/` is an uncertain planned artifact location and should be preserved until persistence plans are clarified.
