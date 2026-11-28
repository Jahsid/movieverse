"""Validated, isolated conversion of the MovieLens CSV files to Parquet."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path
from typing import Any

import duckdb


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = REPOSITORY_ROOT / "data" / "raw"
PERSISTENT_OUTPUT_ROOT = EXPERIMENT_ROOT / "output"
COMPRESSION_OPTIONS = ("uncompressed", "snappy", "zstd")
DATASETS = {
    "movies": {
        "file_name": "movies.csv",
        "columns": {"movieId": "INTEGER", "title": "VARCHAR", "genres": "VARCHAR"},
        "keys": ("movieId",),
    },
    "ratings": {
        "file_name": "ratings.csv",
        "columns": {
            "userId": "INTEGER",
            "movieId": "INTEGER",
            "rating": "DOUBLE",
            "timestamp": "BIGINT",
        },
        "keys": ("userId", "movieId"),
    },
}
PARQUET_TYPES = {
    "INTEGER": "INTEGER",
    "VARCHAR": "VARCHAR",
    "DOUBLE": "DOUBLE",
    "BIGINT": "BIGINT",
}


class DataIntegrityError(ValueError):
    """Raised when CSV rows do not satisfy the MovieLens source contract."""


def _sql_string(value: str | Path) -> str:
    """Quote a filesystem value as a SQL string literal."""
    return "'" + str(value).replace("'", "''") + "'"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_view_sql(path: Path, columns: dict[str, str]) -> str:
    column_config = "{" + ", ".join(
        f"{_sql_string(name)}: {_sql_string(data_type)}"
        for name, data_type in columns.items()
    ) + "}"
    return (
        f"read_csv({_sql_string(path)}, header = true, auto_detect = false, "
        f"columns = {column_config}, nullstr = '')"
    )


def _count(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    return int(connection.execute(query).fetchone()[0])


def _duplicate_rows_query(view_name: str, keys: tuple[str, ...]) -> str:
    key_list = ", ".join(keys)
    return (
        f"SELECT COALESCE(SUM(group_size), 0) FROM ("
        f"SELECT COUNT(*) AS group_size FROM {view_name} "
        f"GROUP BY {key_list} HAVING COUNT(*) > 1) duplicate_groups"
    )


def _validate_source(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    movie_issues = {
        "missing_movie_id": _count(connection, "SELECT COUNT(*) FROM source_movies WHERE movieId IS NULL"),
        "invalid_movie_id": _count(connection, "SELECT COUNT(*) FROM source_movies WHERE movieId <= 0"),
        "missing_title": _count(connection, "SELECT COUNT(*) FROM source_movies WHERE title IS NULL"),
        "invalid_title": _count(connection, "SELECT COUNT(*) FROM source_movies WHERE title IS NOT NULL AND trim(title) = ''"),
        "duplicate_movie_rows": _count(connection, _duplicate_rows_query("source_movies", ("movieId",))),
    }
    rating_issues = {
        "missing_rating_fields": _count(
            connection,
            "SELECT COUNT(*) FROM source_ratings "
            "WHERE userId IS NULL OR movieId IS NULL OR rating IS NULL OR timestamp IS NULL",
        ),
        "invalid_ids": _count(connection, "SELECT COUNT(*) FROM source_ratings WHERE userId <= 0 OR movieId <= 0"),
        "invalid_ratings": _count(
            connection,
            "SELECT COUNT(*) FROM source_ratings "
            "WHERE rating < 0.5 OR rating > 5.0 OR rating * 2 <> floor(rating * 2)",
        ),
        "duplicate_rating_rows": _count(
            connection, _duplicate_rows_query("source_ratings", ("userId", "movieId"))
        ),
        "invalid_movie_references": _count(
            connection,
            "SELECT COUNT(*) FROM source_ratings r "
            "WHERE NOT EXISTS (SELECT 1 FROM source_movies m WHERE m.movieId = r.movieId)",
        ),
    }
    issues = {**movie_issues, **rating_issues}
    failures = {name: count for name, count in issues.items() if count}
    if failures:
        details = ", ".join(f"{name}={count}" for name, count in failures.items())
        raise DataIntegrityError(f"MovieLens source validation failed: {details}")
    return issues


def _parquet_schema(
    connection: duckdb.DuckDBPyConnection,
    parquet_path: Path,
    expected: dict[str, str],
) -> list[dict[str, str]]:
    description = connection.execute(
        f"DESCRIBE SELECT * FROM read_parquet({_sql_string(parquet_path)})"
    ).fetchall()
    schema = [{"name": row[0], "type": row[1]} for row in description]
    expected_schema = [{"name": name, "type": PARQUET_TYPES[data_type]} for name, data_type in expected.items()]
    if schema != expected_schema:
        raise DataIntegrityError(f"Unexpected Parquet schema for {parquet_path.name}: {schema}")
    return schema


def _assert_multiset_equal(
    connection: duckdb.DuckDBPyConnection,
    source_view: str,
    parquet_path: Path,
    columns: dict[str, str],
) -> None:
    names = ", ".join(columns)
    parquet = f"read_parquet({_sql_string(parquet_path)})"
    left_only = _count(
        connection,
        f"SELECT COUNT(*) FROM (SELECT {names} FROM {source_view} "
        f"EXCEPT ALL SELECT {names} FROM {parquet}) differences",
    )
    right_only = _count(
        connection,
        f"SELECT COUNT(*) FROM (SELECT {names} FROM {parquet} "
        f"EXCEPT ALL SELECT {names} FROM {source_view}) differences",
    )
    if left_only or right_only:
        raise DataIntegrityError(
            f"Parquet values differ from CSV for {parquet_path.name}: "
            f"CSV-only={left_only}, Parquet-only={right_only}"
        )


def _prepare_output(output_dir: Path | None) -> tuple[Path, tempfile.TemporaryDirectory[str] | None, bool]:
    if output_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="movieverse-parquet-")
        return Path(temporary.name), temporary, True
    target = output_dir.resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError("Output directory must be new or empty")
    created = not target.exists()
    target.mkdir(parents=True, exist_ok=True)
    return target, None, created


def convert_dataset(
    data_dir: Path = DEFAULT_DATA_DIR,
    output_dir: Path | None = None,
    compressions: tuple[str, ...] = COMPRESSION_OPTIONS,
) -> dict[str, Any]:
    """Convert both source CSVs, validate every output, and report file evidence.

    An omitted output directory uses a temporary directory which is always
    removed. A caller-supplied directory must be empty and is retained on
    success. Files created by a failed invocation are removed.
    """
    if not compressions or len(compressions) != len(set(compressions)):
        raise ValueError("Choose one or more unique compression configurations")
    invalid_compressions = sorted(set(compressions) - set(COMPRESSION_OPTIONS))
    if invalid_compressions:
        raise ValueError(f"Unsupported Parquet compression: {invalid_compressions}")

    source_paths = {name: (data_dir / spec["file_name"]).resolve() for name, spec in DATASETS.items()}
    for source_path in source_paths.values():
        if not source_path.is_file():
            raise FileNotFoundError(f"Required source CSV not found: {source_path.name}")
    initial_hashes = {name: _sha256(path) for name, path in source_paths.items()}
    target, temporary, owns_directory = _prepare_output(output_dir)
    created_files: list[Path] = []
    report: dict[str, Any] = {
        "duckdb_version": duckdb.__version__,
        "source_files": {},
        "compressions": {},
        "output_temporary": temporary is not None,
        "output_cleanup_verified": False,
    }
    try:
        with duckdb.connect(":memory:") as connection:
            connection.execute("SET threads = 1")
            for dataset_name, spec in DATASETS.items():
                source_path = source_paths[dataset_name]
                view_name = f"source_{dataset_name}"
                source_sql = _source_view_sql(source_path, spec["columns"])
                connection.execute(f"CREATE VIEW {view_name} AS SELECT * FROM {source_sql}")
                row_count = _count(connection, f"SELECT COUNT(*) FROM {view_name}")
                if row_count == 0:
                    raise DataIntegrityError(f"Source CSV has no records: {spec['file_name']}")
                null_counts = {
                    column: _count(
                        connection,
                        f"SELECT COUNT(*) FROM {view_name} WHERE {column} IS NULL",
                    )
                    for column in spec["columns"]
                }
                empty_string_counts = {
                    column: _count(
                        connection,
                        f"SELECT COUNT(*) FROM {view_name} WHERE {column} = ''",
                    )
                    for column, data_type in spec["columns"].items()
                    if data_type == "VARCHAR"
                }
                report["source_files"][dataset_name] = {
                    "file_name": spec["file_name"],
                    "row_count": row_count,
                    "sha256": initial_hashes[dataset_name],
                    "source_bytes": source_path.stat().st_size,
                    "columns": list(spec["columns"].items()),
                    "null_counts": null_counts,
                    "empty_string_counts": empty_string_counts,
                }

            validation_start = time.perf_counter()
            report["quality_checks"] = _validate_source(connection)
            report["source_validation_seconds"] = time.perf_counter() - validation_start
            report["source_profile"] = {
                "unrated_movies": _count(
                    connection,
                    "SELECT COUNT(*) FROM source_movies m WHERE NOT EXISTS "
                    "(SELECT 1 FROM source_ratings r WHERE r.movieId = m.movieId)",
                )
            }
            for compression in compressions:
                compression_report = {
                    "files": {},
                    "total_parquet_bytes": 0,
                    "parquet_write_seconds": 0.0,
                    "round_trip_validation_seconds": 0.0,
                }
                for dataset_name, spec in DATASETS.items():
                    file_name = f"{dataset_name}_{compression}.parquet"
                    parquet_path = target / file_name
                    if parquet_path.exists():
                        raise FileExistsError(f"Refusing to overwrite generated output: {file_name}")
                    columns = ", ".join(spec["columns"])
                    write_start = time.perf_counter()
                    connection.execute(
                        f"COPY (SELECT {columns} FROM source_{dataset_name}) "
                        f"TO {_sql_string(parquet_path)} "
                        f"(FORMAT PARQUET, COMPRESSION {compression})"
                    )
                    write_seconds = time.perf_counter() - write_start
                    created_files.append(parquet_path)
                    validation_start = time.perf_counter()
                    schema = _parquet_schema(connection, parquet_path, spec["columns"])
                    _assert_multiset_equal(connection, f"source_{dataset_name}", parquet_path, spec["columns"])
                    parquet_rows = _count(connection, f"SELECT COUNT(*) FROM read_parquet({_sql_string(parquet_path)})")
                    if parquet_rows != report["source_files"][dataset_name]["row_count"]:
                        raise DataIntegrityError(f"Row count changed during conversion: {file_name}")
                    validation_seconds = time.perf_counter() - validation_start
                    size_bytes = parquet_path.stat().st_size
                    source_bytes = report["source_files"][dataset_name]["source_bytes"]
                    compression_report["files"][dataset_name] = {
                        "file_name": file_name,
                        "row_count": parquet_rows,
                        "size_bytes": size_bytes,
                        "compression_ratio": source_bytes / size_bytes,
                        "schema": schema,
                        "logical_values_equal": True,
                        "parquet_write_seconds": write_seconds,
                        "round_trip_validation_seconds": validation_seconds,
                    }
                    compression_report["total_parquet_bytes"] += size_bytes
                    compression_report["parquet_write_seconds"] += write_seconds
                    compression_report["round_trip_validation_seconds"] += validation_seconds
                source_total = sum(item["source_bytes"] for item in report["source_files"].values())
                compression_report["total_source_bytes"] = source_total
                compression_report["combined_compression_ratio"] = (
                    source_total / compression_report["total_parquet_bytes"]
                )
                report["compressions"][compression] = compression_report

        final_hashes = {name: _sha256(path) for name, path in source_paths.items()}
        report["raw_hashes_unchanged"] = final_hashes == initial_hashes
        report["final_source_sha256"] = final_hashes
        if not report["raw_hashes_unchanged"]:
            raise DataIntegrityError("A source CSV changed during conversion")
    except Exception:
        for path in created_files:
            path.unlink(missing_ok=True)
        if owns_directory and temporary is None:
            target.rmdir()
        raise
    finally:
        if temporary is not None:
            temporary.cleanup()
            report["output_cleanup_verified"] = not target.exists()
    if temporary is None:
        report["output_directory"] = str(target)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Retain outputs only inside this experiment's ignored output/ directory; temporary output is the default",
    )
    parser.add_argument("--compression", choices=COMPRESSION_OPTIONS, action="append")
    args = parser.parse_args()
    if args.output_dir is not None:
        target = args.output_dir.resolve()
        try:
            target.relative_to(PERSISTENT_OUTPUT_ROOT.resolve())
        except ValueError:
            parser.error("--output-dir must be under experiments/data_engineering/parquet_duckdb/output/")
    try:
        report = convert_dataset(
            data_dir=args.data_dir,
            output_dir=args.output_dir,
            compressions=tuple(args.compression or COMPRESSION_OPTIONS),
        )
    except (OSError, ValueError, duckdb.Error) as error:
        parser.exit(2, f"Conversion failed: {error}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
