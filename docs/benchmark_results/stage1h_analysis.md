# Stage 1H-E PostgreSQL benchmark analysis

This analysis is derived from [`stage1h_postgresql_matrix.jsonl`](stage1h_postgresql_matrix.jsonl), a sanitized copy of the user's 81-record result file. Its SHA-256 is `64b28802397523d7e1508435f661407d413bfe18f81692cb9e7a71a616196aeb`.

## Method and conditions

The benchmark ran on Windows 11, Python 3.12.0, an Intel Core i3-1115G4 laptop with 8 GB RAM, against the guarded local `movieverse_itest` PostgreSQL database. PostgreSQL server version and server-side CPU/IO statistics were not captured. Each dataset/batch/repetition group ran in a fresh child process; within it the benchmark ran initial ingestion, identical replay, then changed-data replay against a migrated schema. The guarded lifecycle checked database identity, required an empty public schema, held its advisory lock, upgraded through Alembic, and cleaned the benchmark-created schema. The user confirmed cleanup and unchanged pre/post raw CSV hashes.

The timer wraps each ingestion service call. Dataset generation, Alembic setup and cleanup are excluded. Throughput is processed source rows divided by that duration. Each source dataset is counted in all three scenarios and across all three repetitions; totals are cumulative visits, not distinct rows. Changed variants modified 74 small, 306 medium and 1,105 full records per run. Derived users were 570 for small and 610 for medium/full. Initial runs inserted those users; replays skipped them.

Peak memory is the process high-water working set for the entire child: imports, migration setup, all three scenarios and cleanup. The same group-level measurement appears on its three scenario records. It is not an independent scenario measurement. Offline ETL phase measurements are recorded separately in [`benchmarks.md`](../benchmarks.md#stage-1h-c3-offline-smoke-measurement) and must not be combined with PostgreSQL call timings.

Dataset source-record totals and fingerprints (base; changed):

| Dataset | Movies | Ratings | Source rows | Fingerprint (base) | Fingerprint (changed) |
|---|---:|---:|---:|---|---|
| Small | 2,439 | 5,000 | 7,439 | `5c676d408f9001c1d14f499ae131812918ee4309842746c7607abad8dc15b403` | `37d6a78a49201b3c05f9af192c8f36c02d363c6b3498898c3670ffeecc936dce` |
| Medium | 5,611 | 25,000 | 30,611 | `405192d249ede319aee12b0b5a6fe5395d1415c8bda92cbfe03fc389b3cdb9f4` | `498a4e43cc1e0cb84ac22f613344bf2e308537db2042096daf1938a99e208bbb` |
| Full | 9,742 | 100,836 | 110,578 | `9c1fd1eba2d2cbfabb921462100a4f2bc04840d84d913ab9d32a239afe67699d` | `656b534bff04fc073f78ca09e3c01b4827e4562b9aa1f2f1d759dee9b21e591f` |

## Per-configuration statistics

Durations and throughput show median (minimum–maximum) across three repetitions. Group peak memory also shows median (minimum–maximum) across those repetitions.

| Dataset | Batch | Scenario | Duration, s | Throughput, rows/s | Group peak, MiB |
|---|---:|---|---:|---:|---:|
| Small | 250 | Initial | 0.925 (0.921–1.039) | 8,039 (7,157–8,077) | 131.75 (131.46–132.08) |
| Small | 250 | Identical | 1.429 (1.377–1.470) | 5,205 (5,060–5,403) | 131.75 (131.46–132.08) |
| Small | 250 | Changed | 1.419 (1.396–1.453) | 5,244 (5,118–5,329) | 131.75 (131.46–132.08) |
| Small | 1,000 | Initial | 0.931 (0.879–0.935) | 7,992 (7,960–8,464) | 134.52 (134.48–134.91) |
| Small | 1,000 | Identical | 1.427 (1.378–1.581) | 5,212 (4,705–5,397) | 134.52 (134.48–134.91) |
| Small | 1,000 | Changed | 1.429 (1.403–1.509) | 5,207 (4,929–5,302) | 134.52 (134.48–134.91) |
| Small | 2,000 | Initial | 1.036 (0.885–1.057) | 7,178 (7,040–8,409) | 138.91 (138.77–139.01) |
| Small | 2,000 | Identical | 1.576 (1.425–1.667) | 4,722 (4,461–5,220) | 138.91 (138.77–139.01) |
| Small | 2,000 | Changed | 1.463 (1.462–1.885) | 5,086 (3,946–5,088) | 138.91 (138.77–139.01) |
| Medium | 250 | Initial | 3.425 (3.345–3.468) | 8,939 (8,826–9,150) | 145.93 (145.89–145.98) |
| Medium | 250 | Identical | 5.427 (5.369–5.555) | 5,640 (5,510–5,701) | 145.93 (145.89–145.98) |
| Medium | 250 | Changed | 5.611 (5.466–5.750) | 5,456 (5,323–5,600) | 145.93 (145.89–145.98) |
| Medium | 1,000 | Initial | 3.427 (3.281–3.427) | 8,933 (8,933–9,329) | 149.18 (149.08–149.29) |
| Medium | 1,000 | Identical | 5.741 (5.728–5.806) | 5,332 (5,272–5,344) | 149.18 (149.08–149.29) |
| Medium | 1,000 | Changed | 6.002 (5.482–6.130) | 5,100 (4,994–5,584) | 149.18 (149.08–149.29) |
| Medium | 2,000 | Initial | 3.358 (3.338–3.452) | 9,116 (8,868–9,170) | 151.80 (151.68–152.13) |
| Medium | 2,000 | Identical | 5.724 (5.457–6.191) | 5,348 (4,945–5,610) | 151.80 (151.68–152.13) |
| Medium | 2,000 | Changed | 5.547 (5.471–5.777) | 5,518 (5,299–5,595) | 151.80 (151.68–152.13) |
| Full | 250 | Initial | 11.508 (11.336–11.539) | 9,609 (9,583–9,754) | 185.76 (185.68–185.83) |
| Full | 250 | Identical | 19.070 (18.456–20.304) | 5,799 (5,446–5,992) | 185.76 (185.68–185.83) |
| Full | 250 | Changed | 18.624 (18.404–23.256) | 5,937 (4,755–6,008) | 185.76 (185.68–185.83) |
| Full | 1,000 | Initial | 11.274 (11.248–12.402) | 9,809 (8,916–9,831) | 186.63 (186.58–186.93) |
| Full | 1,000 | Identical | 18.949 (18.771–20.350) | 5,836 (5,434–5,891) | 186.63 (186.58–186.93) |
| Full | 1,000 | Changed | 19.301 (18.936–20.163) | 5,729 (5,484–5,839) | 186.63 (186.58–186.93) |
| Full | 2,000 | Initial | 12.440 (11.907–14.127) | 8,889 (7,827–9,287) | 194.20 (193.22–194.23) |
| Full | 2,000 | Identical | 19.905 (19.462–21.587) | 5,555 (5,122–5,682) | 194.20 (193.22–194.23) |
| Full | 2,000 | Changed | 20.908 (20.327–21.808) | 5,289 (5,070–5,440) | 194.20 (193.22–194.23) |

## Findings and recommendation

Across 81 records, cumulative processed source rows were 4,012,956 and summed ingestion-service duration was 634.477 seconds. The maximum throughput was 9,830.83 rows/s (full initial, batch 1,000); maximum whole-child-process peak working set was 194.23 MiB (full, batch 2,000). These totals include repeated visits to each dataset. Replays took longer than initial ingestion. This indicates the unchanged and changed UPSERT paths deserve separate profiling, but the current measurements cannot locate the database or client bottleneck.

Batch size 1,000 is the best balanced measured option: it had the fastest median full initial load and identical replay, near-best full changed replay, and less memory than batch 2,000. Batch 250 led some replay medians with slightly lower memory. Batch 2,000 had no consistent speed advantage and the highest full-data process peak. Keep the existing application default at 1,000; this recommendation is limited to this local setup. Three repetitions on one laptop/database, no server telemetry, no PostgreSQL version, and no concurrent workload limit generalization.

## Reproduction

Use the [guarded PowerShell runbook](stage1h_runbook.md). It sets an unreachable `DATABASE_URL`, enters the restricted local test password through a hidden prompt, sets the explicit benchmark opt-in and dedicated test URL, runs sequential configurations with unique repetition IDs, and verifies database identity, empty public schema and raw-file hashes before/after. Never put a database URL or password in command arguments or result files. For one configuration, the runner interface is:

```powershell
.\.venv-watchlist\Scripts\python.exe -m scripts.benchmark_scenarios `
  --size full --batch-size 1000 --repetitions 1 --repetition-start 2 `
  --seed 2026 --source .\data\raw --results $resultPath
```

The first complete 81-case result was provided by the user; it was not rerun for this analysis. Full isolated pytest is a separate correctness check and does not contact PostgreSQL.
