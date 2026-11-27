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

## Open decisions for Stage 0C and later

| Question | Evidence needed before deciding |
|---|---|
| Is the watchlist SQL migration already applied to the configured PostgreSQL database? | Read-only schema audit against the intended target; no migration in Stage 0B |
| What replaces startup KNN training? | Baseline startup time/RAM, artifact size/load time, failure handling and test results |
| Should ingestion or experiment scripts move? | Stable commands/import paths, contract tests, and a concrete maintenance benefit |
| Which advanced learning tools should be promoted? | Stage-specific quality, latency, cost, resource, and operational comparison |
| What metadata can support semantic search and RAG? | Source permission/license, data quality, usefulness, and storage requirements |
