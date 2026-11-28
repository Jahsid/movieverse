"""Standard-library tests for CSV/Parquet analytical result parity."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

try:
    import duckdb
except ImportError as error:
    raise unittest.SkipTest("DuckDB is installed only in the isolated experiment environment") from error

from .analytics import (
    compare_all_formats,
    create_source_views,
    inspect_query_plans,
    run_analytics,
)


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="movieverse-analytics-test-")
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "raw"
        self.data_dir.mkdir()
        self.write_movies([
            [1, "Alpha Film", "Action|Comedy"],
            [2, "Beta Film", "Comedy"],
            [3, "Unrated Drama", "Drama"],
            [4, "No Genre", ""],
        ])
        self.write_ratings([
            [10, 1, 5.0, 1577836800],
            [20, 1, 3.0, 1580515200],
            [10, 2, 4.0, 1612137600],
        ])

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, name, columns, rows):
        with (self.data_dir / name).open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(columns)
            writer.writerows(rows)

    def write_movies(self, rows):
        self._write("movies.csv", ["movieId", "title", "genres"], rows)

    def write_ratings(self, rows):
        self._write("ratings.csv", ["userId", "movieId", "rating", "timestamp"], rows)

    def query_csv(self, **kwargs):
        with duckdb.connect(":memory:") as connection:
            connection.execute("SET threads = 1")
            create_source_views(connection, self.data_dir, "csv")
            return run_analytics(connection, **kwargs)

    def test_overview_rating_distribution_and_most_rated_aggregation(self):
        result = self.query_csv(minimum_rating_count=1, result_limit=10)
        self.assertEqual(result["overview"]["movie_count"], 4)
        self.assertEqual(result["overview"]["rated_movie_count"], 2)
        self.assertEqual(result["overview"]["unrated_movie_count"], 2)
        self.assertEqual(result["overview"]["rating_count"], 3)
        self.assertEqual(result["overview"]["user_count"], 2)
        self.assertAlmostEqual(result["overview"]["average_rating"], 4.0)
        self.assertEqual(result["rating_distribution"], [[3.0, 1], [4.0, 1], [5.0, 1]])
        self.assertEqual([row[0] for row in result["most_rated_movies"]], [1, 2])

    def test_genre_aggregation_explains_multi_genre_overlap(self):
        result = self.query_csv(minimum_rating_count=1)
        genres = {row[0]: row for row in result["genre_analytics"]}
        self.assertEqual(genres["Action"][1:3], [1, 2])
        self.assertEqual(genres["Comedy"][1:3], [2, 3])
        self.assertEqual(genres["Drama"][1:3], [1, 0])
        # Alpha's two ratings count once under Action and again under Comedy.
        self.assertEqual(sum(row[2] for row in result["genre_analytics"]), 5)

    def test_rating_thresholds_and_parameterized_filters(self):
        one_rating_minimum = self.query_csv(minimum_rating_count=1)
        two_rating_minimum = self.query_csv(minimum_rating_count=2)
        self.assertEqual([row[0] for row in one_rating_minimum["highest_rated_movies"]], [1, 2])
        self.assertEqual([row[0] for row in two_rating_minimum["highest_rated_movies"]], [1])

        filtered = self.query_csv(
            minimum_rating_count=1,
            rating_minimum=4.5,
            movie_title_contains="alpha",
            movie_genre="Comedy",
        )
        self.assertEqual(filtered["rating_filters"], [[10, 1, 5.0, 1577836800]])
        self.assertEqual([row[0] for row in filtered["movie_filters"]], [1])
        injection_like = self.query_csv(movie_title_contains="' OR 1=1 --")
        self.assertEqual(injection_like["movie_filters"], [])

    def test_filter_and_limit_parameters_are_validated(self):
        with self.assertRaisesRegex(ValueError, "positive integers"):
            self.query_csv(result_limit=0)
        with self.assertRaisesRegex(ValueError, "finite"):
            self.query_csv(rating_minimum=float("nan"))
        with self.assertRaisesRegex(ValueError, "positive integer"):
            self.query_csv(rating_movie_id=-1)

    def test_timestamp_conversion_uses_utc_calendar_buckets(self):
        result = self.query_csv(minimum_rating_count=1)
        self.assertEqual(result["yearly_trend"], [["2020", 2, 4.0], ["2021", 1, 4.0]])
        self.assertEqual([row[0] for row in result["monthly_trend"]], [
            "2020-01", "2020-02", "2021-02",
        ])

    def test_top_n_per_genre_uses_window_rank_and_deterministic_ties(self):
        result = self.query_csv(minimum_rating_count=1, top_n=1)
        top = {row[0]: row for row in result["top_movies_per_genre"]}
        self.assertEqual(top["Action"][2], 1)
        self.assertEqual(top["Comedy"][2], 1)
        self.assertEqual(set(top), {"Action", "Comedy"})

    def test_user_activity_and_unrated_anti_join(self):
        result = self.query_csv(minimum_rating_count=1)
        self.assertEqual(result["user_activity_summary"]["active_user_count"], 2)
        self.assertEqual(result["user_activity_summary"]["maximum_ratings_by_one_user"], 2)
        self.assertEqual([row[0] for row in result["unrated_movies"]], [3, 4])

    def test_empty_and_missing_ratings_are_handled(self):
        self.write_ratings([])
        result = self.query_csv(minimum_rating_count=1, top_n=1)
        self.assertEqual(result["overview"]["rating_count"], 0)
        self.assertIsNone(result["overview"]["average_rating"])
        self.assertEqual(result["unrated_movies"], [
            [1, "Alpha Film", "Action|Comedy"],
            [2, "Beta Film", "Comedy"],
            [3, "Unrated Drama", "Drama"],
            [4, "No Genre", None],
        ])
        self.assertEqual(result["top_movies_per_genre"], [])
        self.assertEqual(sum(row[2] for row in result["genre_analytics"]), 0)

    def test_fully_empty_sources_produce_zero_counts(self):
        self.write_movies([])
        self.write_ratings([])
        result = self.query_csv(minimum_rating_count=1, top_n=1)
        self.assertEqual(result["overview"]["movie_count"], 0)
        self.assertEqual(result["overview"]["rating_count"], 0)
        self.assertEqual(result["rating_distribution"], [])
        self.assertEqual(result["genre_analytics"], [])
        self.assertEqual(result["unrated_movies"], [])

    def test_all_four_formats_have_equivalent_json_serializable_results(self):
        result = compare_all_formats(
            data_dir=self.data_dir,
            minimum_rating_count=1,
            top_n=2,
            movie_genre="Comedy",
        )
        self.assertEqual(result["result_equivalence"], "passed")
        self.assertTrue(result["temporary_cleanup_verified"])
        self.assertEqual(set(result["formats"]), {"csv", "uncompressed", "snappy", "zstd"})
        self.assertEqual(result["conversion_summary"]["rows"], {"movies": 4, "ratings": 3})
        json.dumps(result, allow_nan=False)

    def test_explain_plans_report_scans_joins_windows_and_row_group_metadata(self):
        report = compare_all_formats(
            data_dir=self.data_dir,
            minimum_rating_count=1,
            top_n=1,
        )
        for source_format in ("csv", "uncompressed", "snappy", "zstd"):
            plans = report["formats"][source_format]["query_plans"]
            self.assertTrue(plans["projection_and_predicate"]["explain"])
            self.assertTrue(plans["projection_and_predicate"]["explain_analyze"])
            self.assertTrue(plans["join_and_aggregation"]["observed_operators"]["hash_join"])
            self.assertTrue(plans["window_top_per_genre"]["observed_operators"]["window"])
        parquet_stats = report["formats"]["snappy"]["query_plans"]["parquet_row_group_statistics"]
        self.assertGreater(parquet_stats["ratings"]["row_group_count"], 0)
        self.assertGreater(parquet_stats["ratings"]["columns_with_min_max_statistics"], 0)


if __name__ == "__main__":
    unittest.main()
