# MovieVerse: actual project structure

Audit date: 2026-11-25. This is a source and reference audit, not a database inspection. Counts below exclude `.git`, virtual environments, and cache directories. The worktree already contained modified and untracked files when the audit began; those files were inspected in their current state.

Stage 0B subsequently populated the root `README.md` and added `ROADMAP.md`, `docs/decisions.md`, `docs/progress.md`, and `docs/benchmarks.md`. The tree and counts below remain the **2026-11-25 application audit snapshot**, not a refreshed file count.

```text
movieverse/
├── .env                         # present; ignored; contents not inspected
├── .gitignore
├── .vscode/settings.json
├── AGENTS.md
├── README.md                    # empty at audit; populated in Stage 0B
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/{__init__,analytics,movies,recommendations,watchlist}.py
│   ├── database/{__init__,connection,models}.py
│   ├── data_pipeline/{__init__,extractor,transformer,validator}.py
│   ├── recommender/{__init__,content_based,evaluation,hybrid,hybrid_service,model}.py
│   ├── schemas/{__init__,analytics,movie,rating,watchlist}.py
│   ├── services/{__init__,analytics_service,ingestion_service,movie_service,recommendation_service,watchlist_service}.py
│   └── utils/{__init__,logger}.py
├── frontend/{__init__,api_client,components,config,pages,streamlit_app,styles}.py
├── data/raw/{movies,ratings}.csv
├── migrations/{20261125_watchlist_updated_at.sql,README.md}
├── models/                     # empty; no saved model artifacts
├── scripts/schema_audit.py
├── tests/{__init__,test_analytics,test_database,test_frontend_integration,
│          test_ingestion,test_movies,test_recommendations,
│          test_recommender_quality,test_watchlist}.py
├── tests/README.md
├── check_database.py
├── evaluate_recommender.py
├── explore_data.py
├── load_data.py
├── test_content_based.py
├── test_hybrid.py
├── test_hybrid_service.py
└── test_pipeline.py
```

Present generated directories: `.git/`, `.pytest_cache/`, `.venv/`, `.venv-watchlist/`, root and nested `__pycache__/`. `.vscode/` is local editor configuration. `.gitignore` covers `.env`, both virtual environments, Python bytecode/cache, pytest cache, `.vscode/`, `*.db`, and `models/*.pkl`; `git check-ignore` confirmed representative paths. No `.env.example`, `pyproject.toml`, `pytest.ini`, `data/processed/`, or `app/agents/` exists. Raw data are source datasets and must be retained. No database dump or model artifact was found.

| Folder | Relevant files | Responsibility | Main dependencies |
|---|---:|---|---|
| `app/` | 33 | FastAPI, database, ETL, recommender, schemas, services | FastAPI, SQLAlchemy, pandas, scikit-learn |
| `app/api/` | 5 | HTTP routes and validation | Services, schemas, `get_db` |
| `app/database/` | 3 | Engine, sessions, ORM tables | SQLAlchemy, PostgreSQL driver, `.env` |
| `app/data_pipeline/` | 4 | CSV extract, validate, transform | pandas |
| `app/recommender/` | 6 | KNN, content, hybrid, evaluation | pandas, NumPy, SciPy, scikit-learn |
| `app/schemas/` | 5 | Pydantic request and response contracts | Pydantic |
| `app/services/` | 6 | Queries, mutations, ingestion, recommendation response enrichment | ORM, PostgreSQL insert dialect |
| `app/utils/` | 2 | Empty package marker and logger placeholder | None |
| `frontend/` | 7 | Streamlit navigation, pages, components, styling, HTTP client | Streamlit, requests, pandas |
| `data/raw/` | 2 | MovieLens movies and ratings CSV inputs | ETL and offline checks |
| `migrations/` | 2 | Additive watchlist schema migration and runbook | PostgreSQL operational execution |
| `models/` | 0 | Intended artifact location; presently empty | None observed |
| `scripts/` | 1 | Read-only schema comparison CLI | SQLAlchemy, PostgreSQL |
| `tests/` | 10 | Automated tests, one manual runner, guidance | pytest, TestClient, SQLite test fixtures |
| `.vscode/` | 1 | Local Python terminal setting | Editor only |

The repository root also contains seven Python CLI/manual-check files and three configuration/documentation files (`AGENTS.md`, `README.md`, `requirements.txt`) plus `.gitignore` and `.env`. See [FILE_USAGE_AUDIT.md](FILE_USAGE_AUDIT.md) for each file and its usage evidence.
