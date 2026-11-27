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
| 0C | KNN startup wall time and peak RAM; recommendation p50/p95 latency | Unmeasured |
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
