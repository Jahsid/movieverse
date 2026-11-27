# Proposed structure and refactoring roadmap

> **Scope update (Stage 0B):** This is the earlier, narrow refactoring proposal for the existing application. Its P0–P3 labels are **priorities within baseline hardening**, not the approved Stage 0A–10 sequence. [ROADMAP.md](../../ROADMAP.md) is the authoritative development roadmap; [docs/decisions.md](../decisions.md) records the modular-monolith decision. No moves in this document have been approved for implementation merely by approving the roadmap.

This document proposes future work only. No moves, deletions, refactors, environment changes, migrations, or database actions were performed in this audit. Preserve the current API contracts while changing layout.

## Proposed target tree

```text
movieverse/
├── app/
│   ├── main.py
│   ├── api/{movies,recommendations,watchlist,analytics}.py
│   ├── database/{connection,models}.py
│   ├── schemas/{movie,watchlist,analytics,recommendation}.py
│   ├── services/{movie_service,recommendation_service,watchlist_service,analytics_service}.py
│   ├── data_pipeline/{extractor,validator,transformer,ingestion_service}.py
│   └── recommender/{model,content_based,hybrid,hybrid_service,evaluation}.py
├── frontend/{streamlit_app,api_client,config,components,styles,pages}.py
├── data/raw/{movies,ratings}.csv
├── migrations/{20261125_watchlist_updated_at.sql,README.md}
├── models/                         # retain for future persisted artifacts
├── scripts/
│   ├── load_data.py
│   ├── evaluate_recommender.py
│   ├── schema_audit.py
│   └── manual_checks/{check_database,explore_data,pipeline,content_based,hybrid,hybrid_service,recommendations}.py
├── tests/
│   ├── conftest.py                 # shared isolated fixtures
│   ├── api/{test_movies,test_watchlist,test_analytics}.py
│   ├── database/test_database.py
│   ├── data_pipeline/test_ingestion.py
│   ├── recommender/test_recommender_quality.py
│   └── frontend/test_frontend_integration.py
├── docs/architecture/              # the six audit documents
├── README.md
├── requirements.txt
└── .gitignore
```

This is deliberately close to the current layout. Subpackage `__init__.py` markers are omitted from the drawing for clarity, not proposed for deletion. The recommendation response schema was added in Stage 0C Part 2B. Agentic AI, LangGraph, MCP, and advanced data-engineering tools are explicitly deferred to the learning stages in the approved roadmap; they are not baseline refactoring requirements. No database replacement is proposed.

## Proposed moves or removals, with impact

| Current location | Proposed location/action | Reason | Import/command changes | Risk | Necessity |
|---|---|---|---|---|---|
| `app/services/ingestion_service.py` | `app/data_pipeline/ingestion_service.py` | Keep batch ingestion with ETL | Update `load_data.py` and ingestion test imports | Low; PostgreSQL dialect and mocks need retest | Optional |
| `load_data.py` | `scripts/load_data.py` | Group operational CLIs | Update AGENTS/README commands and imports/working-directory path handling | Medium; CSV paths and Python import root | Optional |
| `evaluate_recommender.py` | `scripts/evaluate_recommender.py` | Group offline evaluation | Update commands, imports, CSV path handling | Medium; experiment entry point | Optional |
| `check_database.py`, `explore_data.py` | `scripts/manual_checks/` | Separate diagnostics from app/test entry points | Update invocation commands; add main guards | Low | Optional |
| Root `test_pipeline.py`, `test_content_based.py`, `test_hybrid.py`, `test_hybrid_service.py` | `scripts/manual_checks/` or convert asserted cases to `tests/` | Distinguish smoke scripts; Part 2C already guarded execution without moving files | Update commands/import paths if moved; preserve unique assertions | Medium; manual commands change if moved | Optional after Part 2C |
| `tests/test_recommendations.py` | `scripts/manual_checks/recommendations.py` | It is a guarded database CLI, not a pytest case | Update documented command/import path | Low | Optional |
| Shared fixtures in `tests/test_analytics.py` | Moved to `tests/conftest.py` in Stage 0C Part 2C; shared seed data moved to `tests/helpers.py` | Remove cross-test-module fixture imports | Test assertions and fixture scopes preserved | Low; isolated suite verified | Completed |
| `app/recommender/model.py` second evaluator | Removed in Stage 0C Part 2A | Duplicated `evaluation.py` and called an undefined metric | No internal callers found; retained path has a regression test | External imports cannot be ruled out | Completed |
| `app/schemas/rating.py` | Consider removal | Empty and unreferenced | Check external imports; no internal changes expected | Low | P3 optional |
| `app/utils/logger.py` plus empty package | Consider removal or implement logging there | Empty and unreferenced | Check external imports; if implementing, add callers | Low | P3 optional |
| `README.md` | Filled in place in Stage 0B | Was an empty root entry document | None | Low | Completed documentation task |
| `app/recommender/evaluation.py` | Keep initially; optionally split by experiment later | Large module with multiple evaluation strategies | Update `evaluate_recommender.py` imports and tests | Medium | P3 optional |
| `data/raw/*`, `migrations/*`, `models/`, `.env` | Retain in current locations | Source data, migration, future artifacts, local secret | None | High if mishandled | Required retention |

## Priority roadmap

### P0: correctness and operations

1. On an authorized **read-only** PostgreSQL connection, compare deployed tables with ORM metadata using `scripts/schema_audit.py`; confirm whether the prepared watchlist migration has been applied. This audit did not establish production state. Apply schema changes only through a separate reviewed migration task.
2. Keep production out of destructive tests. If PostgreSQL contract coverage is required, provision a disposable isolated database with explicit configuration and teardown.

### P1: important architecture

1. Completed in Stage 0C Part 2A: reproduced the missing-metric failure, removed the unused duplicate, and tested the retained `evaluation.py` behavior. No internal caller depended on the removed function; external imports cannot be ruled out.
2. Completed in Stage 0C Part 2B: added a Pydantic response model for the similar-movie route and contract tests while preserving its existing wire format.
3. Define startup and readiness behavior for empty/large rating tables. Measure initialization time and memory before choosing persistence or lazy loading.
4. `README.md` was populated in Stage 0B with setup, test safety and current API/frontend scope. Continue improving migration guidance and consider version constraints for reproducible installs.

### P2: maintainability and measured performance

1. Convert import-time root smoke checks to true isolated tests or manual scripts; extract common fixtures to `tests/conftest.py`.
2. Benchmark genre aggregation and repeated Home/Insights requests; optimize only if latency warrants it.
3. Simplify hybrid score normalization with equivalence tests and document what each component score means.
4. Standardize database exception mapping/logging across routes while preserving HTTP codes. Add type hints to older ETL/evaluation functions where practical.
5. Clarify that Discover's genre/year filters apply to the fetched page, or plan server-side filters in a separate backend change.

### P3: optional cleanup

1. Move CLIs and manual checks into `scripts/`, updating documented commands and path resolution.
2. Confirm no external consumers of empty `rating.py` and `utils/`; only then consider removing placeholders.
3. Review unreferenced `plotly` and `python-multipart` requirements and optionally pin tested dependencies.
4. Split the large evaluation module only if maintaining experiments becomes difficult.

## Keep, improve, investigate, potential removal

- **Keep:** `app/main.py`, all four API routers, `database/connection.py` and `models.py`, active schemas/services/pipeline/recommender modules, all frontend modules, raw CSVs, migration files, `scripts/schema_audit.py`, `.gitignore`, `.env` as local untracked configuration, and automated tests.
- **Improve:** Keep `README.md` current; address startup/readiness handling, cross-test fixtures, manual checks collected by pytest, hybrid normalization, and error/logging consistency. The recommendation response was schemaed in Stage 0C Part 2B.
- **Investigate:** deployed PostgreSQL schema and migration state; empty `models/` persistence plans; external imports of placeholder files; direct need for `plotly`/`python-multipart`.
- **Potential removal after explicit verification:** empty `app/schemas/rating.py`, empty `app/utils/logger.py`/package, and redundant root `test_hybrid.py` after preserving unique assertions. The duplicate evaluator in `model.py` was removed in Stage 0C Part 2A. Do not delete source datasets, migrations, secrets, or artifacts.

Stage 0C Part 1B completed a read-only PostgreSQL schema comparison, Part 2A removed the duplicate evaluator, and Part 2B added a typed recommendation response. The 63-test result recorded by the 2026-11-25 audit is historical; Part 2B's isolated suite has 68 passing tests, still mostly SQLite/mocked behavior.
