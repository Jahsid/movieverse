"""Fresh-process DuckDB format and query benchmark for the MovieLens lab."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from .analytics import FORMATS
from .conversion import (
    COMPRESSION_OPTIONS,
    DEFAULT_DATA_DIR,
    EXPERIMENT_ROOT,
    REPOSITORY_ROOT,
    convert_dataset,
)

try:
    import resource
except ImportError:  # Windows uses GetProcessMemoryInfo below.
    resource = None


WORKLOADS = (
    "full_row_scan",
    "single_column_scan",
    "selective_rating_filter",
    "aggregation",
    "movie_rating_join",
    "genre_analytics",
    "window_ranking",
)
DEFAULT_REPETITIONS = 5
DEFAULT_TIMEOUT_SECONDS = 180
HASH_MODULUS = 1 << 256
REDACTIONS = (
    (re.compile(r"(?i)(?:postgres(?:ql)?(?:\+[a-z0-9_]+)?://)[^\s'\"]+"), "[REDACTED_DATABASE_URL]"),
    (re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)\s*[=:]\s*[^\s,;]+"), r"\1=[REDACTED]"),
)


class ChildProcessError(RuntimeError):
    """A sanitized failure raised for a benchmark worker process."""


@dataclass(frozen=True)
class BenchmarkConfig:
    formats: tuple[str, ...] = FORMATS
    workloads: tuple[str, ...] = WORKLOADS
    repetitions: int = DEFAULT_REPETITIONS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self):
        if not self.formats or len(set(self.formats)) != len(self.formats):
            raise ValueError("Select one or more unique source formats")
        if set(self.formats) - set(FORMATS):
            raise ValueError(f"Unsupported source formats: {sorted(set(self.formats) - set(FORMATS))}")
        if not self.workloads or len(set(self.workloads)) != len(self.workloads):
            raise ValueError("Select one or more unique query workloads")
        if set(self.workloads) - set(WORKLOADS):
            raise ValueError(f"Unsupported query workloads: {sorted(set(self.workloads) - set(WORKLOADS))}")
        if not isinstance(self.repetitions, int) or isinstance(self.repetitions, bool) or self.repetitions < 0:
            raise ValueError("Subsequent repetitions must be a non-negative integer")
        if not isinstance(self.timeout_seconds, int) or isinstance(self.timeout_seconds, bool) or self.timeout_seconds < 1:
            raise ValueError("Subprocess timeout must be a positive integer")


def _windows_peak_working_set_bytes() -> int:
    from ctypes import wintypes

    class ProcessMemoryCountersEx(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCountersEx()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCountersEx),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    process = kernel32.GetCurrentProcess()
    success = psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
    if not success:
        raise OSError(f"Windows process memory query failed (error {ctypes.get_last_error()})")
    return int(counters.PeakWorkingSetSize)


def peak_working_set_mib() -> float:
    """Return this process's lifetime peak working set, including imports."""
    if os.name == "nt":
        peak_bytes = _windows_peak_working_set_bytes()
    else:
        if resource is None:
            raise OSError("Peak working-set measurement is unavailable on this platform")
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_bytes = int(peak if sys.platform == "darwin" else peak * 1024)
    return round(peak_bytes / (1024 * 1024), 3)


def _safe_text(value: str, limit: int = 1200) -> str:
    text = value or ""
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text[:limit]


def _child_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in list(environment):
        if key.upper() in {
            "DATABASE_URL",
            "MOVIEVERSE_TEST_DATABASE_URL",
            "MOVIEVERSE_RUN_POSTGRES_INTEGRATION",
        }:
            environment.pop(key, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def run_child(arguments: list[str], timeout_seconds: int) -> tuple[dict[str, Any], float]:
    """Run one fresh worker, parse its single JSON object and sanitize failures."""
    command = [
        sys.executable,
        "-m",
        "experiments.data_engineering.parquet_duckdb.benchmark",
        *arguments,
    ]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=_child_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError("Benchmark child exceeded the configured timeout") from error
    except OSError as error:
        raise ChildProcessError(f"Could not start benchmark child: {_safe_text(str(error))}") from error
    wall_seconds = time.perf_counter() - started
    if completed.returncode != 0:
        detail = _safe_text(completed.stderr.strip() or completed.stdout.strip())
        raise ChildProcessError(
            f"Benchmark child exited with code {completed.returncode}: {detail or 'no diagnostic output'}"
        )
    try:
        result = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError) as error:
        raise ChildProcessError("Benchmark child returned malformed JSON output") from error
    if not isinstance(result, dict):
        raise ChildProcessError("Benchmark child output must be one JSON object")
    return result, wall_seconds


def _normalize_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 12)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _row_hash(label: str, row: tuple[Any, ...]) -> int:
    payload = json.dumps(
        [label, *(_normalize_value(value) for value in row)],
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


def _consume_query(
    connection: duckdb.DuckDBPyConnection,
    label: str,
    sql: str,
    parameters: tuple[Any, ...] = (),
    *,
    build_signature: bool,
) -> tuple[int, int, int]:
    cursor = connection.execute(sql, parameters)
    row_count = 0
    digest_sum = 0
    digest_xor = 0
    while True:
        rows = cursor.fetchmany(8192)
        if not rows:
            break
        row_count += len(rows)
        if build_signature:
            for row in rows:
                row_hash = _row_hash(label, row)
                digest_sum = (digest_sum + row_hash) % HASH_MODULUS
                digest_xor ^= row_hash
    return row_count, digest_sum, digest_xor


WORKLOAD_SQL = {
    "full_row_scan": (
        ("movies", "SELECT movieId, title, genres FROM movies"),
        ("ratings", "SELECT userId, movieId, rating, timestamp FROM ratings"),
    ),
    "single_column_scan": (("ratings", "SELECT rating FROM ratings"),),
    "selective_rating_filter": ((
        "ratings",
        "SELECT userId, movieId, rating, timestamp FROM ratings "
        "WHERE rating >= 4.5 AND movieId BETWEEN 1 AND 5000",
    ),),
    "aggregation": ((
        "movie_aggregation",
        "SELECT movieId, COUNT(*) AS rating_count, AVG(rating) AS average_rating "
        "FROM ratings GROUP BY movieId",
    ),),
    "movie_rating_join": ((
        "joined_movie_aggregation",
        "SELECT m.movieId, m.title, COUNT(r.movieId) AS rating_count, AVG(r.rating) AS average_rating "
        "FROM movies m JOIN ratings r USING (movieId) GROUP BY m.movieId, m.title",
    ),),
    "genre_analytics": ((
        "genre_aggregation",
        "WITH movie_genres AS (SELECT movieId, trim(unnest(string_split(genres, '|'))) AS genre "
        "FROM movies WHERE genres IS NOT NULL AND trim(genres) <> '') "
        "SELECT g.genre, COUNT(DISTINCT g.movieId) AS movie_count, "
        "COUNT(r.movieId) AS rating_count, AVG(r.rating) AS average_rating "
        "FROM movie_genres g LEFT JOIN ratings r USING (movieId) GROUP BY g.genre",
    ),),
    "window_ranking": ((
        "genre_window",
        "WITH movie_genres AS (SELECT movieId, trim(unnest(string_split(genres, '|'))) AS genre "
        "FROM movies WHERE genres IS NOT NULL AND trim(genres) <> ''), movie_scores AS ("
        "SELECT g.genre, m.movieId, m.title, COUNT(r.movieId) AS rating_count, AVG(r.rating) AS average_rating "
        "FROM movie_genres g JOIN movies m USING (movieId) JOIN ratings r USING (movieId) "
        "GROUP BY g.genre, m.movieId, m.title HAVING COUNT(r.movieId) >= 50) "
        "SELECT *, ROW_NUMBER() OVER (PARTITION BY genre "
        "ORDER BY average_rating DESC, rating_count DESC, movieId ASC) AS genre_rank FROM movie_scores",
    ),),
}


def measure_workload(
    connection: duckdb.DuckDBPyConnection,
    workload: str,
) -> dict[str, Any]:
    """Execute and fully consume a query workload, timing the entire result path."""
    if workload not in WORKLOAD_SQL:
        raise ValueError(f"Unsupported workload: {workload}")
    started = time.perf_counter()
    row_count = 0
    for label, sql in WORKLOAD_SQL[workload]:
        count, _, _ = _consume_query(connection, label, sql, build_signature=False)
        row_count += count
    duration_seconds = time.perf_counter() - started

    validation_start = time.perf_counter()
    verified_count = 0
    digest_sum = 0
    digest_xor = 0
    for label, sql in WORKLOAD_SQL[workload]:
        count, row_sum, row_xor = _consume_query(connection, label, sql, build_signature=True)
        verified_count += count
        digest_sum = (digest_sum + row_sum) % HASH_MODULUS
        digest_xor ^= row_xor
    validation_seconds = time.perf_counter() - validation_start
    if verified_count != row_count:
        raise RuntimeError("Benchmark query returned a different row count during correctness validation")
    rows_per_second = row_count / duration_seconds if duration_seconds else None
    return {
        "duration_seconds": duration_seconds,
        "correctness_validation_seconds": validation_seconds,
        "result_rows_consumed": row_count,
        "result_rows_per_second": rows_per_second,
        "result_signature": f"{row_count}:{digest_sum:064x}:{digest_xor:064x}",
    }


def _worker(args: argparse.Namespace) -> dict[str, Any]:
    if args.child_conversion:
        if args.compression not in COMPRESSION_OPTIONS:
            raise ValueError("A valid compression must be selected for conversion worker")
        report = convert_dataset(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            compressions=(args.compression,),
        )
        compression_report = report["compressions"][args.compression]
        return {
            "kind": "conversion",
            "format": args.compression,
            "duckdb_version": duckdb.__version__,
            "source_validation_seconds": report["source_validation_seconds"],
            "parquet_write_seconds": compression_report["parquet_write_seconds"],
            "round_trip_validation_seconds": compression_report["round_trip_validation_seconds"],
            "files": compression_report["files"],
            "raw_hashes_unchanged": report["raw_hashes_unchanged"],
            "peak_working_set_mib": peak_working_set_mib(),
            "measurement_scope": "fresh conversion child process; peak includes imports, source validation, conversion and result checks",
        }
    if args.child_query:
        if args.source_format not in FORMATS or args.workload not in WORKLOADS:
            raise ValueError("Query worker requires a valid format and workload")
        from .analytics import create_source_views

        with duckdb.connect(":memory:") as connection:
            connection.execute("SET threads = 1")
            create_source_views(
                connection,
                Path(args.data_dir),
                args.source_format,
                Path(args.parquet_dir) if args.source_format != "csv" else None,
            )
            measured = measure_workload(connection, args.workload)
        return {
            "kind": "query",
            "format": args.source_format,
            "workload": args.workload,
            "duckdb_version": duckdb.__version__,
            **measured,
            "peak_working_set_mib": peak_working_set_mib(),
            "measurement_scope": "fresh query child process; duration includes SQL execution and full result fetching; excludes imports, view setup and correctness re-execution; peak includes imports, connection/view setup, query and validation",
        }
    raise ValueError("No child operation was selected")


def _child_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--child-conversion", action="store_true")
    parser.add_argument("--child-query", action="store_true")
    parser.add_argument("--compression")
    parser.add_argument("--source-format")
    parser.add_argument("--workload")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--parquet-dir", type=Path)
    return parser


def _child_main(argv: list[str]) -> int:
    parser = _child_parser()
    args = parser.parse_args(argv)
    try:
        result = _worker(args)
        print(json.dumps(result, separators=(",", ":"), allow_nan=False))
        return 0
    except Exception as error:
        print(json.dumps({
            "error_type": type(error).__name__,
            "error": _safe_text(str(error)),
        }, separators=(",", ":")))
        return 2


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_jsonl(path: Path, record: dict[str, Any], stream) -> None:
    line = json.dumps(record, separators=(",", ":"), allow_nan=False)
    stream.write(line + "\n")
    stream.flush()


def _rotate(values: tuple[str, ...], offset: int) -> tuple[str, ...]:
    if not values:
        return values
    position = offset % len(values)
    return values[position:] + values[:position]


def _sample_record(
    result: dict[str, Any],
    wall_seconds: float,
    source_format: str,
    workload: str,
    run_kind: str,
    repetition: int,
    order_index: int,
) -> dict[str, Any]:
    return {
        "record_type": "query_sample",
        "format": source_format,
        "workload": workload,
        "run_kind": run_kind,
        "repetition": repetition,
        "format_order_index": order_index,
        "duration_seconds": result["duration_seconds"],
        "correctness_validation_seconds": result["correctness_validation_seconds"],
        "result_rows_consumed": result["result_rows_consumed"],
        "result_rows_per_second": result["result_rows_per_second"],
        "result_signature": result["result_signature"],
        "peak_working_set_mib": result["peak_working_set_mib"],
        "child_wall_seconds": wall_seconds,
        "measurement_scope": result["measurement_scope"],
    }


def summarize_samples(records: list[dict[str, Any]], metric: str) -> dict[str, float]:
    values = [float(record[metric]) for record in records]
    if not values:
        raise ValueError(f"No values available for metric: {metric}")
    return {
        "minimum": min(values),
        "median": statistics.median(values),
        "maximum": max(values),
    }


def run_benchmark(
    config: BenchmarkConfig,
    data_dir: Path,
    output_path: Path,
    *,
    smoke_mode: bool = False,
) -> dict[str, Any]:
    """Run conversion and all selected fresh-process query samples sequentially."""
    data_dir = data_dir.resolve()
    output_path = output_path.resolve()
    if output_path.exists():
        raise FileExistsError("Refusing to overwrite an existing JSONL benchmark result")
    if not data_dir.is_dir():
        raise FileNotFoundError("Benchmark dataset directory does not exist")
    source_paths = {name: data_dir / filename for name, filename in (
        ("movies", "movies.csv"), ("ratings", "ratings.csv")
    )}
    initial_hashes = {name: _sha256(path) for name, path in source_paths.items()}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.touch(exist_ok=False)
    all_records: list[dict[str, Any]] = []
    conversion_records: dict[str, dict[str, Any]] = {}
    samples: list[dict[str, Any]] = []
    references: dict[str, str] = {}

    def append(record: dict[str, Any], stream) -> None:
        _append_jsonl(output_path, record, stream)
        all_records.append(record)

    work_dir_path: Path
    with tempfile.TemporaryDirectory(prefix="movieverse-stage2a5-") as work_dir:
        work_dir_path = Path(work_dir)
        temp_root = Path(work_dir)
        parquet_dir = temp_root / "parquet"
        parquet_dir.mkdir()
        with output_path.open("a", encoding="utf-8", newline="") as stream:
            for source_format in config.formats:
                if source_format == "csv":
                    continue
                conversion_dir = parquet_dir / source_format
                arguments = [
                    "--child-conversion",
                    "--compression", source_format,
                    "--data-dir", str(data_dir),
                    "--output-dir", str(conversion_dir),
                ]
                result, child_wall_seconds = run_child(arguments, config.timeout_seconds)
                conversion_record = {
                    "record_type": "conversion",
                    **result,
                    "child_wall_seconds": child_wall_seconds,
                }
                conversion_records[source_format] = conversion_record
                append(conversion_record, stream)

            for workload_index, workload in enumerate(config.workloads):
                workload_signatures: dict[str, str] = {}
                first_order = _rotate(config.formats, workload_index)
                for source_format in first_order:
                    result, child_wall_seconds = run_child([
                        "--child-query",
                        "--source-format", source_format,
                        "--workload", workload,
                        "--data-dir", str(data_dir),
                        "--parquet-dir", str(parquet_dir / source_format),
                    ], config.timeout_seconds)
                    order_index = first_order.index(source_format)
                    record = _sample_record(
                        result, child_wall_seconds, source_format, workload,
                        "first_observation", 0, order_index,
                    )
                    append(record, stream)
                    samples.append(record)
                    workload_signatures[source_format] = result["result_signature"]
                    if source_format != first_order[0] and result["result_signature"] != workload_signatures[first_order[0]]:
                        raise ValueError(f"Query result mismatch for workload {workload} across formats")

                for repetition in range(1, config.repetitions + 1):
                    order = _rotate(config.formats, workload_index + repetition)
                    for source_format in order:
                        result, child_wall_seconds = run_child([
                            "--child-query",
                            "--source-format", source_format,
                            "--workload", workload,
                            "--data-dir", str(data_dir),
                            "--parquet-dir", str(parquet_dir / source_format),
                        ], config.timeout_seconds)
                        order_index = order.index(source_format)
                        record = _sample_record(
                            result, child_wall_seconds, source_format, workload,
                            "measured_repetition", repetition, order_index,
                        )
                        append(record, stream)
                        samples.append(record)
                        if result["result_signature"] != workload_signatures[source_format]:
                            raise ValueError(
                                f"Non-repeatable result signature for {source_format}/{workload}"
                            )

    final_hashes = {name: _sha256(path) for name, path in source_paths.items()}
    if final_hashes != initial_hashes:
        raise RuntimeError("Raw dataset hashes changed during benchmark execution")

    query_summaries: dict[str, Any] = {}
    for workload in config.workloads:
        query_summaries[workload] = {}
        for source_format in config.formats:
            group = [
                record for record in samples
                if record["workload"] == workload
                and record["format"] == source_format
                and record["run_kind"] == "measured_repetition"
            ]
            if group:
                first = next(
                    record for record in samples
                    if record["workload"] == workload
                    and record["format"] == source_format
                    and record["run_kind"] == "first_observation"
                )
                query_summaries[workload][source_format] = {
                    "first_observation": {
                        "duration_seconds": first["duration_seconds"],
                        "result_rows_per_second": first["result_rows_per_second"],
                        "peak_working_set_mib": first["peak_working_set_mib"],
                    },
                    "duration_seconds": summarize_samples(group, "duration_seconds"),
                    "result_rows_per_second": summarize_samples(group, "result_rows_per_second"),
                    "peak_working_set_mib": summarize_samples(group, "peak_working_set_mib"),
                    "repetitions": len(group),
                }
            else:
                first = next(
                    record for record in samples
                    if record["workload"] == workload and record["format"] == source_format
                )
                query_summaries[workload][source_format] = {
                    "first_observation_duration_seconds": first["duration_seconds"],
                    "first_observation_peak_working_set_mib": first["peak_working_set_mib"],
                    "repetitions": 0,
                }

    source_total_bytes = sum(path.stat().st_size for path in source_paths.values())
    conversion_summary = {}
    for source_format, record in conversion_records.items():
        files = record["files"]
        total_bytes = sum(item["size_bytes"] for item in files.values())
        conversion_summary[source_format] = {
            "total_parquet_bytes": total_bytes,
            "source_total_bytes": source_total_bytes,
            "csv_to_parquet_ratio": source_total_bytes / total_bytes,
            "csv_bytes_saved_percent": 100 * (1 - total_bytes / source_total_bytes),
            "source_validation_seconds": record["source_validation_seconds"],
            "conversion_child_wall_seconds": record["child_wall_seconds"],
            "parquet_write_seconds": record["parquet_write_seconds"],
            "round_trip_validation_seconds": record["round_trip_validation_seconds"],
            "peak_working_set_mib": record["peak_working_set_mib"],
            "files": files,
        }
    summary = {
        "record_type": "summary",
        "mode": "smoke" if smoke_mode else "full",
        "python_version": platform.python_version(),
        "duckdb_version": duckdb.__version__,
        "platform": platform.platform(),
        "cpu": "Intel Core i3-1115G4",
        "physical_memory_gib": 8,
        "thread_count": 1,
        "formats": list(config.formats),
        "workloads": list(config.workloads),
        "subsequent_repetitions": config.repetitions,
        "raw_hashes_unchanged": True,
        "raw_sha256": final_hashes,
        "conversion": conversion_summary,
        "queries": query_summaries,
        "partial_results_preserved": True,
        "measurement_scope": {
            "conversion": "child-process phase durations isolate source validation, Parquet writes and round-trip checks; peak is process high-water mark including imports",
            "query": "perf_counter spans SQL execution and full result fetching; correctness re-execution and signature hashing are timed separately; peak is a fresh child high-water mark including imports, query and validation",
            "first_observation": "recorded separately and not guaranteed to represent a cold filesystem cache",
            "result_signature": "streaming order-independent digest; floating values rounded to 12 decimal places",
        },
        "temporary_work_directory_cleanup_verified": not work_dir_path.exists(),
        "storage": {
            "csv": {
                "total_bytes": source_total_bytes,
                "files": {name: path.stat().st_size for name, path in source_paths.items()},
            },
            **{
                source_format: {
                    "total_bytes": values["total_parquet_bytes"],
                    "csv_to_parquet_ratio": values["csv_to_parquet_ratio"],
                    "csv_bytes_saved_percent": values["csv_bytes_saved_percent"],
                }
                for source_format, values in conversion_summary.items()
            },
        },
    }
    with output_path.open("a", encoding="utf-8", newline="") as stream:
        append(summary, stream)
    return summary


def _rotate_summary(summary: dict[str, Any]) -> dict[str, dict[str, str]]:
    fastest: dict[str, dict[str, str]] = {}
    for workload, formats in summary["queries"].items():
        measured = {
            source_format: metrics["duration_seconds"]["median"]
            for source_format, metrics in formats.items()
            if "duration_seconds" in metrics
        }
        if measured:
            fastest[workload] = {
                "format": min(measured, key=measured.get),
                "median_seconds": f"{min(measured.values()):.9f}",
            }
    return fastest


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"--child-conversion", "--child-query"}:
        return _child_main(argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--smoke", action="store_true", help="Run a full-data one-workload harness smoke check")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS,
                        help="Subsequent measured runs per workload and format (default: 5)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)
    if args.smoke:
        config = BenchmarkConfig(
            formats=FORMATS,
            workloads=("full_row_scan",),
            repetitions=0,
            timeout_seconds=args.timeout,
        )
        default_output = EXPERIMENT_ROOT / "output" / "stage2a5_smoke.jsonl"
    else:
        config = BenchmarkConfig(repetitions=args.repetitions, timeout_seconds=args.timeout)
        default_output = EXPERIMENT_ROOT / "output" / "stage2a5_results.jsonl"
    output = (args.output or default_output).resolve()
    try:
        output.relative_to((EXPERIMENT_ROOT / "output").resolve())
    except ValueError:
        parser.error("--output must be inside experiments/data_engineering/parquet_duckdb/output/")
    try:
        summary = run_benchmark(config, args.data_dir, output, smoke_mode=args.smoke)
    except (OSError, ValueError, TimeoutError, ChildProcessError, duckdb.Error) as error:
        parser.exit(2, f"Benchmark failed; completed JSONL records are preserved: {_safe_text(str(error))}\n")
    print(json.dumps({
        "output": str(output),
        "mode": summary["mode"],
        "conversion_formats": list(summary["conversion"]),
        "workloads": list(summary["workloads"]),
        "subsequent_repetitions": summary["subsequent_repetitions"],
        "fastest_formats_by_median": _rotate_summary(summary),
        "raw_hashes_unchanged": summary["raw_hashes_unchanged"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
