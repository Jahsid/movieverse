# Parquet and DuckDB learning experiment

This isolated environment is for the Stage 2A Parquet/DuckDB experiment. It is
not used by MovieVerse application code. The original CSV files remain the
canonical inputs under `data/raw/`; generated experiment outputs belong in the
ignored `output/` directory or a temporary directory.

## Environment

Verified with Python 3.12.0 on Windows 11 x86-64 and DuckDB 2.0.0. DuckDB's
Python client supports Python 3.11 or newer and officially supports Windows
x86-64. Windows may require the Microsoft Visual C++ Redistributable. DuckDB
is MIT licensed. It is an in-process analytical database with native Parquet
read/write support, so this setup does not require PyArrow or pandas as direct
experiment dependencies.

Create and install the isolated environment from the repository root:

```powershell
py -3.12 -m venv experiments/data_engineering/parquet_duckdb/.venv
& experiments/data_engineering/parquet_duckdb/.venv/Scripts/python.exe -m pip install -r experiments/data_engineering/parquet_duckdb/requirements.txt
```

Check the installation:

```powershell
$python = "experiments/data_engineering/parquet_duckdb/.venv/Scripts/python.exe"
& $python -c "import duckdb; print(duckdb.__version__); print(duckdb.sql('select 40 + 2').fetchall())"
& $python -m pip check
```

## Stage 2A-2 verification record

- Installed only `duckdb==2.0.0` in this experiment environment. The environment's bundled pip is 23.2.1.
- Import and version check passed; an in-memory SQL query returned `42`.
- Wrote a two-row typed sample to temporary Zstandard-compressed Parquet, read it back, and verified exact values. The temporary directory was removed on context exit; the sample file was 482 bytes.
- `pip check`: no broken requirements found.
- The application environment (`.venv-watchlist`) remains on Python 3.12.0 and does not import DuckDB. Root `requirements.txt` and `constraints-tested-py312-win.txt` were not edited.
- The repository's `.venv` interpreter launcher points to an inaccessible Python 3.13 path in this session; verification used `.venv-watchlist` for the application environment and the new experiment environment for DuckDB.
- No MovieLens data was converted and no performance or memory benchmark was run.

## Stage 2A-3 conversion

Run fixture tests from the repository root:

```powershell
& experiments/data_engineering/parquet_duckdb/.venv/Scripts/python.exe -m unittest experiments.data_engineering.parquet_duckdb.test_conversion -v
```

Convert both complete source files using all three codecs. The default uses a
temporary directory, validates each output, reports its metrics as JSON, then
removes the generated Parquet files:

```powershell
& experiments/data_engineering/parquet_duckdb/.venv/Scripts/python.exe -m experiments.data_engineering.parquet_duckdb.conversion
```

To retain output for local inspection, choose a new or empty child directory
under the ignored experiment `output/` directory:

```powershell
& experiments/data_engineering/parquet_duckdb/.venv/Scripts/python.exe -m experiments.data_engineering.parquet_duckdb.conversion --output-dir experiments/data_engineering/parquet_duckdb/output/full-run
```

The converter reads CSV through DuckDB `read_csv` with an explicit `columns`
schema and `nullstr=''`, validates source constraints, then uses `COPY` to
write Parquet with `uncompressed`, `snappy`, or `zstd`. It sets DuckDB to one
thread. The report compares multisets in both directions with `EXCEPT ALL`,
so equality checks typed values and duplicate multiplicity independent of row
ordering. It checks schema, row counts, duplicate keys, valid ratings,
positive IDs, required fields and rating-to-movie references. Empty source
fields are read as NULL under the configured CSV null-string rule; an empty
`genres` value is permitted and preserved as NULL, while a missing required
rating/title value fails validation.

Parquet organizes values into row groups, each containing per-column chunks;
pages within chunks can be encoded/compressed, and file metadata records chunk
locations and types. This lets readers fetch selected columns without parsing
every field as text ([Parquet file format](https://parquet.apache.org/docs/file-format/),
[Parquet concepts](https://parquet.apache.org/docs/concepts/)). DuckDB documents
filter and projection pushdown for Parquet scans ([DuckDB Parquet docs](https://duckdb.org/docs/stable/data/parquet/overview)).
Explicit schemas prevent inference from silently changing
IDs, ratings or epoch-second timestamps. Snappy generally favors speed and
Zstandard generally favors stronger compression; this conversion run measures
size only, so it provides no comparative codec speed evidence. CSV SHA-256
hashes identify exact source bytes. They are not expected to match Parquet
hashes: logical equality is validated separately from physical file identity.

### Stage 2A-3 full-data conversion record

Environment: Windows 11, Python 3.12.0, DuckDB 2.0.0, one DuckDB thread.
Input files totaled 2,978,154 bytes (movies 494,431; ratings 2,483,723).
All 9,742 movie rows and 100,836 rating rows converted in each configuration;
all expected types matched, logical multiset equality passed, all ten quality
checks reported zero issues, and all unrated movie records were retained by
full-row equality (18 movies have no ratings). Null counts and empty string
counts in the actual raw data were zero. Source hashes before and after were
unchanged:

| Compression | Movies Parquet | Ratings Parquet | Combined Parquet | CSV / Parquet size ratio | CSV bytes saved |
|---|---:|---:|---:|---:|---:|
| Uncompressed | 375,869 B | 1,096,267 B | 1,472,136 B | 2.023x | 50.5% |
| Snappy | 249,617 B | 689,052 B | 938,669 B | 3.173x | 68.5% |
| Zstandard | 164,291 B | 503,226 B | 667,517 B | 4.462x | 77.6% |

The default temporary output was verified removed after reporting. This was a
conversion/size smoke test, not a query or throughput benchmark; it did not
measure conversion duration or memory. Compression ratios compare total raw
CSV bytes with total Parquet bytes and include Parquet metadata overhead.

Input SHA-256 values:

- `movies.csv`: `5a5f32dd9bb3797b8e728a1b98958789d2b13f294a69fdfbc5727f8a9611aa07`
- `ratings.csv`: `aa289ca83157595d0df6aea1be6a4ded676ddc4385472e8313a8ed9805352646`

### Learning prompts

- Why can a query selecting only `rating` read less Parquet data than CSV?
- Why is `EXCEPT ALL` a stronger round-trip check than comparing row counts?
- How do row groups and page statistics affect what a reader can skip?
- When might Snappy be a better choice than Zstandard despite larger files?
- Why do source-file fingerprints and logical dataset equality answer different questions?

Independent exercises: add a deliberately malformed quoted row and ensure the
conversion fails safely; measure query results for CSV and Parquet with the
same SQL; compare a projection-only query with a full-row scan; inspect Parquet
metadata and explain the observed row groups. Do not describe these exercises
as completed until measured.

## Stage 2A-4 analytical queries

Run the same ten workload groups over CSV, uncompressed Parquet, Snappy and
Zstandard. The command converts temporary Parquet copies, opens one in-memory
DuckDB connection per format, runs one thread, emits JSON, and removes all
temporary files:

```powershell
& experiments/data_engineering/parquet_duckdb/.venv/Scripts/python.exe -m experiments.data_engineering.parquet_duckdb.analytics --minimum-rating-count 50 --top-n 3 --rating-minimum 4.0 --movie-genre Drama
```

The `--movie-*` and `--rating-*` values are SQL-bound parameters. The default
minimum rating count is 50; the default per-genre top N is 3. Floating-point
aggregates are compared with relative and absolute tolerance `1e-12`. Result
ordering uses explicit tie-breaks so equivalent formats return the same rows.

| Query | Business question and SQL | Result semantics / execution | Industry use and interview prompt |
|---|---|---|---|
| Overview | How large and active is the catalogue? Scalar counts, distinct counts, min/max and average. | Includes rated and unrated movie counts; one summary row. | Data observability. Why distinguish catalogue rows from rated entities? |
| Rating distribution | How are ratings distributed? `GROUP BY rating`. | One row per observed half-star value, ascending. | Quality and product analytics. How would you detect distribution drift? |
| Most-rated movies | Which titles have the most feedback? Movie/rating join and aggregate. | Counts all rating rows; ties break by movie ID. | Popularity metrics. Why can popularity differ from quality? |
| Highest-rated movies | Which titles rate well with enough evidence? `HAVING COUNT(*) >= ?`. | Average rating, then count and movie ID order; minimum count is configurable. | Bayesian/ranking systems. Why use a support threshold or shrinkage? |
| Genre analytics | How do catalogue size and ratings vary by genre? Split the genre list, left join ratings and aggregate. | A multi-genre movie and each of its ratings count once in every assigned genre. Genre totals therefore overlap and can exceed global totals. | Dimensional analytics. How do bridge tables model many-to-many dimensions? |
| User activity | How active are users? Per-user aggregates plus summary averages, median and maximum. | Active users are users with at least one rating; median is over per-user rating counts. | Cohort/product metrics. What does a long-tailed activity distribution imply? |
| Yearly/monthly trends | When were ratings created? Convert epoch seconds to UTC, then bucket. | Uses UTC calendar boundaries; groups by year or `YYYY-MM`. | Event-time reporting. Why make timezone semantics explicit? |
| Unrated movies | Which catalogue titles have no feedback? `NOT EXISTS` anti-join. | Preserves movies even when the ratings table is empty. | Coverage analysis. When is an anti-join preferable to `NOT IN` with NULLs? |
| Selective filters | Which ratings or titles satisfy chosen criteria? Parameter-bound rating, user/movie, title-substring and genre predicates. | Filter values never become SQL fragments; deterministic ordering and bounded result size. | Interactive analytics. How do parameterized queries reduce injection risk? |
| Top N per genre | What are the best-supported titles in each genre? Aggregate then `ROW_NUMBER() OVER (PARTITION BY genre ...)`. | Threshold is applied before ranking; ties break by count and movie ID. Multi-genre movies can appear in multiple partitions. | Top-N reporting. When would `RANK` differ from `ROW_NUMBER`? |

DuckDB plans show the execution mechanics for these workloads. On this full
MovieLens dataset, the selective Parquet plan has a `READ_PARQUET` scan with
`Projections: movieId, rating` and the `rating >= 4.5` filter in the scan.
The CSV plan prunes to those columns but shows a separate Filter operator above
`READ_CSV`. Plans also showed Hash Join for movie/rating aggregation and a
Window operator for per-genre ranking. `EXPLAIN ANALYZE` output is retained in
the JSON report for inspection; these invocations establish correctness and
plan shape, not comparative performance.

`parquet_metadata` reported one row group per output file and min/max
statistics for all 3 movie and all 4 rating columns. The scan plan shows a
pushed predicate, but one row group and its statistics do not establish that
the reader skipped any row group. No row-group pruning claim is made. Files at
this scale are too small to infer large-table behavior.

### Stage 2A-4 full-data result

Actual CLI run with DuckDB 2.0.0 and one thread:

- All four formats produced equivalent results at `1e-12` floating-point tolerance.
- Full source counts were 9,742 movies, 100,836 ratings, 610 users and 97,424 distinct movie IDs with ratings; 18 movies were unrated.
- Overall average rating was `3.5015569836`. Average ratings per active user was `165.3049`; median was `70.5`, and the most active user had 2,698 ratings.
- Most-rated results began with Forrest Gump (329), The Shawshank Redemption (317), and Pulp Fiction (307).
- With a 50-rating threshold, the highest average began with The Shawshank Redemption (`4.4290`, 317 ratings), followed by The Godfather (`4.2891`, 192).
- The Action top result was Fight Club (`4.2729`, 218 ratings). Genre-level rating counts intentionally overlap because movies can belong to several genres.
- Source hashes remained unchanged and comparison temporary cleanup passed.

The JSON contains complete results and per-format `EXPLAIN`/`EXPLAIN ANALYZE`
plans. Analyze plans include operator timings as diagnostics, but no timing
summary is calculated and no speedup is claimed. Stage 2A-5 owns controlled
query benchmarking.

Independent exercises: vary the minimum count and explain ranking changes;
rewrite genre analytics using an explicit bridge table; compare `ROW_NUMBER`
with `RANK`; add a UTC date-range filter and inspect its plan; inspect row-group
statistics and test a larger partitioned dataset before discussing pruning.

## Stage 2A-5 performance benchmark

Run a bounded full-data harness smoke check first, then the complete sequential
matrix. Both commands write JSON Lines beneath the ignored `output/` directory;
the runner refuses to overwrite existing output. Choose a new filename to keep
prior or partial results:

```powershell
$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
& experiments/data_engineering/parquet_duckdb/.venv/Scripts/python.exe -m experiments.data_engineering.parquet_duckdb.benchmark --smoke --output "experiments/data_engineering/parquet_duckdb/output/stage2a5_smoke_$runId.jsonl"
& experiments/data_engineering/parquet_duckdb/.venv/Scripts/python.exe -m experiments.data_engineering.parquet_duckdb.benchmark --output "experiments/data_engineering/parquet_duckdb/output/stage2a5_results_$runId.jsonl"
```

Default full runs use one thread, all seven query workloads, four formats,
separate first observations, and five subsequent repetitions. Each sample and
each codec conversion runs in a fresh subprocess. The runner rotates format
order, appends and flushes each successful JSONL record, and preserves partial
results on failure. Query timing covers SQL execution and full result fetching;
the correctness replay and signature generation are separate. Conversion
source validation, CSV scan plus Parquet `COPY`, and round-trip checks have
separate timings. The timed `COPY` includes the lazy CSV read and Parquet
encoding/output, not only storage-device writes.
Peak working set includes the entire child process and its validation pass;
it is not phase-specific memory. First observations are not guaranteed cold
cache reads. No PostgreSQL is used.

For a separate sorted-versus-shuffled row-group pruning demonstration:

```powershell
& experiments/data_engineering/parquet_duckdb/.venv/Scripts/python.exe -m experiments.data_engineering.parquet_duckdb.row_group_pruning
```

This writes temporary 2,048-row-group Parquet files from ratings, inspects
`EXPLAIN ANALYZE`, then cleans them up. It does not alter `data/raw/` and is not
part of the primary timing matrix.

### Stage 2A-5 actual results

On the full 110,578-row dataset, Zstandard saved 77.59% of CSV bytes, Snappy
68.48%, and uncompressed Parquet 50.57%. Zstandard was smallest but did not
win all queries. Across five repeated runs, uncompressed Parquet had the
fastest median in five of seven workloads; Snappy led genre analytics and
Zstandard narrowly led the single-column scan. CSV was not fastest by median,
although the full-row scan differences among Parquet codecs were small and
their ranges overlap. The complete per-format median/min/max, first
observations, throughput, memory, conversion phases, pruning evidence and
limitations are in [the Stage 2A-5 analysis](../../../docs/benchmark_results/stage2a5_analysis.md)
and its [sanitized JSONL samples](../../../docs/benchmark_results/stage2a5_full_matrix.jsonl).

The experiment supports Parquet for repeated selective analytics and compact
storage in this local dataset. It does not show that smaller files are always
faster: decoding costs CPU, while CSV parsing and file-cache effects influence
small local scans. Snappy generally favors faster codec work; Zstandard
generally favors density, but codec speed was not isolated in this run. The
row-group demo showed 5/50 groups scanned for timestamp-sorted data and 50/50
for hash-shuffled data under the same filter. This result depends on statistics
and data ordering, not merely on using Parquet.

Interview prompts: Why can a columnar format help a projection but not a full
row scan as much? What does a row-group min/max statistic prove, and what does
the scan count prove? How do compression CPU cost and storage I/O interact?
Why is a fresh process not the same as a cold cache? How would you design a
representative benchmark at a larger scale?

Independent exercises: vary the row-group size and sorting key; plot repeated
query durations and explain outliers; repeat a full-row scan with an explicit
warm-up policy; compare memory when materializing results versus streaming;
test a higher-entropy dataset before generalizing compression ratios. Do not
promote Parquet into the serving application without separate quality,
latency, resource and rollback evidence.
