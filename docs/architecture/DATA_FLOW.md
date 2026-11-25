# Verified MovieVerse data flows

Solid arrows below are implemented in the inspected source. Dashed arrows are explicitly absent or future integrations. No production database calls were made for this audit.

## Serving architecture

```mermaid
flowchart LR
    UI[Streamlit: streamlit_app / pages] -->|requests via api_client| API[FastAPI routers]
    API --> MS[movie_service]
    API --> WS[watchlist_service]
    API --> AS[analytics_service]
    API --> RS[recommendation_service]
    MS --> ORM[SQLAlchemy Session / models]
    WS --> ORM
    AS --> ORM
    RS --> ORM
    ORM --> PG[(PostgreSQL)]
    PG -->|ratings at startup| KNN[MovieRecommender KNN]
    KNN -->|app.state.recommender| RS
```

`get_db` yields a request session and closes it afterward. The startup session reads all ratings and closes in `finally`. The recommendation API relies on the trained object on application state; it returns 503 when that object is unavailable. The root health endpoint does not query PostgreSQL.

## ETL: raw CSV to tables

```mermaid
flowchart LR
    M[data/raw/movies.csv] --> E[extractor: pandas read_csv]
    R[data/raw/ratings.csv] --> E
    E --> V[validator: required columns, IDs, titles, ratings, timestamps, duplicates]
    V --> T[transformer: types, clean genres/title, extract year]
    T --> I[ingestion_service: batches and ingestion job]
    I -->|PostgreSQL ON CONFLICT DO NOTHING| DB[(users / movies / ratings / ingestion_jobs)]
```

`load_data.py` explicitly calls `Base.metadata.create_all`, then extraction, validation, transformation, and `load_movie_data`. Movie validation requires positive integral movie IDs, nonblank title and unique movie IDs. Rating validation requires user/movie IDs, rating and timestamp, enforces positive IDs, half-star values from 0.5 through 5.0, integral timestamp and unique user/movie pairs. Transformer strips titles, fills missing genres, casts fields, and derives release year from a title suffix. The ingestion service inserts users, movies and ratings in foreign-key order in batches of 1,000 using PostgreSQL conflict handling, records inserted counts in an `IngestionJob`, commits, and rolls back on failure. Repeated core rows are skipped, but each run creates a new ingestion-job record. Validation errors stop before ingestion. This is a PostgreSQL-specific ingestion path; SQLite tests mock its insert behavior.

## Recommendation paths

```mermaid
flowchart LR
    PG[(PostgreSQL ratings)] -->|startup load to pandas| P[Item-user matrix / CSR]
    P --> K[Cosine nearest-neighbor KNN]
    K --> S[recommendation_service: enrich movie metadata]
    S --> A[GET /recommendations/similar/movie_id]
    A --> UI[Streamlit For You]

    CSV[data/raw/movies.csv] --> C[ContentBasedRecommender: genre TF-IDF]
    K --> H[Hybrid: normalize + weighted scores]
    C --> H
    PG -->|offline CLI rating read| EV[Evaluation experiments]
    K --> EV
    C --> EV
    H --> EV
    C -. no API route .-> A
    H -. no API route .-> A
```

`MovieRecommender.train` pivots user/movie ratings to a movie-user matrix, fills absent ratings with zero, stores a sparse CSR matrix and fits cosine `NearestNeighbors`. `recommend` finds neighboring movie IDs and similarity scores; `recommend_for_user` uses liked movies as seeds, aggregates candidate scores and excludes already-rated movie IDs. The live route exposes only `recommend` via `recommendation_service`, which performs one movie lookup for candidate metadata.

`ContentBasedRecommender.fit` builds TF-IDF vectors from pipe-separated genres and fits cosine neighbors. It supports similar movies and a weighted genre profile for a user's ratings, excluding seen movies. `hybrid_service.recommend_hybrid_for_user` combines KNN, content and popularity candidate scores with weights. `evaluation.py` computes precision/recall and random/temporal/popularity/rolling comparisons. `evaluate_recommender.py` loads CSV movie metadata and PostgreSQL ratings for offline experiments. Neither content nor hybrid has an HTTP route, and no model save/load artifact path was found. `models/` is empty. The second `evaluate_multi_seed_model` in `model.py` is not called and has a missing symbol; the CLI imports the distinct implementation from `evaluation.py`.

## Watchlist request flow

```mermaid
flowchart LR
    UI[My Watchlist: title search, demo user] --> C[api_client GET / POST / PATCH / DELETE]
    C --> A[Watchlist API: Pydantic validation]
    A --> S[watchlist_service: user/movie checks, CRUD, commit/rollback]
    S --> ORM[SQLAlchemy Watchlist + Movie + User]
    ORM --> PG[(PostgreSQL)]
```

The page uses `MOVIEVERSE_DEMO_USER_ID` with fallback 1. It resolves movie titles through the movie search API, then sends IDs internally. Status values are `PLANNED`, `WATCHING`, `COMPLETED`, `DROPPED`. The list service joins movie metadata and pages results. Mutations commit; integrity/SQL errors are rolled back and mapped to HTTP errors. A prior runbook records a watchlist schema mismatch, so live operation depends on confirming migration state separately.

## Analytics request flow

```mermaid
flowchart LR
    UI[Home and Insights] --> C[api_client GET]
    C --> A[Six analytics routes]
    A --> S[analytics_service]
    S -->|COUNT AVG MIN MAX GROUP BY| PG[(PostgreSQL)]
    S -->|select movie genres, split and count in Python| G[Genre distribution]
    PG --> G
```

The analytics service calculates totals, rating distribution, ranking, and watchlist status/movie counts from stored records. Genre distribution is a full scan of the movie `genres` column followed by a Python split and de-duplication per movie. Home uses overview, popular, top-rated and genres; Insights uses all six endpoints. Rankings use aggregates and stable tie breaks. Empty rating tables return null average/min/max and an empty distribution, while counts remain zero.

## Frontend page mapping

| Page | Implemented calls | Notes |
|---|---|---|
| Home | Analytics overview, popular, top-rated, genres; catalogue links | Uses neutral poster fallback |
| Discover | Movie list/search/detail; watchlist POST action | Genre/year filters apply to fetched page only; pagination is server-side |
| For You | Movie search; similar-movie recommendation | Title selection hides technical ID; no personalized/hybrid HTTP API |
| My Watchlist | Movie search; watchlist GET/POST/PATCH/DELETE | Demo user setting, status selection, refresh after actions |
| Insights | All six analytics GET routes | Tables and Streamlit charts use API values |
