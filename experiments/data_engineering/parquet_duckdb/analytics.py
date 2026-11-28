"""Reusable MovieLens analytical queries over CSV or Parquet files."""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import duckdb

from .conversion import (
    COMPRESSION_OPTIONS,
    DATASETS,
    DEFAULT_DATA_DIR,
    _sql_string,
    convert_dataset,
)


FORMATS = ("csv", *COMPRESSION_OPTIONS)


def create_source_views(
    connection: duckdb.DuckDBPyConnection,
    data_dir: Path,
    source_format: str,
    parquet_dir: Path | None = None,
) -> dict[str, Path]:
    """Create identically named, explicitly typed movie/rating source views."""
    if source_format not in FORMATS:
        raise ValueError(f"Unsupported source format: {source_format}")
    if source_format != "csv" and parquet_dir is None:
        raise ValueError("A Parquet directory is required for Parquet formats")

    paths: dict[str, Path] = {}
    for dataset_name, spec in DATASETS.items():
        view_name = "movies" if dataset_name == "movies" else "ratings"
        if source_format == "csv":
            source_path = (data_dir / spec["file_name"]).resolve()
            if not source_path.is_file():
                raise FileNotFoundError(f"Required source CSV not found: {source_path.name}")
            columns = "{" + ", ".join(
                f"{_sql_string(name)}: {_sql_string(data_type)}"
                for name, data_type in spec["columns"].items()
            ) + "}"
            relation = (
                f"read_csv({_sql_string(source_path)}, header = true, auto_detect = false, "
                f"columns = {columns}, nullstr = '')"
            )
        else:
            source_path = (parquet_dir / f"{dataset_name}_{source_format}.parquet").resolve()
            if not source_path.is_file():
                raise FileNotFoundError(f"Required Parquet file not found: {source_path.name}")
            relation = f"read_parquet({_sql_string(source_path)})"
            paths[dataset_name] = source_path
        connection.execute(f"CREATE VIEW {view_name} AS SELECT * FROM {relation}")
    return paths


def _rows(connection: duckdb.DuckDBPyConnection, sql: str, parameters=()) -> list[list[Any]]:
    return [list(row) for row in connection.execute(sql, parameters).fetchall()]


def _one(connection: duckdb.DuckDBPyConnection, sql: str, parameters=()) -> dict[str, Any]:
    cursor = connection.execute(sql, parameters)
    names = [column[0] for column in cursor.description]
    return dict(zip(names, cursor.fetchone(), strict=True))


def run_analytics(
    connection: duckdb.DuckDBPyConnection,
    minimum_rating_count: int = 50,
    top_n: int = 3,
    result_limit: int = 10,
    rating_minimum: float | None = None,
    rating_maximum: float | None = None,
    rating_movie_id: int | None = None,
    rating_user_id: int | None = None,
    movie_title_contains: str | None = None,
    movie_genre: str | None = None,
) -> dict[str, Any]:
    """Run deterministic summary and detailed analytics with bound filters."""
    counts = (minimum_rating_count, top_n, result_limit)
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in counts):
        raise ValueError("Counts and limits must be positive integers")
    for name, value in (("Minimum", rating_minimum), ("Maximum", rating_maximum)):
        if value is not None and (
            not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.5 <= value <= 5.0
        ):
            raise ValueError(f"{name} rating must be finite and between 0.5 and 5.0")
    if rating_minimum is not None and rating_maximum is not None and rating_minimum > rating_maximum:
        raise ValueError("Minimum rating cannot exceed maximum rating")
    for name, value in (("Movie", rating_movie_id), ("User", rating_user_id)):
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 1
        ):
            raise ValueError(f"{name} filter ID must be a positive integer")
    for name, value in (("Title", movie_title_contains), ("Genre", movie_genre)):
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{name} filter must be a string")

    overview = _one(connection, """
        SELECT
            (SELECT COUNT(*) FROM movies) AS movie_count,
            (SELECT COUNT(DISTINCT movieId) FROM ratings) AS rated_movie_count,
            (SELECT COUNT(*) FROM movies m WHERE NOT EXISTS
                (SELECT 1 FROM ratings r WHERE r.movieId = m.movieId)) AS unrated_movie_count,
            (SELECT COUNT(*) FROM ratings) AS rating_count,
            (SELECT COUNT(DISTINCT userId) FROM ratings) AS user_count,
            (SELECT AVG(rating) FROM ratings) AS average_rating,
            (SELECT MIN(timestamp) FROM ratings) AS earliest_epoch_seconds,
            (SELECT MAX(timestamp) FROM ratings) AS latest_epoch_seconds
    """)

    rating_distribution = _rows(connection, """
        SELECT rating, COUNT(*) AS rating_count
        FROM ratings
        GROUP BY rating
        ORDER BY rating ASC
    """)

    most_rated_movies = _rows(connection, """
        SELECT m.movieId, m.title, COUNT(*) AS rating_count, AVG(r.rating) AS average_rating
        FROM ratings r JOIN movies m USING (movieId)
        GROUP BY m.movieId, m.title
        ORDER BY rating_count DESC, m.movieId ASC
        LIMIT ?
    """, [result_limit])

    highest_rated_movies = _rows(connection, """
        SELECT m.movieId, m.title, COUNT(*) AS rating_count, AVG(r.rating) AS average_rating
        FROM ratings r JOIN movies m USING (movieId)
        GROUP BY m.movieId, m.title
        HAVING COUNT(*) >= ?
        ORDER BY average_rating DESC, rating_count DESC, m.movieId ASC
        LIMIT ?
    """, [minimum_rating_count, result_limit])

    genre_analytics = _rows(connection, """
        WITH movie_genres AS (
            SELECT movieId, trim(unnest(string_split(genres, '|'))) AS genre
            FROM movies
            WHERE genres IS NOT NULL AND trim(genres) <> ''
        )
        SELECT g.genre,
               COUNT(DISTINCT g.movieId) AS movie_count,
               COUNT(r.movieId) AS rating_count,
               AVG(r.rating) AS average_rating
        FROM movie_genres g
        LEFT JOIN ratings r USING (movieId)
        GROUP BY g.genre
        ORDER BY g.genre ASC
    """)

    user_activity = _rows(connection, """
        SELECT userId, COUNT(*) AS rating_count, AVG(rating) AS average_rating,
               MIN(rating) AS minimum_rating, MAX(rating) AS maximum_rating
        FROM ratings
        GROUP BY userId
        ORDER BY rating_count DESC, userId ASC
        LIMIT ?
    """, [result_limit])
    user_activity_summary = _one(connection, """
        WITH activity AS (
            SELECT userId, COUNT(*) AS rating_count, AVG(rating) AS average_rating
            FROM ratings GROUP BY userId
        )
        SELECT COUNT(*) AS active_user_count,
               AVG(rating_count) AS average_ratings_per_user,
               median(rating_count) AS median_ratings_per_user,
               MAX(rating_count) AS maximum_ratings_by_one_user,
               AVG(average_rating) AS average_of_user_average_ratings
        FROM activity
    """)

    yearly_trend = _rows(connection, """
        SELECT strftime(timezone('UTC', to_timestamp(timestamp)), '%Y') AS calendar_year,
               COUNT(*) AS rating_count, AVG(rating) AS average_rating
        FROM ratings
        GROUP BY calendar_year
        ORDER BY calendar_year ASC
    """)
    monthly_trend = _rows(connection, """
        SELECT strftime(timezone('UTC', to_timestamp(timestamp)), '%Y-%m') AS calendar_month,
               COUNT(*) AS rating_count, AVG(rating) AS average_rating
        FROM ratings
        GROUP BY calendar_month
        ORDER BY calendar_month ASC
    """)

    unrated_movies = _rows(connection, """
        SELECT m.movieId, m.title, m.genres
        FROM movies m
        WHERE NOT EXISTS (SELECT 1 FROM ratings r WHERE r.movieId = m.movieId)
        ORDER BY m.movieId ASC
        LIMIT ?
    """, [result_limit])

    rating_filters = _rows(connection, """
        SELECT userId, movieId, rating, timestamp
        FROM ratings
        WHERE (? IS NULL OR rating >= ?)
          AND (? IS NULL OR rating <= ?)
          AND (? IS NULL OR movieId = ?)
          AND (? IS NULL OR userId = ?)
        ORDER BY timestamp ASC, userId ASC, movieId ASC
        LIMIT ?
    """, [rating_minimum, rating_minimum, rating_maximum, rating_maximum,
          rating_movie_id, rating_movie_id, rating_user_id, rating_user_id,
          result_limit])

    movie_filters = _rows(connection, """
        SELECT movieId, title, genres
        FROM movies
        WHERE (? IS NULL OR contains(lower(title), lower(?)))
          AND (? IS NULL OR list_contains(string_split(genres, '|'), ?))
        ORDER BY movieId ASC
        LIMIT ?
    """, [movie_title_contains, movie_title_contains,
          movie_genre, movie_genre, result_limit])

    top_movies_per_genre = _rows(connection, """
        WITH movie_genres AS (
            SELECT movieId, trim(unnest(string_split(genres, '|'))) AS genre
            FROM movies
            WHERE genres IS NOT NULL AND trim(genres) <> ''
        ), movie_scores AS (
            SELECT g.genre, m.movieId, m.title, COUNT(r.movieId) AS rating_count,
                   AVG(r.rating) AS average_rating
            FROM movie_genres g
            JOIN movies m USING (movieId)
            JOIN ratings r USING (movieId)
            GROUP BY g.genre, m.movieId, m.title
            HAVING COUNT(r.movieId) >= ?
        ), ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY genre
                ORDER BY average_rating DESC, rating_count DESC, movieId ASC
            ) AS genre_rank
            FROM movie_scores
        )
        SELECT genre, genre_rank, movieId, title, rating_count, average_rating
        FROM ranked
        WHERE genre_rank <= ?
        ORDER BY genre ASC, genre_rank ASC
    """, [minimum_rating_count, top_n])

    return {
        "overview": overview,
        "rating_distribution": rating_distribution,
        "most_rated_movies": most_rated_movies,
        "highest_rated_movies": highest_rated_movies,
        "genre_analytics": genre_analytics,
        "user_activity": user_activity,
        "user_activity_summary": user_activity_summary,
        "yearly_trend": yearly_trend,
        "monthly_trend": monthly_trend,
        "unrated_movies": unrated_movies,
        "rating_filters": rating_filters,
        "movie_filters": movie_filters,
        "top_movies_per_genre": top_movies_per_genre,
        "parameters": {
            "minimum_rating_count": minimum_rating_count,
            "top_n": top_n,
            "result_limit": result_limit,
            "rating_minimum": rating_minimum,
            "rating_maximum": rating_maximum,
            "rating_movie_id": rating_movie_id,
            "rating_user_id": rating_user_id,
            "movie_title_contains": movie_title_contains,
            "movie_genre": movie_genre,
        },
    }


def _plan_text(connection: duckdb.DuckDBPyConnection, statement: str) -> str:
    rows = connection.execute(statement).fetchall()
    if not rows:
        return ""
    return "\n".join(str(value) for row in rows for value in row if value is not None)


def inspect_query_plans(
    connection: duckdb.DuckDBPyConnection,
    parquet_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Return real plans for a pushed filter/projection, join and window query."""
    statements = {
        "projection_and_predicate": """
            SELECT movieId, rating FROM ratings WHERE rating >= 4.5
            ORDER BY movieId, rating LIMIT 20
        """,
        "join_and_aggregation": """
            SELECT m.movieId, m.title, COUNT(r.movieId) AS rating_count
            FROM movies m JOIN ratings r USING (movieId)
            GROUP BY m.movieId, m.title ORDER BY rating_count DESC, m.movieId LIMIT 10
        """,
        "window_top_per_genre": """
            WITH genre_rows AS (
                SELECT movieId, trim(unnest(string_split(genres, '|'))) AS genre
                FROM movies WHERE genres IS NOT NULL AND trim(genres) <> ''
            ), scores AS (
                SELECT g.genre, m.movieId, m.title, AVG(r.rating) AS average_rating
                FROM genre_rows g JOIN movies m USING (movieId)
                JOIN ratings r USING (movieId)
                GROUP BY g.genre, m.movieId, m.title
            )
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY genre ORDER BY average_rating DESC, movieId
            ) AS genre_rank FROM scores
        """,
    }
    plans: dict[str, Any] = {}
    for name, query in statements.items():
        logical = _plan_text(connection, f"EXPLAIN {query}")
        analyzed = _plan_text(connection, f"EXPLAIN ANALYZE {query}")
        normalized = (logical + "\n" + analyzed).upper().replace("_", " ")
        plans[name] = {
            "explain": logical,
            "explain_analyze": analyzed,
            "observed_operators": {
                "scan_mentions_projection": "PROJECTIONS:" in normalized,
                "scan_mentions_filter": "FILTER" in normalized,
                "hash_join": "HASH JOIN" in normalized,
                "window": "WINDOW" in normalized,
            },
        }
    if parquet_paths:
        parquet_stats: dict[str, Any] = {}
        for dataset_name, path in parquet_paths.items():
            rows = connection.execute(
                "SELECT row_group_id, path_in_schema, stats_min, stats_max "
                "FROM parquet_metadata(?) ORDER BY row_group_id, path_in_schema",
                [str(path)],
            ).fetchall()
            parquet_stats[dataset_name] = {
                "metadata_rows": len(rows),
                "row_group_count": len({row[0] for row in rows}),
                "columns_with_min_max_statistics": sum(
                    row[2] is not None and row[3] is not None for row in rows
                ),
            }
        plans["parquet_row_group_statistics"] = parquet_stats
    return plans


def _equivalent(left: Any, right: Any, tolerance: float) -> bool:
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _equivalent(left[key], right[key], tolerance) for key in left
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _equivalent(a, b, tolerance) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) and not isinstance(right, bool):
        return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
    return left == right


def compare_all_formats(
    data_dir: Path = DEFAULT_DATA_DIR,
    minimum_rating_count: int = 50,
    top_n: int = 3,
    result_limit: int = 10,
    rating_minimum: float | None = None,
    rating_maximum: float | None = None,
    rating_movie_id: int | None = None,
    rating_user_id: int | None = None,
    movie_title_contains: str | None = None,
    movie_genre: str | None = None,
    tolerance: float = 1e-12,
) -> dict[str, Any]:
    """Run the same analytics and plans on CSV plus all codecs in temp storage."""
    if tolerance < 0:
        raise ValueError("Floating-point tolerance cannot be negative")
    with tempfile.TemporaryDirectory(prefix="movieverse-analytics-") as temporary_dir:
        parquet_dir = Path(temporary_dir) / "parquet"
        conversion_report = convert_dataset(data_dir=data_dir, output_dir=parquet_dir)
        format_results: dict[str, Any] = {}
        for source_format in FORMATS:
            with duckdb.connect(":memory:") as connection:
                connection.execute("SET threads = 1")
                parquet_paths = create_source_views(
                    connection, data_dir, source_format,
                    parquet_dir if source_format != "csv" else None,
                )
                result = run_analytics(
                    connection,
                    minimum_rating_count=minimum_rating_count,
                    top_n=top_n,
                    result_limit=result_limit,
                    rating_minimum=rating_minimum,
                    rating_maximum=rating_maximum,
                    rating_movie_id=rating_movie_id,
                    rating_user_id=rating_user_id,
                    movie_title_contains=movie_title_contains,
                    movie_genre=movie_genre,
                )
                result["query_plans"] = inspect_query_plans(connection, parquet_paths or None)
                format_results[source_format] = result
        reference = format_results["csv"]
        differences: dict[str, list[str]] = {}
        for source_format in FORMATS[1:]:
            unequal = [
                name for name in reference
                if name != "query_plans"
                and not _equivalent(reference[name], format_results[source_format][name], tolerance)
            ]
            if unequal:
                differences[source_format] = unequal
        if differences:
            raise ValueError(f"Analytical results differ between formats: {differences}")
        report = {
            "duckdb_version": duckdb.__version__,
            "thread_count": 1,
            "formats": format_results,
            "result_equivalence": "passed",
            "floating_point_tolerance": tolerance,
            "conversion_summary": {
                "rows": {
                    key: value["row_count"]
                    for key, value in conversion_report["source_files"].items()
                },
                "raw_hashes_unchanged": conversion_report["raw_hashes_unchanged"],
                "source_sha256": conversion_report["final_source_sha256"],
            },
            "measurement_scope": "correctness and query-plan inspection; not a performance benchmark",
        }
    report["temporary_cleanup_verified"] = not Path(temporary_dir).exists()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--minimum-rating-count", type=int, default=50)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--result-limit", type=int, default=10)
    parser.add_argument("--rating-minimum", type=float)
    parser.add_argument("--rating-maximum", type=float)
    parser.add_argument("--rating-movie-id", type=int)
    parser.add_argument("--rating-user-id", type=int)
    parser.add_argument("--movie-title-contains")
    parser.add_argument("--movie-genre")
    args = parser.parse_args()
    try:
        result = compare_all_formats(
            data_dir=args.data_dir,
            minimum_rating_count=args.minimum_rating_count,
            top_n=args.top_n,
            result_limit=args.result_limit,
            rating_minimum=args.rating_minimum,
            rating_maximum=args.rating_maximum,
            rating_movie_id=args.rating_movie_id,
            rating_user_id=args.rating_user_id,
            movie_title_contains=args.movie_title_contains,
            movie_genre=args.movie_genre,
        )
    except (OSError, ValueError, duckdb.Error) as error:
        parser.exit(2, f"Analytics failed: {error}\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
