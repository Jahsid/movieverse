# MovieVerse development roadmap

This is the approved **sequence and learning scope**, not a claim that future features exist. Build a reliable modular monolith while deliberately practicing technologies relevant to seven engineering areas. Complete one stage at a time, preserve existing behavior, and record actual results in [docs/progress.md](docs/progress.md) and [docs/benchmarks.md](docs/benchmarks.md). The current source architecture is documented in [docs/architecture/](docs/architecture/ARCHITECTURE_OVERVIEW.md); proposed file paths below are created only when needed.

**Constraints:** zero additional expenditure, open-source/local tools first, Windows Intel i3-1115G4 with 8 GB RAM, optional free Google Colab for heavy experiments, and no required paid inference or hosted infrastructure. Stage 2 technologies and later AI frameworks are intentional **learning experiments**; they do not automatically become production dependencies. Free service limits can change and should be checked when a stage begins.

**Promotion rule:** an experiment joins the serving application only when a measured benefit, reproducible setup, tested failure behavior, acceptable CPU/RAM/latency, and a rollback path are documented. Keep public APIs stable unless a contract change is approved. Every stage closes with the implementation explanation, independent run/test instructions, related interview questions, and evidence for any resume claim required by [AGENTS.md](AGENTS.md).

## Stage 0A — Repository audit — completed

- **Objective:** Establish an evidence-based picture of the existing system.
- **Learn:** Dependency tracing, data flow, architecture boundaries, test isolation, and risk prioritization.
- **Features/work:** Read-only inventory, architecture and technical-debt analysis; no application feature.
- **Tools/frameworks:** Git, `rg`, source inspection, Markdown and Mermaid; **free alternatives:** PowerShell search and hand-drawn diagrams.
- **Dependencies:** Repository access only. **Expected file changes:** None in this stage; existing `docs/architecture/*` records capture the audit.
- **Acceptance criteria:** Current flow, important files, implemented/partial/missing behavior, debt, and migration options documented.
- **Testing:** Source-reference cross-check; no production database write. The architecture docs record a historical pytest result, not a Stage 0B run.
- **Performance metrics:** No new measurements; startup time, memory, and endpoint latency remain unmeasured.
- **Roles:** Data Engineer, ML Engineer, Forward Deployed Engineer.
- **Resume target, unverified:** “Mapped X application/data flows and prioritized Y risks by tracing MovieVerse source, tests, and database contracts.” Replace X/Y only with audited, cited counts.

## Stage 0B — Development foundation — completed

- **Objective:** Establish durable contribution rules, project entry documentation, stage gates, and evidence logs.
- **Learn:** Technical planning, architecture decision records, reproducibility, and honest measurement.
- **Features/work:** Documentation only: `AGENTS.md`, `README.md`, `ROADMAP.md`, architecture alignment, decisions, progress, and benchmarks templates.
- **Tools/frameworks:** Markdown and Git diff; **free alternatives:** Plain text files and local diagrams.
- **Dependencies:** Stage 0A audit. **Expected file changes:** The named documentation files only.
- **Acceptance criteria:** All stages have scope and gates; no future feature is presented as implemented; source and database remain unchanged.
- **Testing:** Check links, stage labels, file status/diff, and source claims; no runtime or database test needed for documentation-only changes.
- **Performance metrics:** Documentation completeness and link validity; no application performance claim.
- **Roles:** Forward Deployed Engineer, ML Engineer, Data Engineer.
- **Resume target, unverified:** “Established X reproducible development gates and Y decision/evidence records through a staged MovieVerse engineering plan.” Measure X/Y before use.

## Stage 0C — Baseline hardening and contract verification

- **Objective:** Confirm current behavior and remove correctness risks before expansion.
- **Learn:** API contracts, test fixtures, schema drift, migrations, and startup profiling.
- **Features/work:** Read-only deployed-schema comparison; isolated PostgreSQL test plan; recommendation response model; fix/retire the duplicate evaluator; shared test fixtures; README correction as needed. Measure startup before changing model loading.
- **Tools/frameworks:** Existing pytest, FastAPI/Pydantic, SQLAlchemy, `scripts/schema_audit.py`; **free alternatives:** SQLite unit fixtures plus disposable local PostgreSQL for dialect checks.
- **Dependencies:** Stage 0B; isolated DB access for PostgreSQL integration. **Expected file changes:** `app/schemas/recommendation.py`, `app/api/recommendations.py`, `app/recommender/model.py` or `evaluation.py`, `tests/conftest.py`, targeted tests and relevant docs, subject to a scoped implementation review.
- **Acceptance criteria:** Existing response shape preserved, duplicate evaluator resolved, test collection free of new side effects, schema status recorded without production mutation.
- **Testing:** Targeted evaluator/API tests, full pytest suite, isolated PostgreSQL contract checks when available; never migrate a shared database as a test.
- **Performance metrics:** API startup wall time and peak RAM on a specified dataset/machine; baseline endpoint p50/p95 latency if feasible. Record methodology and actual values only.
- **Roles:** ML Engineer, Backend Engineer, Forward Deployed Engineer.
- **Resume target, unverified:** “Reduced X contract failures and improved startup visibility by adding Y isolated checks and profiling the existing recommender.”

## Stage 1 — Reliable Data Engineering

- **Objective:** Make ingestion repeatable, explainable, and safe to rerun.
- **Learn:** Data contracts, idempotency, lineage, transactional loads, and schema evolution.
- **Features/work:** Dataset manifest, validation report, clear ingestion-job counts/status, versioned migration process, recovery instructions, and reproducible offline/guarded ETL benchmarks.
- **Tools/frameworks:** pandas, SQLAlchemy, PostgreSQL, pytest; **free alternatives:** CSV and Python standard library for small checks; SQLite only for non-dialect unit tests.
- **Dependencies:** Stage 0C schema knowledge and disposable DB. **Expected file changes:** `app/data_pipeline/*`, `app/services/ingestion_service.py`, `app/database/models.py` only if justified, `load_data.py`, `migrations/*`, `tests/test_ingestion.py`, docs.
- **Acceptance criteria:** Repeated import does not duplicate core rows; invalid data is rejected with an actionable report; job counts and schema version are understandable; benchmark scenarios produce reproducible, count-checked results with safe local database lifecycle and cleanup.
- **Testing:** Synthetic bad/duplicate CSVs, rollback cases, repeat load and migration upgrade on isolated PostgreSQL; deterministic offline samples and guarded benchmark matrix.
- **Performance metrics:** Rows processed/sec, rejected rows, duplicate rows, peak RAM, and total ingestion time by dataset size and batch size. Stage 1H measured a single local PostgreSQL environment; see [benchmark analysis](docs/benchmark_results/stage1h_analysis.md).
- **Roles:** Data Engineer, Forward Deployed Engineer.
- **Resume target, unverified:** “Processed X MovieLens records at Y rows/sec by adding validated, idempotent PostgreSQL ingestion with Z rejected-record visibility.”

## Stage 2 — Advanced Data Engineering learning lab

- **Objective:** Demonstrate orchestration, streaming, distributed processing, transformations, and columnar storage without burdening the core app.
- **Learn:** Airflow DAGs, Kafka events/consumer offsets, PySpark partitions, dbt models/tests, and Parquet layout. Compare each with the simple batch pipeline.
- **Features/work:** A proposed sequence begins with typed Parquet and DuckDB analysis, then dbt SQL models/tests, a local Airflow DAG, a bounded Kafka event/replay lab, and a PySpark comparison. Keep each tool in an isolated experiment; full scope, current installation constraints, alternatives and approval gates are in [the Stage 2 assessment](docs/stage2_advanced_data_engineering.md).
- **Tools/frameworks:** Apache Airflow, Kafka, PySpark, dbt, Parquet, optional DuckDB. **Free alternatives:** Windows Task Scheduler/cron concept, Python queue or file log, pandas, SQL views, CSV. Use Colab or limited containers only if local RAM permits.
- **Dependencies:** Stage 1 contracts and stable sample data. **Expected file changes:** `experiments/data_engineering/` or `notebooks/`, optional `data/processed/` outputs ignored by Git, lab-specific dependency file, tests and docs; no serving path changes by default.
- **Acceptance criteria:** Each approved lab is independently runnable, has a bounded dataset and cleanup instructions, compares behavior/resources with the simple pipeline, and does not require any of these tools for API startup. Approve each phase before implementation.
- **Testing:** DAG parse/one-run test, event replay/idempotency test, pandas–Spark result comparison, dbt tests, Parquet read/write schema round trip.
- **Performance metrics:** Setup time, throughput, end-to-end lag, data size, peak RAM, and Parquet size/query time versus CSV. Record hardware and sample size.
- **Roles:** Data Engineer, Platform Engineer.
- **Resume target, unverified:** “Reduced X sample-pipeline runtime or storage by Y% using Parquet/dbt/PySpark while validating Z events through an Airflow/Kafka learning workflow.” Claim only components actually measured.

## Stage 3 — ML Engineering and MLOps

- **Objective:** Make model training, evaluation, selection, and serving reproducible.
- **Learn:** Data splits, leakage, baselines, experiment tracking, artifact compatibility, and rollback.
- **Features/work:** Separate training from API startup; artifact manifest and loader; popularity/content baselines; versioned evaluation report; optional local experiment tracking.
- **Tools/frameworks:** scikit-learn, SciPy, pandas, pytest; optional local MLflow. **Free alternatives:** JSON/CSV run ledger and Git-tracked experiment configuration.
- **Dependencies:** Stage 1 data contracts and Stage 0C timing baseline. **Expected file changes:** `app/ml/`, `scripts/train.py`, `scripts/evaluate.py`, `app/main.py`, `app/services/recommendation_service.py`, artifact ignore rules, tests and docs.
- **Acceptance criteria:** Offline training produces a loadable, version-checked artifact; API restart does not silently retrain; failed load has documented behavior and rollback.
- **Testing:** Temporal holdout and baseline comparisons, artifact compatibility/corruption tests, cold-start paths, API contract regression, isolated integration run.
- **Performance metrics:** Precision/recall@K, coverage, startup time, model size, peak training/serving RAM, and p50/p95 inference latency.
- **Roles:** ML Engineer, MLOps Engineer.
- **Resume target, unverified:** “Improved recommendation precision@K by X% over Y baseline while cutting API startup time by Z% through reproducible offline training and versioned artifacts.”

## Stage 4 — Advanced recommendation algorithms and APIs

- **Objective:** Expose and compare useful personalized recommendations safely.
- **Learn:** Collaborative/content/hybrid ranking, cold start, candidate generation, scoring calibration, and online contracts.
- **Features/work:** Add user-oriented and content/hybrid API options, metadata enrichment, fallback ranking, and UI selection only after offline comparison.
- **Tools/frameworks:** Existing KNN, TF-IDF, SQLAlchemy, FastAPI; **free alternatives:** Popularity and genre heuristic baselines.
- **Dependencies:** Stage 3 model lifecycle and Stage 0C contracts. **Expected file changes:** `app/recommender/*`, `app/services/recommendation_service.py`, `app/api/recommendations.py`, recommendation schemas, `frontend/pages.py`, tests and docs.
- **Acceptance criteria:** Known users get ranked unseen movies; sparse/unknown users get an explicit fallback; existing similar-movie endpoint remains compatible.
- **Testing:** Seen-item exclusion, stable ordering, cold-start cases, temporal offline evaluation, API/UI integration tests.
- **Performance metrics:** Precision/recall@K, NDCG@K if justified, catalogue coverage, fallback rate, and p95 response time.
- **Roles:** ML Engineer, AI Engineer.
- **Resume target, unverified:** “Raised NDCG@K by X% and coverage by Y% by serving a measured hybrid recommender with a Z ms p95 latency.”

## Stage 5 — Deep Learning with PyTorch

- **Objective:** Learn neural recommendation/representation methods and compare them with simpler models.
- **Learn:** PyTorch tensors, datasets, training loops, regularization, embeddings, checkpointing, and CPU/GPU tradeoffs.
- **Features/work:** One bounded neural baseline or pretrained embedding experiment; export a compact artifact only if it improves a defined use case.
- **Tools/frameworks:** PyTorch, optional free Colab. **Free alternatives:** scikit-learn matrix factorization or TF-IDF baseline; CPU with small sampled data.
- **Dependencies:** Stage 3 evaluation protocol and artifact manifest. **Expected file changes:** `experiments/deep_learning/` or `notebooks/`, optional `app/ml/` loader, stage-specific dependency file, tests and docs.
- **Acceptance criteria:** Training is reproducible on a documented sample, evaluation uses the same split as a baseline, and promotion depends on measured gain and resource fit.
- **Testing:** Tensor shape and checkpoint round trip, reproducible seed check, leakage check, baseline comparison.
- **Performance metrics:** Quality metric@K, epochs/time, peak RAM/VRAM, artifact size, and CPU inference latency.
- **Roles:** Deep Learning Engineer, ML Engineer.
- **Resume target, unverified:** “Improved X recommendation metric by Y% over Z classical baseline using a reproducible PyTorch model within a measured memory budget.”

## Stage 6 — AI Engineering and semantic search

- **Objective:** Retrieve relevant movies from natural-language preferences with a measured fallback.
- **Learn:** Embeddings, vector similarity, indexing, query/document mismatch, and retrieval evaluation.
- **Features/work:** Build a metadata corpus, optional semantic embeddings, retrieval service and API; retain lexical/TF-IDF comparison. Obtain and document any additional metadata license before ingesting it.
- **Tools/frameworks:** Sentence Transformers or small open embeddings, NumPy/scikit-learn nearest neighbors; **free alternatives:** existing TF-IDF plus title/genre search. A separate vector database is optional.
- **Dependencies:** Stages 1 and 3 data/artifact contracts; Stage 5 only if its embedding is selected. **Expected file changes:** `app/ai/retrieval.py`, retrieval schema/API, artifact build script, tests and docs.
- **Acceptance criteria:** Deterministic, bounded top-K results with source fields; empty and ambiguous queries handled; serving runs within local resource limits.
- **Testing:** Labeled query set, lexical baseline comparison, index reload, malformed query, latency and memory checks.
- **Performance metrics:** Recall@K/MRR on labeled queries, index size, build time, p95 latency, peak RAM.
- **Roles:** AI Engineer, Search Engineer.
- **Resume target, unverified:** “Improved semantic retrieval recall@K by X% over lexical search across Y labeled queries at Z ms p95.”

## Stage 7 — Generative AI and RAG

- **Objective:** Generate grounded explanations or answers from retrieved movie facts.
- **Learn:** Prompt design, context construction, citations, hallucination evaluation, model licensing, and fallback behavior.
- **Features/work:** One bounded explanation/RAG endpoint with retrieved evidence, explicit uncertainty, and deterministic fallback; no paid API requirement.
- **Tools/frameworks:** Small locally runnable open model or optional Colab experiment; **free alternatives:** template-based explanations using retrieved fields. Add a serving library only after measuring the chosen model.
- **Dependencies:** Stage 6 retrieval and licensed metadata. **Expected file changes:** `app/ai/explanations.py`, prompts/config, API/schema, evaluation fixtures, tests and docs.
- **Acceptance criteria:** Claims are traceable to retrieved facts; unsupported queries decline or fall back; latency and memory are documented.
- **Testing:** Grounding set, adversarial/irrelevant context, no-result case, output contract and regression tests.
- **Performance metrics:** Supported-claim rate, unsupported-claim rate, answer usefulness on a rubric, token/output length, p95 latency and RAM.
- **Roles:** Generative AI Engineer, AI Engineer.
- **Resume target, unverified:** “Raised grounded-answer accuracy to X% across Y evaluated questions using retrieval-backed generation and a Z ms fallback.”

## Stage 8 — Agentic AI, LangGraph, and MCP

- **Objective:** Demonstrate a bounded multi-step recommendation workflow and interoperable tool access.
- **Learn:** State graphs, tool schemas, MCP client/server boundaries, human approval, traces, and failure recovery.
- **Features/work:** First express preference parsing → retrieval → ranking → explanation as plain functions; then reproduce a useful case with LangGraph and a narrowly scoped MCP tool. Keep write-capable tools behind explicit authorization.
- **Tools/frameworks:** Python, LangGraph, MCP SDK. **Free alternatives:** direct function calls and FastAPI endpoints; no hosted agent service required.
- **Dependencies:** Stages 4, 6 and optionally 7. **Expected file changes:** `app/ai/workflow.py`, optional `app/ai/mcp_tools.py`, tool schemas, trace tests and docs; experiment code separate if not promoted.
- **Acceptance criteria:** Finite step/tool limits, deterministic fallback, inspectable trace, no unauthorized database writes, and documented benefit over direct orchestration.
- **Testing:** Tool contract, malformed tool output, timeout/retry, prompt injection, step-limit and authorization tests.
- **Performance metrics:** Task completion rate, wrong-tool rate, average/max steps, p95 runtime, and per-run local resource use.
- **Roles:** Agentic AI Engineer, AI Engineer.
- **Resume target, unverified:** “Completed X% of Y preference tasks with a bounded LangGraph/MCP workflow while reducing Z failure mode versus direct orchestration.”

## Stage 9 — Production Engineering and deployment

- **Objective:** Make the chosen serving features operable, observable, and recoverable on a zero-budget-first path.
- **Learn:** Readiness, configuration, logs/metrics, CI, deployment contracts, backup/rollback, and resource planning.
- **Features/work:** Separate liveness/readiness, structured diagnostics, isolated CI checks, artifact deployment runbook, and a reproducible local deployment. A free-tier hosted demo is optional only after reviewing current limits.
- **Tools/frameworks:** FastAPI/Uvicorn, pytest, GitHub Actions free allowance where available, PostgreSQL, optional Docker. **Free alternatives:** local PowerShell scripts and manual runbooks.
- **Dependencies:** Stable Stage 3 artifact path and whichever later features are promoted. **Expected file changes:** `app/main.py`, config/logging modules as needed, workflow file, `docs/operations/`, tests and docs.
- **Acceptance criteria:** Fresh isolated deployment follows written steps; failures expose actionable status; rollback restores prior behavior; no secrets in repository/logs.
- **Testing:** Configuration validation, readiness failures, CI suite, isolated deployment smoke and rollback rehearsal.
- **Performance metrics:** Startup/readiness time, p95 API latency, error rate, peak RAM, recovery time, and zero-cost resource limits.
- **Roles:** ML Platform Engineer, Production Engineer, Forward Deployed Engineer.
- **Resume target, unverified:** “Reduced recovery time from X to Y minutes by implementing Z deployment checks, observability, and rollback procedures.”

## Stage 10 — Forward Deployed Engineering

- **Objective:** Demonstrate adapting MovieVerse to a concrete stakeholder need with measurable delivery and support.
- **Learn:** Requirements discovery, data mapping, integration contracts, solution tradeoffs, acceptance testing, handoff, and incident response.
- **Features/work:** Choose one realistic organization/demo scenario; import an authorized sample catalogue or preferences, map fields, configure recommendations, deliver an acceptance demo, and document handoff and limitations.
- **Tools/frameworks:** Existing API, ingestion checks, Streamlit, contract tests, Markdown runbooks. **Free alternatives:** local fixture files and a simulated customer environment; no paid connector required.
- **Dependencies:** Stages 1, 4 and 9; optional later AI features only if the scenario needs them. **Expected file changes:** scenario fixtures under `tests/fixtures/` or `experiments/`, integration adapter only if required, `docs/operations/` case study, tests and docs.
- **Acceptance criteria:** Stakeholder problem, success measure, data permissions, mapping, demo steps, acceptance result, and handoff are explicit and reproducible.
- **Testing:** Contract/field mapping, representative end-to-end scenario, failure and rollback, privacy and permissions review.
- **Performance metrics:** Time to onboard a new dataset, mapping error rate, task completion, response latency, and stakeholder acceptance result.
- **Roles:** Forward Deployed Engineer, Solutions Engineer, Data/ML Engineer.
- **Resume target, unverified:** “Onboarded X data sources in Y days and improved Z stakeholder workflow metric by delivering a tested MovieVerse integration and handoff.”

## How to update this roadmap

At the start of a stage, select one small deliverable and verify tool versions, licenses, free-tier limits, and hardware fit. At the end, update [progress](docs/progress.md) with what actually shipped, [benchmarks](docs/benchmarks.md) with reproducible measurements, and [decisions](docs/decisions.md) with material tradeoffs. A target resume bullet becomes usable only after its X/Y/Z values are supported by recorded evidence.
