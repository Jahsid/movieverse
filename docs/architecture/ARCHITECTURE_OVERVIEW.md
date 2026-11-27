# MovieVerse architecture overview

> **Scope:** This document describes the source architecture observed in the 2026-11-25 audit. The approved future stage sequence is in [ROADMAP.md](../../ROADMAP.md), and Stage 0B decisions are in [docs/decisions.md](../decisions.md). Planned modules and learning labs are not implemented features.

## Executive summary

MovieVerse has a working FastAPI backend and five-page Streamlit client. The live recommendation API exposes only similar movies from a KNN model trained at API startup. Content-based and hybrid recommendation code is used by offline evaluation and tests, but is not exposed through HTTP. The database is PostgreSQL in normal operation; automated tests use isolated SQLite fixtures or mocks. The current source tree contains operational scripts and manual checks alongside automated tests. No source files were changed during this audit.

## Runtime and backend

`app/main.py` constructs `FastAPI`, registers the movies, recommendations, watchlist and analytics routers, and supplies `/` and `/health`. Its lifespan opens a database session, reads all rating triples into pandas, trains `MovieRecommender` once, stores it on `app.state`, and closes the startup session. Startup fails if there are no ratings. There is no custom middleware or CORS configuration. `/health` returns a static healthy response and does not test live database or model availability.

| HTTP route | Input | Response contract | Implementation |
|---|---|---|---|
| `GET /` | None | Message object | `app/main.py` |
| `GET /health` | None | Status and application object | `app/main.py` |
| `GET /api/v1/movies/` | `page>=1`, `page_size=1..100` | `MovieListResponse` | `movie_service.get_movies` |
| `GET /api/v1/movies/search` | `q` nonempty, paging | `MovieListResponse` | `movie_service.search_movies` |
| `GET /api/v1/movies/{movie_id}` | Integer path ID | `MovieResponse`; 404 missing | `movie_service.get_movie_by_id` |
| `GET /api/v1/recommendations/similar/{movie_id}` | `k=1..20`, default 5 | Unschemaed object: `movie_id`, `title`, `recommendations` with IDs, titles, genres, similarity | `recommendation_service.get_similar_movies` and lifespan model |
| `POST /api/v1/watchlist/` | `WatchlistCreate` | `WatchlistItemResponse`; 201 | `watchlist_service.add_to_watchlist` |
| `GET /api/v1/watchlist/{user_id}` | Paging | `WatchlistResponse` | `watchlist_service.get_user_watchlist` |
| `PATCH /api/v1/watchlist/{user_id}/{movie_id}` | `WatchlistUpdate` | `WatchlistItemResponse` | `watchlist_service.update_watchlist_status` |
| `DELETE /api/v1/watchlist/{user_id}/{movie_id}` | None | 204 | `watchlist_service.remove_from_watchlist` |
| `GET /api/v1/analytics/overview` | None | `OverviewResponse` | `analytics_service.get_overview` |
| `GET /api/v1/analytics/genres` | None | `GenresResponse` | `analytics_service.get_genres` |
| `GET /api/v1/analytics/ratings` | None | `RatingsResponse` | `analytics_service.get_ratings` |
| `GET /api/v1/analytics/top-rated` | `limit=1..100`, `min_ratings>=1` | `MoviesResponse` | `analytics_service.get_top_rated` |
| `GET /api/v1/analytics/popular` | `limit=1..100` | `MoviesResponse` | `analytics_service.get_popular` |
| `GET /api/v1/analytics/watchlist` | None | `WatchlistAnalyticsResponse` | `analytics_service.get_watchlist` |

Routes mostly delegate to services. The recommendation route directly checks model readiness and movie existence, while the watchlist service raises HTTP exceptions itself. Analytics routes centralize SQLAlchemy failures into a rollback and HTTP 503; other routes have less uniform database error handling. The recommendation route lacks a declared Pydantic response model.

## Database architecture

`app/database/connection.py` loads `.env`, requires `DATABASE_URL`, normalizes older PostgreSQL URL schemes to psycopg, creates an engine with `pool_pre_ping=True`, and provides `SessionLocal` and a `get_db` yield dependency that closes sessions. Importing it constructs the engine. `load_data.py` calls `Base.metadata.create_all`; there is no general migration framework. The sole SQL migration is the additive watchlist migration in `migrations/`, accompanied by a runbook and a read-only `scripts/schema_audit.py` utility. The migration's application to any database was not established by this audit.

| Table / model | Primary key and important columns | Relations and constraints |
|---|---|---|
| `movies` / `Movie` | `movie_id`; title, pipe-delimited genres, release year | Indexed movie ID |
| `users` / `User` | `user_id`; optional username, created time | Referenced by ratings/watchlist |
| `ratings` / `Rating` | Composite `(user_id,movie_id)`; float rating, optional timestamp | FKs to users and movies; composite key prevents duplicate pair |
| `watchlist` / `Watchlist` | `id`; user/movie IDs, status, `added_at`, `updated_at` | FKs to users and movies; named unique `(user_id,movie_id)`; status server default `PLANNED`; `updated_at` nonnull server default and ORM on-update |
| `ingestion_jobs` / `IngestionJob` | `id`; filename, status, record counts, created time | Tracks each load; no ORM relationship |

The models declare foreign keys but no SQLAlchemy `relationship()` properties. The actual Render schema was **not** connected to or inspected during this audit; ORM definitions and the prepared migration are evidence of expected schema, not proof of deployed schema. A prior migration runbook describes a missing `watchlist.updated_at` column, which remains an operational verification item.

## Pydantic contracts

`schemas/movie.py` defines a single movie and paginated movie list. `schemas/watchlist.py` defines the four allowed statuses, create/update input, item output, and paginated list. `schemas/analytics.py` defines the overview, genre counts, rating counts, rated-movie lists, and watchlist analytics responses. `schemas/rating.py` is empty. These contracts are wired to the routes indicated above; only the recommendation route returns a plain dictionary without `response_model`.

## Service boundaries

`movie_service` uses SQLAlchemy for count, pagination, title `ILIKE`, and detail lookup. `recommendation_service` maps KNN results to one movie query and preserves rank. `watchlist_service` implements CRUD and transaction handling. `analytics_service` performs SQL aggregates; genre counts read every movie genre string and split it in Python. `ingestion_service` batches PostgreSQL `ON CONFLICT DO NOTHING` inserts and records each ingestion job. These services have clear roles, although HTTP exceptions in `watchlist_service` couple it to FastAPI.

## Frontend and dependencies

`frontend/streamlit_app.py` owns the five-page sidebar and shared state. `pages.py` renders Home, Discover, For You, My Watchlist and Insights; `api_client.py` centralizes HTTP methods, timeout, base URL and user-facing errors; `components.py` provides cards, neutral poster fallback and shared display elements; `styles.py` injects the dark theme; `config.py` reads the demo user ID. Streamlit calls FastAPI through `requests`; it does not access PostgreSQL directly. Cards can consume a future `poster_url`, but the current movie model/API does not provide one. Discover's genre/year selection filters the current fetched page, not the full server catalogue. For You calls only the similar-movie endpoint.

## Deployment and dependency notes

`requirements.txt` is unpinned. `plotly` and `python-multipart` have no direct import or form-route use in the inspected source; they warrant dependency review, not immediate removal. No hardcoded database credential was observed; `.env` contents were deliberately not read. `.gitignore` excludes local secrets and generated files. See [DATA_FLOW.md](DATA_FLOW.md) and [TECHNICAL_DEBT.md](TECHNICAL_DEBT.md) for detailed traces and evidence-qualified issues.
