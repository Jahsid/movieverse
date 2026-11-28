# Stage 2A-5 Parquet and DuckDB benchmark

## Environment and method

- Windows 11 (`Windows-11-10.0.26300-SP0`), Python 3.12.0, DuckDB 2.0.0.
- Intel Core i3-1115G4 laptop, 8 GiB RAM; one DuckDB thread.
- Full MovieLens data: 9,742 movies and 100,836 ratings (110,578 records); CSV inputs total 2,978,154 bytes.
- The full matrix contains seven query workloads × four formats. Each workload/format has one separately recorded first observation and five subsequent repetitions (168 query samples), plus three fresh-process Parquet conversions and one JSONL summary (172 JSONL records total).
- Format order rotates across workloads and repetitions. Runs are sequential. Every query sample uses a fresh Python process; conversion also runs in a fresh child per codec.
- `perf_counter` timing covers SQL execution and fetching the complete result. A second correctness execution and signature calculation are separately timed and excluded from query duration. Query output is consumed in batches of 8,192 rows. Signatures are order-independent and canonicalize float values to 12 decimals.
- Process working-set memory is the child’s Windows high-water mark. Query peak includes imports, connection and view setup, timed query, and correctness pass. Conversion peak includes imports, source validation, writing and round-trip checks. It is not phase-specific memory.
- First observations are reported separately; earlier file reads and OS caching mean they are not guaranteed cold-cache results. `EXPLAIN ANALYZE` and correctness re-execution are outside timed query intervals.
- Detailed sanitized samples: [stage2a5_full_matrix.jsonl](stage2a5_full_matrix.jsonl). It contains no credentials or local file paths. The machine-specific platform version, dataset fingerprints, durations and row-result signatures are retained as evidence.

## Storage and conversion

Compression ratios are total source CSV bytes divided by total Parquet bytes. The Parquet write interval covers the two DuckDB `COPY` operations. Source validation and round-trip checks are measured separately.

| Format | Movies bytes | Ratings bytes | Total bytes | CSV / Parquet | Space saved | Source validation s | CSV scan + Parquet `COPY` s | Round-trip validation s | Conversion child peak MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CSV | 494,431 | 2,483,723 | 2,978,154 | 1.000× | 0% | — | — | — | — |
| Parquet uncompressed | 375,869 | 1,096,267 | 1,472,136 | 2.023× | 50.57% | 0.124505 | 0.067796 | 0.231956 | 64.176 |
| Parquet Snappy | 249,617 | 689,052 | 938,669 | 3.173× | 68.48% | 0.121219 | 0.046099 | 0.224618 | 64.746 |
| Parquet Zstandard | 164,291 | 503,226 | 667,517 | 4.462× | 77.59% | 0.122693 | 0.050883 | 0.237606 | 65.414 |

There is one conversion child per codec, so these durations are single observations, not repeated conversion statistics. Source validation is repeated for each conversion child. The `COPY` interval includes DuckDB's lazy CSV scan, conversion/encoding and Parquet file output. Round-trip validation checks schema, counts and multiset values and is timed separately. Zstandard wins on this dataset’s size, but the test does not establish codec throughput.

## Query duration and process memory

Each cell reports the first observation, then the median of five later runs with minimum and maximum in parentheses. Throughput is **result rows consumed per second**. It equals source rows per second for full-row scan, but it is not scanned-source throughput for aggregation, join, genre or window queries. Peak is the repeated-run median with minimum and maximum child-process working set.

| Workload | Format | First s | Median s (min–max) | Median result rows/s | Peak MiB (median; min–max) |
|---|---|---:|---:|---:|---:|
| Full-row scan | CSV | 0.084886 | 0.073607 (0.071792–0.077175) | 1,502,280 | 56.785 (56.324–56.898) |
| Full-row scan | Uncompressed | 0.045018 | 0.049228 (0.048301–0.051785) | 2,246,251 | 53.406 (53.000–53.691) |
| Full-row scan | Snappy | 0.058264 | 0.050346 (0.045720–0.087911) | 2,196,379 | 53.062 (52.629–53.164) |
| Full-row scan | Zstandard | 0.049119 | 0.050258 (0.049282–0.089274) | 2,200,198 | 52.883 (52.809–53.691) |
| Single-column scan | CSV | 0.044731 | 0.033323 (0.031185–0.096217) | 3,025,982 | 52.160 (52.004–52.629) |
| Single-column scan | Uncompressed | 0.015501 | 0.016086 (0.014973–0.023134) | 6,268,479 | 47.031 (46.699–47.070) |
| Single-column scan | Snappy | 0.015447 | 0.015592 (0.014950–0.033608) | 6,467,121 | 47.023 (46.949–47.227) |
| Single-column scan | Zstandard | 0.018461 | 0.015588 (0.014909–0.019990) | 6,468,947 | 47.188 (47.008–47.527) |
| Selective rating filter | CSV | 0.037795 | 0.034641 (0.032348–0.035719) | 412,746 | 53.133 (52.965–53.273) |
| Selective rating filter | Uncompressed | 0.010440 | 0.010311 (0.009522–0.013487) | 1,386,621 | 50.176 (50.023–50.215) |
| Selective rating filter | Snappy | 0.011234 | 0.011673 (0.010198–0.016889) | 1,224,909 | 50.098 (49.961–50.590) |
| Selective rating filter | Zstandard | 0.014005 | 0.015111 (0.011308–0.021696) | 946,217 | 49.828 (49.637–50.051) |
| Aggregation | CSV | 0.028230 | 0.034108 (0.031737–0.038220) | 285,094 | 54.430 (54.164–54.703) |
| Aggregation | Uncompressed | 0.011097 | 0.012910 (0.011832–0.015674) | 753,197 | 49.973 (49.906–50.035) |
| Aggregation | Snappy | 0.011108 | 0.013410 (0.010411–0.014262) | 725,120 | 50.059 (49.875–50.371) |
| Aggregation | Zstandard | 0.014972 | 0.013979 (0.010985–0.015638) | 695,630 | 50.043 (49.910–50.195) |
| Movie-rating join | CSV | 0.047466 | 0.051436 (0.048294–0.051849) | 189,049 | 59.707 (59.625–60.324) |
| Movie-rating join | Uncompressed | 0.038431 | 0.025731 (0.024098–0.034672) | 377,907 | 57.762 (57.652–57.984) |
| Movie-rating join | Snappy | 0.036486 | 0.026564 (0.024128–0.043918) | 366,061 | 57.938 (57.766–58.105) |
| Movie-rating join | Zstandard | 0.028338 | 0.026032 (0.024686–0.035538) | 373,536 | 57.812 (57.699–58.016) |
| Genre analytics | CSV | 0.062675 | 0.067475 (0.060777–0.082998) | 296.4 | 59.570 (59.242–59.801) |
| Genre analytics | Uncompressed | 0.041376 | 0.042739 (0.039204–0.056733) | 468.0 | 54.930 (54.883–55.262) |
| Genre analytics | Snappy | 0.040378 | 0.040557 (0.039742–0.051069) | 493.1 | 54.969 (54.762–55.266) |
| Genre analytics | Zstandard | 0.040170 | 0.046082 (0.034563–0.050148) | 434.0 | 54.953 (54.840–55.199) |
| Window ranking | CSV | 0.149989 | 0.087455 (0.080110–0.216760) | 15,128 | 60.789 (60.090–61.004) |
| Window ranking | Uncompressed | 0.061554 | 0.055886 (0.053840–0.090999) | 23,673 | 55.938 (55.727–56.215) |
| Window ranking | Snappy | 0.054349 | 0.056091 (0.048761–0.078286) | 23,586 | 56.074 (55.914–56.266) |
| Window ranking | Zstandard | 0.054341 | 0.061361 (0.050024–0.079850) | 21,561 | 55.934 (55.852–56.195) |

The fastest format by median was uncompressed Parquet for full-row scan, selective filter, aggregation, movie-rating join and window ranking; Snappy for genre analytics; and Zstandard for the single-column scan, narrowly ahead of Snappy. CSV was not fastest in these five-run medians, but the full-row medians for the three Parquet codecs are close and ranges overlap. The genre throughput is low because it counts returned genre rows, not the 100,836 ratings scanned.

The separate correctness re-execution was excluded from query duration. Median validation durations across the four formats and five repetitions ranged from 0.037159s for genre analytics to 0.761089s for full-row scans; those reads are not part of query-time statistics. Maximum query-process working set was 61.004 MiB; conversion-child peaks ranged from 64.176 to 65.414 MiB. These high-water marks include imports and validation, so they are not isolated operator memory estimates.

## Pushdown and row-group pruning

On the primary files there was one row group per Parquet file. `EXPLAIN ANALYZE` for the selective Parquet query showed `Projections: movieId, rating` and `rating >= 4.5` inside `READ_PARQUET`; the CSV plan showed the projection in `READ_CSV` with a Filter operator above it. Plans also showed Hash Join, aggregation, and Window operators. One group cannot demonstrate row-group skipping.

A separate temporary experiment wrote the same 100,836 ratings to 50-row-group Zstandard Parquet files (2,048 target rows per group), once ordered by timestamp and once ordered by a deterministic hash. For the same filter `timestamp >= 1,500,000,000`, both returned 8,167 ratings with rating sum 28,047.5. `EXPLAIN ANALYZE` reported **5 / 50 row groups scanned** for timestamp-sorted data and **50 / 50** for hash-shuffled data; Parquet min/max statistics predicted the same candidate counts. Reported data read was 52.6 kB versus 506.0 kB. This demonstrates pruning for this sorted, multi-group example only; it is not part of the primary format timing table or a general performance claim.

## Interpretation and limits

Parquet's typed columns reduced storage substantially and improved most selected analytical workloads here, especially projection-heavy scans and filters. The full-row workload gains were smaller. Zstandard's much smaller files did not make it fastest for every workload: decompression CPU and data layout can offset I/O savings, while uncompressed Parquet can be competitive for CPU-heavy local scans. CSV remains simple and was within a similar range for full-row scan.

Cache state, process startup, Windows scheduling, filesystem caching, DuckDB vectorized execution and this small dataset all affect timings. Each child is fresh, but the OS page cache is shared. Conversion measurements are single observations. Five query repetitions provide a small local sample; large min/max spreads (notably window ranking and first observations) show variability. Results do not predict production or larger datasets. No application default, storage format or serving architecture is changed by this experiment.
