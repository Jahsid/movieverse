# Stage 2A learning checkpoint: Parquet and DuckDB

**Status:** The Stage 2A implementation and measurements are complete. This records project evidence and a study guide; it does not establish that an individual has mastered every concept.

## Architecture and data flow

MovieVerse's production batch path and PostgreSQL serving database were left unchanged. The lab lives in `experiments/data_engineering/parquet_duckdb/` and uses its own Python 3.12 environment with only `duckdb==2.0.0` as a direct dependency. The MovieLens CSV files in `data/raw/` remain canonical and read-only.

```text
canonical CSV files
      |
      +--> explicit typed DuckDB CSV scans --> validation and fingerprints
      |                                       |
      |                                       +--> CSV analytics
      |                                       +--> temporary Parquet (none / Snappy / Zstandard)
      |                                                   |
      +-----------------------------------------> equivalent DuckDB analytics
                                                          |
                                            signatures, plans, timings, memory
                                                          |
                                             sanitized JSONL and written analysis
```

Conversion creates temporary outputs by default, checks schema and row counts, applies source quality constraints, compares typed row multisets in both directions, checks raw input hashes and cleans the temporary directory. Analytics runs the same SQL concepts over CSV and each Parquet codec and compares deterministic result signatures. The benchmark starts fresh worker processes, rotates formats, fully consumes query results, records first observations separately from five later repetitions, and preserves JSONL as it runs. A separate row-group exercise creates temporary sorted and hash-shuffled files to make pruning observable.

## Important files

| File | Responsibility |
|---|---|
| `conversion.py` | Explicit source schemas, quality checks, CSV-to-Parquet `COPY`, schema and multiset validation, raw hashes, temporary-output lifecycle. |
| `analytics.py` | Shared CSV/Parquet source views; deterministic aggregation, filters, joins, UTC time buckets, anti-join and window queries; plan inspection and result parity. |
| `benchmark.py` | Workload definitions, full result consumption and signatures, fresh-process measurement, time/memory reporting, order rotation, JSONL output and failure handling. |
| `row_group_pruning.py` | Bounded sorted-vs-shuffled multi-row-group pruning demonstration, correctness comparison and cleanup. |
| `test_conversion.py`, `test_analytics.py`, `test_benchmark.py` | Standard-library fixture-based checks; DuckDB remains optional to the application environment. |
| `requirements.txt` | Exact isolated dependency pin `duckdb==2.0.0`. |
| `README.md` | Setup, reproducible commands, semantics, results and limits for the experiment. |
| `docs/benchmark_results/stage2a5_analysis.md` | Human-readable corrected measurement analysis. |
| `docs/benchmark_results/stage2a5_full_matrix.jsonl` | Sanitized record-level evidence for the corrected full run. |

## Storage and database concepts

### CSV and Parquet; row and column layouts

CSV is a portable text interchange format. Values are parsed from text and a reader may scan bytes for fields even when a query needs only a few columns. Parquet is a typed, compressed columnar file format. It groups rows into row groups, then stores column chunks and pages with metadata/statistics. A projection can read only selected column chunks; predicates may skip row groups when their statistics prove they cannot match. Parquet is not an execution engine: DuckDB supplies the SQL planner and operators.

Row-oriented PostgreSQL storage is suited to transactional access to complete records, constraints, updates and concurrent application writes. Columnar Parquet is suited to scans and aggregations across selected columns. OLTP emphasizes small transactions and current application state; OLAP emphasizes scans, joins and aggregates. PostgreSQL can perform analytics, and DuckDB can read/write files, but their operational roles differ here. The experiment does not justify replacing PostgreSQL.

DuckDB is an embedded, in-process analytical engine: there is no database server to provision for this offline lab. It is a convenient local comparator for PostgreSQL-backed MovieVerse, but does not reproduce PostgreSQL concurrency, network, indexing or transaction behavior.

### Explicit schema and logical equality

The converter declares `movieId`/`userId` as integers, `title`/`genres` as strings, `rating` as double, and `timestamp` as 64-bit epoch seconds. This prevents inference from changing identifier or timestamp types. `EXCEPT ALL` in both directions checks typed row multisets, including duplicate multiplicity, without depending on output order. Byte-level SHA-256 identifies a particular physical source file; CSV and Parquet hashes are expected to differ even when their decoded rows are logically equal.

### Compression

Uncompressed Parquet avoids codec work but is larger. Snappy generally trades stronger density for fast compression/decompression. Zstandard generally compresses more densely at additional CPU cost. Actual performance also depends on data entropy, layout, caching and query shape; codec names alone do not predict the fastest query.

## Query execution concepts

- **Projection pushdown / column pruning:** request only needed columns so a Parquet reader can avoid unrelated column chunks. The recorded Parquet selective plan projected `movieId, rating` within `READ_PARQUET`.
- **Predicate pushdown:** apply a filter close to the scan. The Parquet plan showed `rating >= 4.5` in its scan; CSV showed the projected scan with a separate Filter operator. A plan is evidence of plan placement, not automatically proof of bytes skipped.
- **Row-group pruning:** min/max statistics can rule out groups outside a predicate range. The primary files had one row group each, so they could not demonstrate group skipping.
- **Joins and aggregations:** movie/rating queries join on `movieId`, then aggregate rating rows. Plans showed hash joins and aggregate operators. Genre totals overlap because each multi-genre movie and its ratings contribute to every assigned genre.
- **Window functions:** top-N-per-genre uses a partitioned `ROW_NUMBER` with deterministic tie breaks. This is different from `RANK`, which preserves tied rank numbers and may return more than N rows.
- **EXPLAIN / EXPLAIN ANALYZE:** inspect logical/physical operators and measured operators respectively. Correctness runs and plan diagnostics were excluded from the timed query intervals.

## Measured evidence

Environment: Windows 11, Python 3.12.0, DuckDB 2.0.0, Intel Core i3-1115G4, 8 GiB RAM and one DuckDB thread. Full input was 9,742 movies and 100,836 ratings (110,578 total records; 2,978,154 CSV bytes). The corrected benchmark contains 172 JSONL records: 3 conversions, 168 query observations (7 workloads × 4 formats × first + 5 repeated samples) and 1 summary. Formats were rotated and queries ran sequentially in fresh child processes.

| Representation | Total bytes | CSV/Parquet ratio | Bytes saved |
|---|---:|---:|---:|
| CSV source | 2,978,154 | 1.000× | 0% |
| Parquet uncompressed | 1,472,136 | 2.023× | 50.57% |
| Parquet Snappy | 938,669 | 3.173× | 68.48% |
| Parquet Zstandard | 667,517 | 4.462× | 77.59% |

Across the seven median query results, uncompressed Parquet was fastest in five workloads, Snappy in genre analytics, and Zstandard narrowly in a single-column scan. Thus the densest file was not the universal query winner. Query-process peak working set reached 61.004 MiB; conversion child peaks ranged 64.176–65.414 MiB. These are process lifetime high-water marks including setup and correctness work, not operator-level memory. The full median/minimum/maximum table, first observations, throughput semantics, validation timings and limitations are in [the corrected analysis](../benchmark_results/stage2a5_analysis.md); individual sanitized observations are in [the JSONL](../benchmark_results/stage2a5_full_matrix.jsonl).

In the separate row-group demo, sorted and hash-shuffled data returned the same 8,167 ratings and rating sum 28,047.5. EXPLAIN ANALYZE reported 5/50 groups scanned for timestamp-sorted data and 50/50 for hash-shuffled data; estimated data read was 52.6 kB versus 506.0 kB. This is evidence for that layout, filter and DuckDB version only.

Query duration includes SQL execution and fetching the complete result; result rows/sec is not source-scan throughput for aggregate queries. Query children are fresh, but the Windows file cache is shared. First observations are not guaranteed cold-cache results; five repeats are a small sample. Conversion measurements are single observations. Neither the dataset nor machine represents production-scale behavior. Original CSV hashes were unchanged, temporary files were removed, and no application dependency or serving path changed.

## Engineering decisions and trade-offs

1. Keep raw CSV canonical; Parquet is derived and reproducible.
2. Keep DuckDB and its exact dependency pin in a separate experiment environment.
3. Prefer temporary outputs and explicit ignored output locations; never write generated files into `data/raw/`.
4. Validate logical values separately from physical file hashes.
5. Run query formats in fresh processes and rotate order to reduce interpreter reuse/order bias, while documenting that OS cache remains shared.
6. Record time, memory, correctness, and storage separately; do not treat output-row throughput as source throughput for every query.
7. Keep the experiment out of the core serving architecture absent a measured product need.

## Interview questions and concise answers

1. **Why can Parquet improve a selective query?** Its typed column chunks let the scan read only projected columns, and row-group statistics may skip groups that cannot satisfy a predicate.
2. **Why are equal hashes not the right cross-format assertion?** Hashes identify bytes; format encodings differ. Compare decoded typed rows, including duplicate counts, for logical equivalence.
3. **When can CSV be competitive?** Small full-row scans, warm caches, or parsing workloads where Parquet decode and setup costs offset reduced I/O.
4. **What is the purpose of row groups?** They are independently organized row partitions with column chunks and statistics, enabling bounded reads and possible pruning.
5. **Why use `EXCEPT ALL`?** It compares multisets, so it detects missing/extra duplicate rows as well as value differences.
6. **Why is DuckDB not a replacement for PostgreSQL here?** DuckDB is embedded and optimized for local analytics; PostgreSQL provides the application's shared transactional database and concurrency semantics.
7. **What does the pruning result prove?** For this sorted sample and filter, the plan scanned 5 of 50 groups; shuffled ordering scanned all 50. It does not guarantee pruning on another dataset/query.
8. **Why report first observations separately?** They may include different process/file-cache effects; a new process does not clear shared OS caches.

## Independent exercises

1. Add a column-selective query and confirm only required columns appear in the Parquet scan plan.
2. Build equivalent `RANK()` and `ROW_NUMBER()` reports with tied scores and explain row-count differences.
3. Change row-group size and sort key; predict candidate groups from min/max metadata, then compare with EXPLAIN ANALYZE.
4. Write tests for null/empty-field behavior and a malformed quoted CSV record.
5. Add streamed result consumption and compare peak memory with full result materialization.
6. Modify the benchmark to compare warm-up policies and show min/median/max without combining the corrected run with preliminary data.
7. Add a new codec only after checking package/engine support and measuring size, CPU and query trade-offs.

## Resume evidence

**Quantified, supported bullets:**

- Built an isolated DuckDB pipeline preserving all 110,578 MovieLens records across CSV and three Parquet codecs, with typed schemas, referential/quality checks and cross-format logical result validation.
- Measured seven analytical workloads over four storage formats with 168 fresh-process observations; on this Windows laptop, Zstandard reduced file size 77.59%, while uncompressed Parquet led median query time in five of seven workloads.
- Demonstrated layout-sensitive Parquet pruning: timestamp-sorted data scanned 5/50 row groups versus 50/50 for deterministic hash-shuffled data with identical filter results.

These bullets describe a local learning experiment and must not be represented as production-scale or production deployment achievements.
