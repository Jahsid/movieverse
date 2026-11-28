"""Bounded sorted-vs-shuffled Parquet row-group pruning demonstration."""

from __future__ import annotations

import argparse
import csv
import json
import re
import tempfile
from pathlib import Path
from typing import Any

import duckdb

from .conversion import DEFAULT_DATA_DIR, _sql_string


DEFAULT_THRESHOLD = 1_500_000_000
ROW_GROUP_SIZE = 2048


def _extract_scan_counts(plan: str) -> tuple[int, int]:
    match = re.search(r"Row Groups Scanned:\s*(\d+)\s*/\s*(\d+)", plan, re.IGNORECASE)
    if match is None:
        raise RuntimeError("EXPLAIN ANALYZE did not report Parquet row groups scanned")
    return int(match.group(1)), int(match.group(2))


def run_pruning_demo(
    data_dir: Path = DEFAULT_DATA_DIR,
    threshold: int = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Build two temporary multi-row-group files and inspect actual pruning."""
    if not isinstance(threshold, int) or isinstance(threshold, bool):
        raise ValueError("Timestamp threshold must be an integer epoch second")
    ratings_path = (data_dir / "ratings.csv").resolve()
    if not ratings_path.is_file():
        raise FileNotFoundError("ratings.csv was not found in the dataset directory")
    with ratings_path.open("r", encoding="utf-8-sig", newline="") as source:
        source_row_count = sum(1 for _ in csv.reader(source)) - 1

    with tempfile.TemporaryDirectory(prefix="movieverse-rowgroup-demo-") as temp_dir:
        root = Path(temp_dir)
        results: dict[str, Any] = {}
        with duckdb.connect(":memory:") as connection:
            connection.execute("SET threads = 1")
            for name, order_by in (
                ("timestamp_sorted", "timestamp, userId, movieId"),
                ("timestamp_shuffled_by_hash", "hash(userId, movieId), userId, movieId"),
            ):
                parquet_path = root / f"{name}.parquet"
                columns = "{'userId':'INTEGER','movieId':'INTEGER','rating':'DOUBLE','timestamp':'BIGINT'}"
                connection.execute(
                    f"COPY (SELECT userId, movieId, rating, timestamp "
                    f"FROM read_csv({_sql_string(ratings_path)}, header=true, auto_detect=false, columns={columns}) "
                    f"ORDER BY {order_by}) TO {_sql_string(parquet_path)} "
                    f"(FORMAT PARQUET, COMPRESSION zstd, ROW_GROUP_SIZE {ROW_GROUP_SIZE})"
                )
                query = (
                    f"SELECT COUNT(*) AS rating_count, SUM(rating) AS rating_sum "
                    f"FROM read_parquet({_sql_string(parquet_path)}) "
                    f"WHERE timestamp >= {threshold}"
                )
                plan = str(connection.execute(f"EXPLAIN ANALYZE {query}").fetchone()[1])
                scanned, total = _extract_scan_counts(plan)
                count, rating_sum = connection.execute(query).fetchone()
                metadata = connection.execute(
                    "SELECT row_group_id, stats_min_value, stats_max_value "
                    "FROM parquet_metadata(?) WHERE path_in_schema='timestamp' "
                    "ORDER BY row_group_id",
                    [str(parquet_path)],
                ).fetchall()
                candidate_groups = sum(
                    maximum is None or int(maximum) >= threshold
                    for _, _, maximum in metadata
                )
                results[name] = {
                    "file_bytes": parquet_path.stat().st_size,
                    "row_group_size_target": ROW_GROUP_SIZE,
                    "row_group_count": len({row[0] for row in metadata}),
                    "row_groups_with_min_max_statistics": sum(
                        minimum is not None and maximum is not None
                        for _, minimum, maximum in metadata
                    ),
                    "metadata_candidate_groups_for_filter": candidate_groups,
                    "row_groups_scanned_from_explain_analyze": scanned,
                    "row_groups_reported_by_plan": total,
                    "filtered_rating_count": int(count),
                    "filtered_rating_sum": float(rating_sum),
                    "explain_analyze": plan,
                }
                if scanned != candidate_groups or total != len({row[0] for row in metadata}):
                    raise RuntimeError("Plan row-group scan count disagrees with Parquet statistics")

        sorted_result = results["timestamp_sorted"]
        shuffled_result = results["timestamp_shuffled_by_hash"]
        if (
            sorted_result["filtered_rating_count"], sorted_result["filtered_rating_sum"]
        ) != (
            shuffled_result["filtered_rating_count"], shuffled_result["filtered_rating_sum"]
        ):
            raise RuntimeError("Sorted and shuffled Parquet files returned different analytical results")
    return {
        "duckdb_version": duckdb.__version__,
        "source_row_count": source_row_count,
        "timestamp_filter_gte": threshold,
        "thread_count": 1,
        "formats": results,
        "result_equivalence": "passed",
        "temporary_cleanup_verified": not root.exists(),
        "measurement_scope": "plan and row-group pruning demonstration only; not included in the primary format benchmark",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    args = parser.parse_args()
    try:
        report = run_pruning_demo(args.data_dir, args.threshold)
    except (OSError, ValueError, duckdb.Error, RuntimeError) as error:
        parser.exit(2, f"Pruning demonstration failed: {error}\n")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
