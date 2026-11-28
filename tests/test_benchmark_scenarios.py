from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import benchmark_scenarios as scenarios


def test_scenarios_run_in_order_with_batch_and_expected_counts(tmp_path, monkeypatch):
    events = []

    def build(size, source, output, seed):
        return {"movie_rows": 10, "rating_rows": 20}

    def changed(source, output, seed):
        return {"changed_movie_rows": 1, "changed_rating_rows": 2}

    @contextmanager
    def lifecycle():
        events.append("lifecycle")
        yield object()

    def load(session, movies, ratings, *, batch_size):
        name = Path(movies).parent.name
        events.append((name, batch_size))
        scenario_index = len([event for event in events if isinstance(event, tuple)]) - 1
        values = ((30, 0, 0), (0, 0, 30), (0, 3, 27))[scenario_index]
        return dict(zip(("inserted_records", "updated_records", "unchanged_records"), values),
            processed_records=30, users_inserted=4, users_skipped=0,
            content_fingerprint="fingerprint")

    monkeypatch.setattr(scenarios, "build_dataset", build)
    monkeypatch.setattr(scenarios, "build_changed_variant", changed)
    monkeypatch.setattr(scenarios, "load_movie_files", load)
    result = scenarios.run_scenarios(tmp_path, tmp_path / "out", "medium", 250,
                                     lifecycle=lifecycle)
    assert events == ["lifecycle", ("medium", 250), ("medium", 250),
                      ("medium_changed", 250)]
    assert [item["scenario"] for item in result] == [
        "initial", "identical_replay", "changed_replay"
    ]
    assert result[2]["updated_records"] == 3
    assert result[2]["users_inserted"] == 4


def test_scenario_failure_stops_later_scenarios(tmp_path, monkeypatch):
    monkeypatch.setattr(scenarios, "build_dataset", lambda *args: {
        "movie_rows": 1, "rating_rows": 1
    })
    monkeypatch.setattr(scenarios, "build_changed_variant", lambda *args: {
        "changed_movie_rows": 1, "changed_rating_rows": 0
    })

    @contextmanager
    def lifecycle():
        yield object()

    calls = []

    def bad_counts(*args, **kwargs):
        calls.append(1)
        return {"processed_records": 2, "inserted_records": 0, "updated_records": 0,
                "unchanged_records": 2, "users_inserted": 0, "users_skipped": 0}

    monkeypatch.setattr(scenarios, "load_movie_files", bad_counts)
    with pytest.raises(RuntimeError, match="unexpected source record counts"):
        scenarios.run_scenarios(tmp_path, tmp_path / "out", "medium", 1000,
                                lifecycle=lifecycle)
    assert len(calls) == 1


def test_count_invariant_rejects_inconsistent_result():
    with pytest.raises(RuntimeError, match="inconsistent"):
        scenarios._check_counts({"processed_records": 5, "inserted_records": 1,
                                 "updated_records": 1, "unchanged_records": 1},
                                (3, 0, 2), "test")


def test_parent_worker_command_uses_supported_repetition_and_inherits_environment(
        tmp_path, monkeypatch):
    records = [{"scenario": name} for name in
               ("initial", "identical_replay", "changed_replay")]
    completed = subprocess.CompletedProcess([], 0,
                                            "".join(json.dumps(item) + "\n" for item in records), "")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return completed

    monkeypatch.setattr(scenarios.subprocess, "run", fake_run)
    result = scenarios.run_group("small", 1000, 2, tmp_path, tmp_path / "out")
    assert result == records
    command = captured["command"]
    assert command[command.index("--repetition") + 1] == "2"
    assert command[command.index("--batch-size") + 1] == "1000"
    assert "--worker" in command and "-m" in command
    assert captured["kwargs"]["cwd"] == Path(scenarios.__file__).resolve().parents[1]
    assert "env" not in captured["kwargs"]


def test_worker_cli_accepts_parent_repetition_argument(tmp_path, monkeypatch):
    received = []
    monkeypatch.setattr(scenarios, "_child", lambda args: received.append(args))
    monkeypatch.setattr(sys, "argv", [
        "benchmark_scenarios", "--worker", "--size", "small", "--batch-size", "1000",
        "--repetition", "2", "--source", str(tmp_path), "--output", str(tmp_path / "out"),
    ])
    scenarios.main()
    assert len(received) == 1
    assert received[0].repetition == 2


def test_parent_reports_only_allowlisted_child_diagnostics(tmp_path, monkeypatch):
    marker = scenarios.ERROR_MARKER + json.dumps({
        "error_type": "RuntimeError", "frames": ["scripts/benchmark_scenarios.py:88"],
        "message": "postgresql://user:secret@host/db SELECT * FROM private",
    })
    completed = subprocess.CompletedProcess([], 1, "", marker)
    monkeypatch.setattr(scenarios.subprocess, "run", lambda *args, **kwargs: completed)
    with pytest.raises(RuntimeError) as raised:
        scenarios.run_group("small", 1000, 1, tmp_path, tmp_path / "out")
    message = str(raised.value)
    assert "RuntimeError" in message
    assert "benchmark_scenarios.py:88" in message
    assert "secret" not in message and "SELECT" not in message


def test_child_error_report_omits_exception_message(capsys):
    try:
        raise RuntimeError("postgresql://role:password@127.0.0.1/db private-value")
    except RuntimeError as error:
        scenarios._report_safe_error(error)
    output = capsys.readouterr().err
    payload = json.loads(output.removeprefix(scenarios.ERROR_MARKER))
    assert payload["error_type"] == "RuntimeError"
    assert payload["frames"]
    assert "password" not in output and "private-value" not in output


def test_worker_failure_is_reported_without_exception_text(tmp_path, monkeypatch, capsys):
    def fail(_args):
        raise RuntimeError("postgresql://role:password@127.0.0.1/db private-value")

    monkeypatch.setattr(scenarios, "_child", fail)
    monkeypatch.setattr(sys, "argv", [
        "benchmark_scenarios", "--worker", "--source", str(tmp_path),
        "--output", str(tmp_path / "out"),
    ])
    with pytest.raises(SystemExit) as raised:
        scenarios.main()
    assert raised.value.code == 1
    output = capsys.readouterr().err
    assert scenarios.ERROR_MARKER in output
    assert "RuntimeError" in output
    assert "password" not in output and "private-value" not in output


def test_results_file_contains_one_json_record_per_line(tmp_path, monkeypatch):
    records = [{"scenario": name} for name in
               ("initial", "identical_replay", "changed_replay")]
    monkeypatch.setattr(scenarios, "run_group", lambda *args: records)
    result_file = tmp_path / "results.jsonl"
    monkeypatch.setattr(sys, "argv", ["benchmark_scenarios", "--results", str(result_file)])
    scenarios.main()
    lines = result_file.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == records


def test_repetition_start_creates_unique_append_identifiers(tmp_path, monkeypatch):
    calls = []

    def fake_run_group(size, batch_size, repetition, *args):
        calls.append(repetition)
        return [{"repetition": repetition, "scenario": name} for name in
                ("initial", "identical_replay", "changed_replay")]

    monkeypatch.setattr(scenarios, "run_group", fake_run_group)
    result_file = tmp_path / "matrix.jsonl"
    result_file.write_text('{"repetition": 1}\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "benchmark_scenarios", "--repetitions", "2", "--repetition-start", "2",
        "--results", str(result_file),
    ])
    scenarios.main()
    assert calls == [2, 3]
    lines = result_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 7
    assert [json.loads(line)["repetition"] for line in lines[1:]] == [2] * 3 + [3] * 3
