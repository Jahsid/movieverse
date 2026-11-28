"""Coordinate correctness-checked ETL benchmark scenarios."""

import argparse
from contextlib import redirect_stdout
import json
import io
import platform
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.services.ingestion_service import load_movie_files
from scripts.benchmark_etl import build_changed_variant, build_dataset
from scripts.benchmark_postgres import benchmark_database
from scripts.benchmark_etl import peak_working_set_mib


ERROR_MARKER = "MOVIEVERSE_BENCHMARK_ERROR:"


def _safe_error_payload(error):
    """Expose exception class and project frame locations, never messages."""
    root = Path(__file__).resolve().parents[1]
    frames = []
    for frame in traceback.extract_tb(error.__traceback__):
        try:
            filename = Path(frame.filename).resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        frames.append(f"{filename}:{frame.lineno}")
    return {"error_type": type(error).__name__, "frames": frames[-5:]}


def _report_safe_error(error):
    print(ERROR_MARKER + json.dumps(_safe_error_payload(error)), file=sys.stderr)


def _check_counts(result, expected, scenario):
    inserted = result["inserted_records"]
    updated = result["updated_records"]
    unchanged = result["unchanged_records"]
    if result["processed_records"] != inserted + updated + unchanged:
        raise RuntimeError(f"{scenario} returned inconsistent source record counts")
    actual = (inserted, updated, unchanged)
    if actual != expected:
        raise RuntimeError(f"{scenario} returned unexpected source record counts")


def run_scenarios(source_directory, output_directory, size, batch_size,
                  lifecycle=benchmark_database, seed=2026, repetition=1):
    """Run initial, identical, then changed replay in one clean DB lifecycle."""
    source_dir = output_directory / size
    changed_dir = output_directory / f"{size}_changed"
    source = build_dataset(size, source_directory, source_dir, seed)
    changed = build_changed_variant(source_dir, changed_dir, seed)
    total = source["movie_rows"] + source["rating_rows"]
    changed_count = changed["changed_movie_rows"] + changed["changed_rating_rows"]
    results = []

    with lifecycle() as engine:
        session_factory = sessionmaker(bind=engine, class_=Session)
        for name, folder, expected in (
            ("initial", source_dir, (total, 0, 0)),
            ("identical_replay", source_dir, (0, 0, total)),
            ("changed_replay", changed_dir,
             (0, changed_count, total - changed_count)),
        ):
            with session_factory() as session:
                started = time.perf_counter()
                result = load_movie_files(
                    session, folder / "movies.csv", folder / "ratings.csv",
                    batch_size=batch_size,
                )
                duration = time.perf_counter() - started
            _check_counts(result, expected, name)
            results.append({
                "dataset_size": size,
                "content_fingerprint": result["content_fingerprint"],
                "seed": seed,
                "repetition": repetition,
                "scenario": name,
                "batch_size": batch_size,
                "ingestion_duration_seconds": duration,
                "processed_records_per_second": result["processed_records"] / duration if duration else 0,
                "processed_records": result["processed_records"],
                "inserted_records": result["inserted_records"],
                "updated_records": result["updated_records"],
                "unchanged_records": result["unchanged_records"],
                "users_inserted": result["users_inserted"],
                "users_skipped": result["users_skipped"],
            })
    return results


def _child(args):
    captured = io.StringIO()
    with redirect_stdout(captured):
        results = run_scenarios(args.source, args.output, args.size, args.batch_size,
                                seed=args.seed, repetition=args.repetition)
    memory = peak_working_set_mib()
    for result in results:
        result.update({
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "peak_process_working_set_mib": memory,
            "memory_scope": "whole child process high-water working set including imports, migration setup, all three scenarios, and cleanup",
            "measurement_scope": "ingestion duration times each service call only; excludes dataset generation, migration setup and cleanup",
        })
        print(json.dumps(result))


def run_group(size, batch_size, repetition, source, output, seed=2026, timeout=300):
    command = [sys.executable, "-m", "scripts.benchmark_scenarios", "--worker",
               "--size", size, "--batch-size", str(batch_size), "--repetition", str(repetition),
               "--source", str(Path(source).resolve()), "--output", str(Path(output).resolve()),
               "--seed", str(seed)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                   check=False, cwd=Path(__file__).resolve().parents[1])
    except subprocess.TimeoutExpired:
        raise RuntimeError("Scenario benchmark child timed out") from None
    if completed.returncode:
        diagnostic = ""
        for line in completed.stderr.splitlines():
            if line.startswith(ERROR_MARKER):
                try:
                    payload = json.loads(line[len(ERROR_MARKER):])
                    error_type = payload.get("error_type")
                    frames = payload.get("frames", [])
                    if (isinstance(error_type, str) and error_type.isidentifier()
                            and isinstance(frames, list)
                            and all(isinstance(frame, str) and len(frame) < 180
                                    and "\\" not in frame for frame in frames)):
                        location = ", ".join(frames)
                        diagnostic = f" ({error_type}" + (f" at {location}" if location else "") + ")"
                except (json.JSONDecodeError, AttributeError, TypeError):
                    pass
                break
        raise RuntimeError(
            f"Scenario benchmark child failed with code {completed.returncode}{diagnostic}"
        )
    try:
        records = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    except json.JSONDecodeError:
        raise RuntimeError("Scenario benchmark child returned malformed JSONL") from None
    if len(records) != 3 or [record.get("scenario") for record in records] != [
        "initial", "identical_replay", "changed_replay"
    ]:
        raise RuntimeError("Scenario benchmark child returned an incomplete scenario group")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--size", choices=("small", "medium", "full"), default="small")
    parser.add_argument("--batch-size", type=int, choices=(250, 1000, 2000), default=1000)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--repetition-start", type=int, default=1,
                        help="Identifier for the first repetition (useful when appending runs)")
    parser.add_argument("--repetition", type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--source", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--results", type=Path)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    if args.repetition_start < 1:
        parser.error("--repetition-start must be positive")
    if args.worker:
        if args.output is None:
            parser.error("worker mode requires --output")
        try:
            _child(args)
        except Exception as error:
            _report_safe_error(error)
            raise SystemExit(1) from None
        return
    records = []
    with tempfile.TemporaryDirectory(prefix="movieverse-scenarios-") as temporary:
        output = Path(temporary)
        for repetition in range(args.repetition_start,
                                 args.repetition_start + args.repetitions):
            records.extend(run_group(args.size, args.batch_size, repetition,
                                     args.source, output / str(repetition), args.seed))
    destination = args.results.open("a", encoding="utf-8") if args.results else None
    try:
        for record in records:
            line = json.dumps(record)
            print(line)
            if destination:
                destination.write(line + "\n")
    finally:
        if destination:
            destination.close()


if __name__ == "__main__":
    main()
