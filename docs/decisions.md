# Architecture decisions

This log records approved choices and unresolved questions. The [current-state audit](architecture/ARCHITECTURE_OVERVIEW.md) describes implemented behavior; [ROADMAP.md](../ROADMAP.md) defines future stages. Record the date, decision, reason, alternatives, consequences, and evidence when a material choice changes.

## D-001 — Retain a modular monolith

- **Status:** Approved in the Stage 0B request; implementation remains incremental.
- **Decision:** Keep FastAPI, Streamlit, and PostgreSQL as the core. Add modules at the stage that needs them; do not split into services merely for portfolio breadth.
- **Reason:** Existing code is understandable and functional; a single deployment fits the 8 GB development machine and zero-budget goal.
- **Alternatives considered:** Microservices, an event-driven serving system, or replacing the database. These add operational cost and complexity before a measured need exists.
- **Consequence:** Learning tools can run in independent labs and later integrate through explicit contracts if useful.

## D-002 — Serve measured features; isolate learning experiments

- **Status:** Approved as a development rule.
- **Decision:** Airflow, Kafka, PySpark, dbt, PyTorch, LangGraph, and MCP have deliberate learning stages. Their experiments do not automatically become API startup dependencies.
- **Reason:** Both skill development and a reliable product are objectives; optional labs allow each to be demonstrated within local hardware and free-resource limits.
- **Alternatives considered:** Install every framework in the core environment or omit them entirely. Neither meets both objectives well.
- **Consequence:** Promotion requires quality, resource, safety, test, and rollback evidence.

## D-003 — Zero additional expenditure first

- **Status:** Approved as a development constraint.
- **Decision:** Prefer existing packages, free/open-source local tools, and optional free Google Colab for heavy experiments. Do not make a paid hosted service or API essential.
- **Reason:** The project must remain independently runnable and maintainable on Windows, Intel i3-1115G4, 8 GB RAM.
- **Consequence:** Free-tier capacity is variable; stages must document limits and retain local or deterministic fallbacks.

## D-004 — Evidence before benchmark or resume claims

- **Status:** Approved as a documentation rule.
- **Decision:** Keep unmeasured values blank; mark resume bullets as targets until implemented and measured. Record method, environment, dataset, baseline, and raw result in [benchmarks.md](benchmarks.md).
- **Reason:** Reproducibility and credibility matter more than speculative performance claims.
- **Consequence:** Historical test results are labeled by date and never presented as a fresh run.

## D-005 — Separate liveness from full readiness

- **Status:** Implemented in Stage 0C Part 2D; pending review.
- **Decision:** Keep the existing `/health` response unchanged. Add `/ready`, returning 200 only when a `SELECT 1` database probe succeeds and the recommendation model is trained; otherwise return 503 with generic component statuses. Database query failure or memory exhaustion during lifespan stops startup. Empty ratings or ordinary model initialization failure allow catalogue and analytics routes to start, while recommendation requests and `/ready` return 503.
- **Reason:** A running process can serve catalogue functions without a model, but cannot serve database-backed routes without a database. Distinct endpoints make that partial state explicit without retraining on probe requests.
- **Alternatives considered:** Fail startup for every model problem; make `/health` depend on the model; declare the whole app ready when only catalogue routes work. Each would either lose useful catalogue access or obscure the existing `/health` contract and full recommendation readiness.
- **Consequences and limits:** A deployment using `/ready` as a whole-service gate may withhold catalogue traffic during model failure. The probe is one lightweight SQL statement but current engine connection settings do not guarantee a hard response-time bound. A later isolated deployment exercise can decide whether to add connection and statement timeouts or separate catalogue readiness.

## Open decisions for Stage 0C and later


| Question | Evidence needed before deciding |
|---|---|
| Was the watchlist SQL migration file actually executed? | The approved 2026-11-27 read-only audit found its intended schema shape, but no migration ledger. Execution history remains unknown; do not reapply based on the earlier audit. |
| What replaces startup KNN training? | Baseline startup time/RAM, artifact size/load time, failure handling and test results |
| Should ingestion or experiment scripts move? | Stable commands/import paths, contract tests, and a concrete maintenance benefit |
| Which advanced learning tools should be promoted? | Stage-specific quality, latency, cost, resource, and operational comparison |
| What metadata can support semantic search and RAG? | Source permission/license, data quality, usefulness, and storage requirements |

## Stage 1E ingestion transactions

Commit a processing job before extraction, then commit data and completion together. After rollback, update only a still-processing job so a lost commit acknowledgement cannot overwrite completed status. This uses the existing SQLAlchemy session, conflict handling and schema. A separate job store would add a consistency boundary and another operational dependency. Dedicated diagnostic columns are deferred to Stage 1G.

## Stage 1F incremental ingestion

Keep inserted counts compatible with Stage 1E and report updated and unchanged counts in the job result. Two bounded statements for conflicting movie and rating keys avoid PostgreSQL tuple-header heuristics and unlocked pre-read counts. The trade-off is an extra round trip for a batch with conflicts. Stage 1G owns durable fingerprint, update count and watermark schema decisions. Interview question: How can conditional UPSERT and RETURNING distinguish changes under concurrent loads?

## Stage 1G-B migration foundation

Use Alembic (MIT) as an optional, free local migration dependency. Reviewed Python revisions and a database revision ledger supply ordering that standalone repair SQL lacks. Keep declarative metadata independent of application engine initialization. Offline rendering selects the PostgreSQL dialect directly. Online verification reuses the dedicated integration guard and an explicitly supplied connection. The baseline contains frozen operations so later model edits cannot change historical DDL.

## Stage 1G-C adoption checks

Compare against a frozen public-schema contract using PostgreSQL catalogs. The older audit uses mutable ORM definitions and loads the application URL at import. PostgreSQL catalogs expose generator ownership, index definitions and constraint details without that initialization. A verified legacy fixture requires a separate explicit stamp tag. The application loader keeps its existing behavior.

## Stage 1G-D ingestion metadata schema

Revision `0002_ingestion_metadata` follows `0001_stage_1f`. It adds eight nullable job columns. Both the revision and ORM omit defaults so historical unknowns remain distinguishable from zero counts and known timings. Existing job fields retain their meanings. Capture the original Stage 1F ORM DDL in a test fixture so legacy adoption stays independent of the current ORM. The schema guard accepts the metadata shape only with the matching ledger entry; stamping still requires the frozen baseline.

## Stage 1G-E ingestion metadata writes

Store successful metadata in the dataset transaction. Sample elapsed milliseconds using the monotonic clock immediately before the terminal write; the returned elapsed seconds still include the successful commit. A separate post-commit metadata write could leave completed jobs without counts. Record only a fixed phase/code pair on failure, conditional on the job still being in processing.

## Stage 1G-F loader gate

Resolve the single head through the repository Alembic configuration and validate the ledger and frozen public-schema contract before opening input files. Checking the version string alone would miss drift. Keep provisioning and stamping outside the loader. Future schema revisions must supply their corresponding verification contract.

## Stage 1H batch benchmark and default

The guarded local matrix measured three dataset sizes, batch sizes 250/1,000/2,000, three ingestion scenarios and three repetitions on Windows 11 with Python 3.12.0. Retain the existing 1,000-row normal default. It was the best balanced result, especially on full initial ingestion and identical replay, while 2,000 had no consistent speed gain and the highest process peak. Replay performance varied by dataset and scenario, so this is a local recommendation only; no application default change is approved. Full measurements and method: [Stage 1H-E analysis](benchmarks.md#stage-1h-e-complete-three-repetition-matrix).
## Stage 2A-2 DuckDB experiment dependency

Use DuckDB only in a dedicated environment under `experiments/data_engineering/parquet_duckdb/`, pinned to the tested `duckdb==2.0.0` release. DuckDB's embedded SQL engine reads and writes Parquet directly, avoiding a PyArrow direct dependency for the planned lab. This is MIT-licensed, free local tooling compatible with Python 3.12 and Windows x86-64; the application dependency set and modular serving architecture stay unchanged. Initial smoke checks proved import, SQL, Parquet round trip and package consistency, but do not establish MovieLens performance or memory characteristics. Reassess version, license and platform prerequisites when rebuilding the lab environment.

## Stage 2A-3 CSV-to-Parquet conversion

Keep CSV as the immutable canonical source and write fully validated typed Parquet outputs only in temporary or explicitly ignored experiment storage. Use explicit types and multiset equality to preserve values and duplicate semantics. In the full conversion, Zstandard produced the smallest output (667,517 B, 4.462x vs. 2,978,154 CSV bytes), followed by Snappy (938,669 B) and uncompressed Parquet (1,472,136 B). This supports Zstandard when minimizing local storage is the priority, but no codec-speed, query-speed or memory comparison was made; no default/promotion decision follows from size alone.

## Stage 2A-4 analytical workload semantics

Keep analytics as an offline DuckDB experiment over CSV and Parquet; it does not alter the PostgreSQL serving path. Bind user filters, use deterministic tie-breaks, and define multi-genre counting as one movie/rating contribution per assigned genre, so category totals overlap. UTC is explicit for timestamp buckets. Cross-format correctness is established separately from plan shape. A pushed filter and available row-group statistics do not prove row-group pruning; the inspected full dataset had one row group per Parquet file, and query performance remains unmeasured.

## Stage 2A-5 local format benchmark disposition

Retain CSV as the canonical source and keep Parquet/DuckDB in the separate lab. In the measured MovieLens run Zstandard used the least space (667,517 B, 77.59% below CSV), while uncompressed Parquet had the fastest median for five of seven workloads; Snappy and Zstandard each led one. Full-row medians were close and workload ranges sometimes overlap. Select Zstandard for this experiment when storage is the priority, but do not choose a serving format or change application behavior from this single-machine test. Fresh child processes, five repeat observations, and rotated order improve consistency, but the shared OS cache is not cold and the dataset is small. The separate sorted-data plan showed 5/50 row groups scanned versus 50/50 for shuffled data with an identical result; row-group ordering/statistics are therefore part of the observed pruning behavior.

## Stage 2A-6 experiment closeout

Keep Stage 2A complete and isolated: it establishes file conversion, data parity, query-plan and local performance learning, not a reason to replace PostgreSQL or change the application. The corrected JSONL is the retained evidence; preliminary benchmark observations are not combined with it. The experiment environment remains pinned separately from core application dependencies. Stage 2B should begin with dbt plus the DuckDB adapter only after current compatibility and package constraints are verified and approval is given.
