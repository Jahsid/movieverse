"""Standard-library tests for the sequential fresh-process benchmark."""

import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import duckdb
except ImportError as error:
    raise unittest.SkipTest("DuckDB is installed only in the isolated experiment environment") from error

from . import benchmark
from .row_group_pruning import _extract_scan_counts


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="movieverse-benchmark-test-")
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "raw"
        self.data_dir.mkdir()
        with (self.data_dir / "movies.csv").open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(["movieId", "title", "genres"])
            writer.writerows([[1, "First Film", "Action|Comedy"], [2, "Unrated", "Drama"]])
        with (self.data_dir / "ratings.csv").open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(["userId", "movieId", "rating", "timestamp"])
            writer.writerow([10, 1, 4.5, 1577836800])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_configuration_validates_formats_workloads_and_repetitions(self):
        config = benchmark.BenchmarkConfig(
            formats=("csv",), workloads=("full_row_scan",), repetitions=0
        )
        self.assertEqual(config.repetitions, 0)
        with self.assertRaisesRegex(ValueError, "unique source formats"):
            benchmark.BenchmarkConfig(formats=("csv", "csv"))
        with self.assertRaisesRegex(ValueError, "Unsupported query workloads"):
            benchmark.BenchmarkConfig(workloads=("count_only",))
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            benchmark.BenchmarkConfig(repetitions=-1)

    def test_measurement_consumes_all_rows_and_returns_deterministic_signature(self):
        with duckdb.connect(":memory:") as connection:
            connection.execute("CREATE TABLE ratings (rating DOUBLE)")
            connection.execute("INSERT INTO ratings VALUES (4.5), (3.0), (5.0)")
            result = benchmark.measure_workload(connection, "single_column_scan")
        self.assertEqual(result["result_rows_consumed"], 3)
        self.assertGreater(result["duration_seconds"], 0)
        self.assertGreater(result["correctness_validation_seconds"], 0)
        self.assertGreater(result["result_rows_per_second"], 0)
        self.assertTrue(result["result_signature"].startswith("3:"))

    def test_summary_statistics_report_minimum_median_and_maximum(self):
        records = [{"seconds": value} for value in (2.0, 1.0, 4.0, 3.0, 5.0)]
        self.assertEqual(benchmark.summarize_samples(records, "seconds"), {
            "minimum": 1.0, "median": 3.0, "maximum": 5.0,
        })

    def test_row_group_scan_count_is_read_from_plan_output(self):
        self.assertEqual(
            _extract_scan_counts("Table Scan\nRow Groups Scanned: 5 / 50\n"),
            (5, 50),
        )
        with self.assertRaisesRegex(RuntimeError, "did not report"):
            _extract_scan_counts("Table Scan\nno scan counters\n")

    def test_jsonl_records_are_serializable_and_flushed(self):
        output_path = self.root / "records.jsonl"
        with output_path.open("w", encoding="utf-8") as output:
            benchmark._append_jsonl(output_path, {"value": 4.5, "ok": True}, output)
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), {
            "value": 4.5, "ok": True,
        })

    def test_child_nonzero_exit_is_sanitized(self):
        completed = subprocess.CompletedProcess(
            args=["python"], returncode=7, stdout="", stderr=(
                "failed postgresql://user:secret@host/db password=hunter2"
            ),
        )
        with patch.object(benchmark.subprocess, "run", return_value=completed):
            with self.assertRaises(benchmark.ChildProcessError) as raised:
                benchmark.run_child(["--child-query"], 10)
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("hunter2", str(raised.exception))
        self.assertIn("REDACTED", str(raised.exception))

    def test_child_timeout_and_malformed_json_are_reported(self):
        with patch.object(benchmark.subprocess, "run", side_effect=subprocess.TimeoutExpired("python", 1)):
            with self.assertRaisesRegex(TimeoutError, "configured timeout"):
                benchmark.run_child(["--child-query"], 1)
        malformed = subprocess.CompletedProcess(args=["python"], returncode=0, stdout="not-json", stderr="")
        with patch.object(benchmark.subprocess, "run", return_value=malformed):
            with self.assertRaisesRegex(benchmark.ChildProcessError, "malformed JSON"):
                benchmark.run_child(["--child-query"], 10)

    def test_runner_preserves_raw_files_and_removes_temporary_work_directory(self):
        output_path = self.root / "smoke.jsonl"
        before = {
            path.name: path.read_bytes()
            for path in self.data_dir.glob("*.csv")
        }
        summary = benchmark.run_benchmark(
            benchmark.BenchmarkConfig(
                formats=("csv",), workloads=("full_row_scan",), repetitions=0
            ),
            self.data_dir,
            output_path,
            smoke_mode=True,
        )
        self.assertTrue(summary["raw_hashes_unchanged"])
        self.assertTrue(summary["temporary_work_directory_cleanup_verified"])
        self.assertEqual({path.name: path.read_bytes() for path in self.data_dir.glob("*.csv")}, before)
        records = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["record_type"] for record in records], ["query_sample", "summary"])
        self.assertEqual(records[0]["run_kind"], "first_observation")

    def test_runner_refuses_to_overwrite_existing_result_file(self):
        output_path = self.root / "existing.jsonl"
        output_path.write_text("existing", encoding="utf-8")
        with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
            benchmark.run_benchmark(
                benchmark.BenchmarkConfig(formats=("csv",), workloads=("full_row_scan",), repetitions=0),
                self.data_dir,
                output_path,
                smoke_mode=True,
            )
        self.assertEqual(output_path.read_text(encoding="utf-8"), "existing")


if __name__ == "__main__":
    unittest.main()
