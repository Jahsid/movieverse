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
| 0C | Local CSV/model training time, process peak RAM, direct model inference | Measured offline on 2026-11-27 below; API startup and HTTP latency unmeasured |
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
