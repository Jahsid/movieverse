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

## Stage 1G-B migration tooling (Windows, Python 3.12.0)

Alembic 1.20.1 and its Mako 1.4.3 dependency account for 3,099,080 bytes when summing installed files listed by their distributions. A fresh Python process running the offline baseline upgrade into StringIO peaked at 36,082,840 traced Python allocation bytes, measured with tracemalloc started before importing Alembic. This excludes untraced native allocations. SQLAlchemy 2.1.9 was already installed. Pip reported no broken requirements.

## Stage 1G-C isolated correctness checks (2026-11-28)

In the existing Windows Python 3.12 environment with PostgreSQL opt-in disabled, the migration and integration test modules passed 17 tests with 3 skipped in 1.30 seconds. The full isolated suite passed 123 tests with 3 skipped in 10.13 seconds. Both emitted the existing Starlette warning. These results measure isolated verification coverage; live migration evidence is pending.

## Stage 1G-D isolated verification

On Windows with PostgreSQL opt-in disabled, the focused migration and integration modules passed 19 tests with 3 skips in 2.31s. The complete suite passed 125 tests with 3 skips in 8.70s. Both runs emitted the existing Starlette warning. The isolated tests compare the offline metadata DDL to ORM columns and check drift and revision handling. PostgreSQL round-trip and historical-row verification for this revision await a live run.

## Stage 1G-E isolated correctness checks

The ingestion, migration and PostgreSQL modules passed 51 isolated cases with 3 guarded skips in 3.16s. The full suite passed 126 with 3 skips in 8.35s. Both runs used the existing Python 3.12 environment with live opt-in disabled and emitted the existing Starlette warning. This verifies job metadata behavior under SQLite and injected failures. Live evidence for Part E is pending.

## Stage 1G-F isolated checks

Focused loader, migration and integration modules: 27 passed, 3 guarded skips, 1 existing warning in 1.99s. Full isolated suite: 134 passed, 3 guarded skips, 1 existing warning in 11.07s with PostgreSQL opt-in disabled. Live no-write rejection checks are pending.
## Stage 1H-B deterministic sampling verification

With seed 2026, small produced 2,439 movies and 5,000 ratings, medium 5,611 movies and 25,000 ratings, and full preserved all 9,742 source movies and 100,836 ratings, including unrated movies. The medium changed variant modified 56 movie titles and 250 rating values. All rating references were present in their corresponding movie files. Repeated generation produced matching content fingerprints for all four outputs. The raw source file hashes were unchanged.

The focused sampler suite passed 5 tests with the existing Starlette warning. The full isolated suite passed 139 tests, skipped 3 guarded PostgreSQL tests, and emitted 1 existing warning in 8.21 seconds. No database connection or performance benchmark was involved.


## Stage 1H-C3 offline smoke measurement

With seed 2026, one fresh subprocess generated a small dataset with 2,439 movies and 5,000 ratings, for 7,439 source rows. Measured times were extraction 0.0226s, validation including referential integrity 0.0452s, sampling/transformation 0.0061s, fingerprinting 0.0988s, and total offline duration 0.1895s. Throughput was 39,253 source rows/s. Peak process working set was 95.39 MiB. The child initially failed to import the project package when launched as a script because its import path began at the scripts directory. Running it as a module from the repository root fixed the subprocess import path.

The memory figure is the whole child process high-water working set, including interpreter startup and imports. Phase timings are offline diagnostics and exclude PostgreSQL ingestion. These are one-run smoke results, not a repeated performance benchmark. The full isolated suite passed 142 tests, skipped 3 guarded PostgreSQL tests, and emitted 1 existing warning in 8.99s.

## Stage 1H-D guarded PostgreSQL smoke measurement

The user ran the guarded benchmark against the dedicated local `movieverse_itest` database on Windows 11 with Python 3.12.0, seed 2026, small dataset, batch size 1,000, and one repetition. The generated JSONL was inspected locally and contained three valid records:

| Scenario | Duration | Rows/s | Inserted | Updated | Unchanged | Derived users |
|---|---:|---:|---:|---:|---:|---:|
| Initial | 1.044474 s | 7,122.25 | 7,439 | 0 | 0 | 570 inserted |
| Identical replay | 1.563498 s | 4,757.92 | 0 | 0 | 7,439 | 570 skipped |
| Changed replay | 1.649212 s | 4,510.64 | 0 | 74 | 7,365 | 570 skipped |

All scenarios processed 7,439 source rows and met the count invariant. Initial and identical replay fingerprints were `5c676d408f9001c1d14f499ae131812918ee4309842746c7607abad8dc15b403`; changed replay fingerprint was `37d6a78a49201b3c05f9af192c8f36c02d363c6b3498898c3670ffeecc936dce`. Peak working set was 134.35 MiB for each record, but this is one high-water mark for the child process across imports, Alembic setup, all three scenarios and cleanup; it is not per-scenario memory. The timer covers the ingestion-service call and excludes dataset generation, migration setup and cleanup. User-reported post-run verification confirmed the guarded local identity and empty public schema. Current raw SHA-256 values matched the recorded baseline: movies `5a5f32dd9bb3797b8e728a1b98958789d2b13f294a69fdfbc5727f8a9611aa07`; ratings `aa289ca83157595d0df6aea1be6a4ded676ddc4385472e8313a8ed9805352646`.

This is a single smoke repetition on one small dataset, not a representative performance comparison. The isolated suite after subprocess fixes passed 164, skipped 3 guarded PostgreSQL cases, and emitted 1 existing warning in 11.00s. Stage 1H-E will run one sequential pass over all dataset and batch-size combinations before deciding whether three repetitions are reasonable. No default batch-size recommendation is supported yet.

## Stage 1H-E first benchmark matrix repetition

The user completed all nine dataset/batch configurations sequentially on the same Windows 11 / Python 3.12.0 laptop. I inspected the preserved JSONL at the user-provided temporary path: 27 unique records (three scenarios per configuration), repetition 1, totaling 1,337,652 cumulative source-record visits. Every record's processed count matched its dataset size and inserted + updated + unchanged equaled the processed count. Fingerprints were stable across initial and identical replay for a dataset, and changed replay had a distinct fingerprint. Derived users were 570 for small and 610 for medium/full; they were inserted only on initial runs and skipped on replays. All records state that timing is for the ingestion service call only, excluding dataset generation, migration setup and cleanup. The per-configuration peak is a whole-child high-water mark that covers imports, migration setup, all three scenarios and cleanup, repeated on each scenario row.

| Dataset | Batch | Initial s / rows/s | Identical replay s / rows/s | Changed replay s / rows/s | Group peak MiB |
|---|---:|---:|---:|---:|---:|
| Small | 250 | 0.925 / 8,039 | 1.429 / 5,205 | 1.419 / 5,244 | 132.08 |
| Small | 1,000 | 0.879 / 8,464 | 1.427 / 5,212 | 1.403 / 5,302 | 134.91 |
| Small | 2,000 | 0.885 / 8,409 | 1.667 / 4,461 | 1.885 / 3,946 | 138.91 |
| Medium | 250 | 3.425 / 8,939 | 5.369 / 5,701 | 5.466 / 5,600 | 145.93 |
| Medium | 1,000 | 3.281 / 9,329 | 5.728 / 5,344 | 6.130 / 4,994 | 149.29 |
| Medium | 2,000 | 3.338 / 9,170 | 6.191 / 4,945 | 5.471 / 5,595 | 151.68 |
| Full | 250 | 11.539 / 9,583 | 19.070 / 5,799 | 18.624 / 5,937 | 185.76 |
| Full | 1,000 | 11.274 / 9,809 | 18.949 / 5,836 | 19.301 / 5,729 | 186.63 |
| Full | 2,000 | 11.907 / 9,287 | 19.905 / 5,555 | 20.908 / 5,289 | 193.22 |

Dataset fingerprints (initial and replay; changed variant): small `5c676d408f9001c1d14f499ae131812918ee4309842746c7607abad8dc15b403` / `37d6a78a49201b3c05f9af192c8f36c02d363c6b3498898c3670ffeecc936dce`; medium `405192d249ede319aee12b0b5a6fe5395d1415c8bda92cbfe03fc389b3cdb9f4` / `498a4e43cc1e0cb84ac22f613344bf2e308537db2042096daf1938a99e208bbb`; full `9c1fd1eba2d2cbfabb921462100a4f2bc04840d84d913ab9d32a239afe67699d` / `656b534bff04fc073f78ca09e3c01b4827e4562b9aa1f2f1d759dee9b21e591f`.

This one-pass result suggests batch 1,000 was fastest for initial ingestion at all three sizes; replay results were mixed, and batch 2,000 was slower on the full dataset and used the largest group peak (193.22 MiB). The maximum observed throughput was 9,808.66 rows/s (full initial, batch 1,000). These are single observations and do not justify a default change or a batch-size recommendation. Replay paths took longer than initial loads in every configuration. The benchmark does not isolate database-server CPU, client-side phase timings, or per-scenario memory. The user subsequently verified database cleanup and confirmed the pre-run and post-run raw-file hashes matched the original baseline. The final three-repetition analysis, limits and recommendation are in [the Stage 1H-E analysis](benchmark_results/stage1h_analysis.md).

## Stage 1H-E complete three-repetition matrix

The preserved [81-record JSONL](benchmark_results/stage1h_postgresql_matrix.jsonl) was independently checked: 27 unique dataset/batch/scenario groups, three repetitions per group, no duplicate IDs, valid counts and fingerprints, and consistent measurement scopes. Total: 4,012,956 cumulative source-row visits and 634.477 seconds of measured ingestion-service calls. Maximum throughput was 9,830.83 rows/s; maximum whole-child high-water working set was 194.23 MiB. The user verified database cleanup and pre/post raw-file hashes. Full per-configuration medians, min/max ranges, methodology, recommendation and limitations are in [the analysis](benchmark_results/stage1h_analysis.md). Keep application batch size 1,000 for this measured setup; no universal claim is made.

## Stage 2A-5 Parquet and DuckDB

Full-dataset runs on Windows 11 / Python 3.12.0 / DuckDB 2.0.0 used one thread and 9,742 movies plus 100,836 ratings. Parquet storage was 1,472,136 B uncompressed, 938,669 B with Snappy and 667,517 B with Zstandard, versus 2,978,154 B of source CSV (50.57%, 68.48% and 77.59% savings). The 168-query-sample matrix covered seven workloads and four formats, with one first observation and five repeated measurements per configuration. The fastest median format varied: uncompressed Parquet led five workloads, Snappy led genre aggregation, and Zstandard narrowly led the single-column scan. These are local diagnostics, not production-scale claims.

The complete first/median/min/max, result-row throughput, process-memory ranges, conversion/validation phases, execution method, and sorted-versus-shuffled row-group-pruning evidence are in [the Stage 2A-5 analysis](benchmark_results/stage2a5_analysis.md). The [sanitized 172-record JSONL](benchmark_results/stage2a5_full_matrix.jsonl) preserves individual samples. Zstandard is the storage-density winner here; no codec is a universal query-speed winner. No core dependency or serving architecture changed.
