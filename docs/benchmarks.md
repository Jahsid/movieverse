# Benchmark and evidence ledger

**No performance benchmark has been run or verified in Stage 0B.** The architecture audit reports 63 passing tests on 2026-11-25; that is a historical functional test result, not a performance measurement or a fresh run. Do not infer latency, throughput, model quality, memory use, or deployment reliability from it.

## Measurement rules

1. State the question and baseline before running the experiment.
2. Record date, commit or source revision, Windows/Colab environment, CPU/GPU, RAM, Python/package versions, data source and row counts, seed, and command.
3. Use the same split and dataset for model comparisons; prevent training/test leakage. Report repeated runs or variance when useful.
4. Record raw results, units, measurement method, and failure/skip conditions. Include the generated output location if reproducible and safe to retain.
5. Distinguish local, Colab, and deployed numbers. Do not publish secrets or private data in logs.
6. Mark a metric **unmeasured** until the command has actually run. Replace resume-target placeholders only with evidence linked here.

## Measurements to establish

| Stage | Baseline and proposed metric | Status |
|---|---|
| 0C | Local CSV/model training time, process peak RAM, direct model inference | Full-dataset offline KNN result below; separate 10,000-rating SQLite lifespan and in-process HTTP result below. Real network serving remains unmeasured. |
| 1–2 | Ingestion rows/sec and peak RAM; Parquet size/query time; lab setup cost and lag | Unmeasured |
| 3–5 | Precision/recall@K, coverage, artifact size, training time, startup and inference RAM/latency | Unmeasured |
| 6–8 | Retrieval recall/MRR, grounded-claim rate, task completion, tool failures, p95 latency | Unmeasured |
| 9–10 | Error rate, readiness/recovery time, integration onboarding time and acceptance result | Unmeasured |

## Result entry template

| Field | Value |
|---|---|
| Date, stage, question | To record |
| Revision and environment | To record |
| Dataset and split, row counts | To record |
| Baseline and candidate | To record |
| Exact commands and measurement method | To record |
| Raw runs and units | To record |
| Summary and uncertainty | To record |
| Limits and decision | To record |

## 2026-11-27 — Stage 0C Part 1 local recommender baseline

**Question:** What are current CSV loading, dense-pivot KNN training, memory, and direct similar-movie inference costs on the checked-in dataset, without an external database connection?

**Environment and revision:** Windows, Intel i3-1115G4, 8 GB RAM; `.venv-watchlist` Python 3.12.0; source revision `9f58cde`; pandas 3.1.1, NumPy 2.5.5, SciPy 1.18.1, scikit-learn 1.9.1. This is an offline run, not an API or PostgreSQL run.

**Input and method:** Read `data/raw/ratings.csv` with pandas using only `userId`, `movieId`, and `rating`; rename to `user_id`, `movie_id`, `rating`; call `MovieRecommender.train`. The file had **100,836 ratings, 9,724 distinct rated movies, and 610 users**. Wall times used `time.perf_counter`. Python allocation peak used `tracemalloc`; a separate run used Windows `GetProcessMemoryInfo` to read process working set and peak working set. Thirty direct `recommend(movie_id, k=5)` calls used the first 30 mapped movie IDs after one warm-up; p95 uses the nearest-rank observation (rank 29 of 30). No random seed or train/test split applies to this serving-path timing.

| Measurement | Observed value | Interpretation |
|---|---:|---|
| CSV read | 0.042 s | Three columns from local CSV; excludes DB transfer |
| Model `train` | 0.325 s | Includes pandas pivot, CSR conversion, and KNN fit; excludes CSV read and package imports |
| CSV read + train | 0.368 s | One run; timing subject to local load/cache |
| Python allocation peak (`tracemalloc`) | 115.77 MiB | Tracked allocations only, not total process memory |
| Process working set after imports / after CSV / after train | 152.75 / 157.97 / 162.37 MiB | Separate process run; working set at checkpoints |
| Process peak working set after train | 273.05 MiB | Separate process run; includes imports, CSV and training, not API/server |
| Dense float64 pivot size estimate | 45.25 MiB | `9,724 × 610 × 8` bytes for values alone; pandas copies/indices add overhead |
| Stored CSR arrays | 1.19 MiB | `data + indices + indptr` only, not estimator or Python objects |
| Direct inference p50 / p95 / max | 3.85 / 8.70 / 10.80 ms | 30 warmed calls, `k=5`; no HTTP or DB enrichment |

**Reproduction:** From the repository root, set `PYTHONDONTWRITEBYTECODE=1` and use `.venv-watchlist\Scripts\python.exe`. Read the three CSV columns as above, time `MovieRecommender.train` and 30 `recommend` calls with `time.perf_counter`, and inspect `model.movie_matrix` arrays. For process memory on Windows, query the same Python process with `GetProcessMemoryInfo`; `tracemalloc.get_traced_memory()` supplies the Python allocation peak. The full commands used were ephemeral stdin scripts and created no repository files. A controlled benchmark should repeat runs with fixed seeds/query sets and record distribution before using these figures as a performance claim.

**Limits:** No configured database was contacted. Actual API startup includes DB connection, query/materialization, application imports, and lifespan behavior, so **startup wall time and peak RAM remain unverified**. HTTP p50/p95 and live schema behavior remain unverified. The two memory methods ran in separate processes and should not be subtracted from each other.

## Stage 0C Part 2E — isolated application lifespan and in-process HTTP (2026-11-27)

**Question and environment.** How long does the actual FastAPI lifespan take to load ratings, build a DataFrame, train KNN, and become ready with a disposable local dataset, and what is warmed in-process recommendation latency? Measured on Windows 11 build 26300, 11th Gen Intel Core i3-1115G4, 7.75 GiB physical RAM, Python 3.12.0 in `.venv-watchlist`. Key installed packages: FastAPI 0.165.0, Starlette 1.10.0, SQLAlchemy 2.1.9, pandas 3.1.1, NumPy 2.5.5, SciPy 1.18.1, scikit-learn 1.9.1, HTTPX 0.28.1, pytest 9.2.0. [The tested dependency snapshot](../constraints-tested-py312-win.txt) records all 61 installed application/test distributions. The app source used here includes Stage 0C Parts 2A–2D; no benchmark optimization was made.

**Input and method.** `scripts/benchmark_startup.py` takes the first 10,000 rows of `data/raw/ratings.csv`: 66 users and 3,218 rated movies. It loads matching movie metadata, creates an in-memory SQLite schema, and inserts data before timing. It overrides application startup and request sessions to use only this engine; the configured external PostgreSQL database is never contacted. Each of three repetitions enters the **real FastAPI lifespan** through `TestClient`, checks `/ready`, warms the same similar-movie route five times, then times 30 in-process GET requests for movie 356 with `k=5`. Timing uses `time.perf_counter`; the rating-load component times the SQLAlchemy `.all()` call, DataFrame timing wraps construction, and training timing wraps the unchanged KNN training method. Lifespan time runs from just before TestClient entry until startup completes; time until readiness includes the first `/ready` response. HTTP p50 is the median and p95 is the nearest-rank observation. Windows `GetProcessMemoryInfo` gives current and process-high-water working set. Repetitions reuse one process and SQLite dataset, so later runs benefit from loaded imports, caches, and allocator state.

| Metric | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| Lifespan initialization | 0.1278 s | 0.0682 s | 0.0710 s |
| Rating `.all()` load | 0.0148 s | 0.0104 s | 0.0119 s |
| DataFrame construction | 0.0538 s | 0.0474 s | 0.0504 s |
| KNN training | 0.0192 s | 0.0084 s | 0.0063 s |
| Until first successful `/ready` response | 0.1415 s | 0.0724 s | 0.0744 s |
| Working set before / after readiness | 206.59 / 209.10 MiB | 209.41 / 209.45 MiB | 209.41 / 209.45 MiB |
| Process peak working set after readiness | 212.25 MiB | 212.65 MiB | 212.66 MiB |
| Warm HTTP p50 / p95, 30 requests | 5.06 / 9.38 ms | 5.09 / 9.00 ms | 4.78 / 8.03 ms |

Across all 90 measured HTTP requests, pooled p50 was **5.03 ms** and nearest-rank p95 was **9.00 ms**. These pooled values describe this one run, not a population guarantee. The process peak is a high-water mark since process launch and includes imports and SQLite setup; it is **not** startup-only peak memory. The app's existing startup print says “PostgreSQL,” but this benchmark uses SQLite exclusively. The earlier offline result used all 100,836 ratings and timed direct model calls, so its training, memory, and inference values are **not equivalent comparisons** with these 10,000-rating HTTP/lifespan results.

**Interpretation and reproduction.** “Cold startup” normally includes a fresh process, imports, connection establishment, and initialization. This measures lifespan entry after imports and data setup, with the first repetition colder than the subsequent two but not true cold process startup. “Warm inference” follows five warm-up requests; its HTTP time includes FastAPI routing, TestClient transport, SQLite metadata lookup, serialization, and model inference, whereas direct offline model latency omits those layers. In PowerShell from the repository root run `$env:PYTHONDONTWRITEBYTECODE = '1'`, then `.venv-watchlist\Scripts\python.exe -m scripts.benchmark_startup --ratings 10000 --repetitions 3 --requests 30`. The script forces an unreachable loopback `DATABASE_URL` before importing the app and makes no external connection. It does write only to disposable in-memory SQLite. No live PostgreSQL load, real server socket, multi-process startup, network latency, or production memory measurement was made.

## Stage 1E verification (2026-11-27)

On the isolated SQLite partial-rerun fixture, three CSV rows yielded one insert and two conflict skips. One existing derived user was counted separately. The injected ratings failure rolled back both parent inserts and retained the failed job. The isolated regression suite passed 107 tests in 18.34 seconds with one guarded PostgreSQL skip. These are correctness measurements. PostgreSQL throughput and peak memory remain targets.

## Stage 1F incremental ingestion checks

In the isolated CSV fixture, a corrected movie and rating plus a new movie produced one insert and two updates. Replaying the same bytes yielded three unchanged rows. After editing the stored rating, replaying the identical fingerprint repaired that one row. These measurements cover correctness on SQLite. PostgreSQL throughput, peak memory, and concurrent-load performance remain unmeasured.
