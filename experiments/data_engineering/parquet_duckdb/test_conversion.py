"""Standard-library tests for the isolated CSV-to-Parquet converter."""

import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

try:
    import duckdb
except ImportError as error:
    raise unittest.SkipTest("DuckDB is installed only in the isolated experiment environment") from error

from .conversion import (
    COMPRESSION_OPTIONS,
    DataIntegrityError,
    convert_dataset,
)


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="movieverse-conversion-test-")
        self.root = Path(self.temp_dir.name)
        self.source_dir = self.root / "raw"
        self.source_dir.mkdir()
        self.write_sources()

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_sources(self, movies=None, ratings=None):
        movies = movies or [
            [1, "Toy Story", "Adventure|Animation"],
            [2, "Unrated Movie", ""],
        ]
        ratings = ratings or [
            [10, 1, 4.5, 964982703],
            [11, 1, 3.0, 964982224],
        ]
        self._write_csv("movies.csv", ["movieId", "title", "genres"], movies)
        self._write_csv("ratings.csv", ["userId", "movieId", "rating", "timestamp"], ratings)

    def _write_csv(self, name, columns, rows):
        with (self.source_dir / name).open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(columns)
            writer.writerows(rows)

    def test_conversion_preserves_schema_values_and_every_compression(self):
        output_dir = self.root / "converted"
        report = convert_dataset(self.source_dir, output_dir)

        self.assertEqual(set(report["compressions"]), set(COMPRESSION_OPTIONS))
        self.assertEqual(report["source_files"]["movies"]["row_count"], 2)
        self.assertEqual(report["source_files"]["ratings"]["row_count"], 2)
        self.assertEqual(report["source_profile"]["unrated_movies"], 1)
        self.assertTrue(report["raw_hashes_unchanged"])
        self.assertFalse(report["output_temporary"])
        self.assertTrue(report["quality_checks"])
        for compression in COMPRESSION_OPTIONS:
            files = report["compressions"][compression]["files"]
            self.assertEqual(files["movies"]["schema"], [
                {"name": "movieId", "type": "INTEGER"},
                {"name": "title", "type": "VARCHAR"},
                {"name": "genres", "type": "VARCHAR"},
            ])
            self.assertEqual(files["ratings"]["schema"], [
                {"name": "userId", "type": "INTEGER"},
                {"name": "movieId", "type": "INTEGER"},
                {"name": "rating", "type": "DOUBLE"},
                {"name": "timestamp", "type": "BIGINT"},
            ])
            self.assertTrue(files["movies"]["logical_values_equal"])
            self.assertTrue(files["ratings"]["logical_values_equal"])
            self.assertEqual(files["movies"]["row_count"], 2)
            self.assertTrue((output_dir / files["movies"]["file_name"]).is_file())

    def test_default_output_is_temporary_and_cleaned(self):
        report = convert_dataset(self.source_dir, compressions=("zstd",))
        self.assertTrue(report["output_temporary"])
        self.assertTrue(report["output_cleanup_verified"])

    def test_empty_genres_follow_csv_null_handling(self):
        output_dir = self.root / "empty-genre"
        report = convert_dataset(self.source_dir, output_dir, compressions=("snappy",))
        self.assertEqual(report["source_files"]["movies"]["null_counts"]["genres"], 1)
        self.assertEqual(report["source_files"]["movies"]["empty_string_counts"]["genres"], 0)
        parquet_path = output_dir / report["compressions"]["snappy"]["files"]["movies"]["file_name"]
        with duckdb.connect(":memory:") as connection:
            self.assertIsNone(connection.execute(
                "SELECT genres FROM read_parquet(?) WHERE movieId = 2", [str(parquet_path)]
            ).fetchone()[0])

    def test_duplicate_movie_ids_are_rejected(self):
        self.write_sources(movies=[
            [1, "First", "Drama"],
            [1, "Duplicate", "Comedy"],
        ])
        with self.assertRaisesRegex(DataIntegrityError, "duplicate_movie_rows=2"):
            convert_dataset(self.source_dir, self.root / "duplicate-movies")

    def test_duplicate_user_movie_ratings_are_rejected(self):
        self.write_sources(ratings=[
            [10, 1, 4.5, 964982703],
            [10, 1, 3.0, 964982224],
        ])
        with self.assertRaisesRegex(DataIntegrityError, "duplicate_rating_rows=2"):
            convert_dataset(self.source_dir, self.root / "duplicate-ratings")

    def test_missing_movie_reference_is_rejected(self):
        self.write_sources(ratings=[[10, 999, 4.5, 964982703]])
        with self.assertRaisesRegex(DataIntegrityError, "invalid_movie_references=1"):
            convert_dataset(self.source_dir, self.root / "bad-reference")

    def test_invalid_rating_is_rejected(self):
        self.write_sources(ratings=[[10, 1, 4.2, 964982703]])
        with self.assertRaisesRegex(DataIntegrityError, "invalid_ratings=1"):
            convert_dataset(self.source_dir, self.root / "bad-rating")

    def test_raw_inputs_are_unchanged_after_conversion(self):
        before = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.source_dir.glob("*.csv"))
        }
        convert_dataset(self.source_dir, compressions=("snappy",))
        after = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.source_dir.glob("*.csv"))
        }
        self.assertEqual(after, before)

    def test_nonempty_output_directory_is_not_overwritten(self):
        output_dir = self.root / "existing"
        output_dir.mkdir()
        marker = output_dir / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "new or empty"):
            convert_dataset(self.source_dir, output_dir)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
