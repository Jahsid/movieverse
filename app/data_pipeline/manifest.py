"""Read-only metadata and fingerprints for MovieVerse's raw CSV inputs."""

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_FILES = ("movies.csv", "ratings.csv")


def inspect_csv(directory: Path, relative_path: str) -> dict:
    """Stream a CSV to count rows and hash its bytes without loading it into RAM."""
    name = Path(relative_path)
    if name.is_absolute() or ".." in name.parts:
        raise ValueError("File names must stay inside the dataset directory")
    path = directory / name
    before = path.stat()
    if before.st_size == 0:
        raise ValueError(f"Empty CSV file: {relative_path}")

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            columns = next(reader, None)
            if not columns or not all(column.strip() for column in columns):
                raise ValueError(f"Missing CSV header: {relative_path}")
            if len(columns) != len(set(columns)):
                raise ValueError(f"Duplicate CSV columns: {relative_path}")
            row_count = 0
            for row in reader:
                if len(row) != len(columns):
                    raise ValueError(f"Malformed CSV row in {relative_path} at line {reader.line_num}")
                row_count += 1
    except (csv.Error, UnicodeError) as error:
        raise ValueError(f"Malformed CSV file: {relative_path}") from error

    if row_count == 0:
        raise ValueError(f"CSV has no data rows: {relative_path}")
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"CSV changed while being inspected: {relative_path}")
    return {
        "relative_path": name.as_posix(),
        "size_bytes": after.st_size,
        "sha256": digest.hexdigest(),
        "row_count": row_count,
        "columns": columns,
    }


def content_fingerprint(files: list[dict]) -> str:
    """Hash file names and byte checksums; omit generation time and metadata."""
    fingerprints = sorted(
        (item["relative_path"], item["sha256"]) for item in files
    )
    encoded = json.dumps(fingerprints, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def generate_manifest(directory: Path, file_names=DEFAULT_FILES) -> dict:
    """Describe the actual local files; source/version follow repository evidence."""
    if not file_names:
        raise ValueError("At least one CSV file is required")
    files = [inspect_csv(directory, name) for name in file_names]
    return {
        "manifest_schema_version": 1,
        "dataset_name": "MovieLens",
        "source": {"name": "MovieLens", "url": None},
        "dataset_version": None,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "content_fingerprint": content_fingerprint(files),
        "files": files,
    }


def compare_manifests(previous: dict, current: dict) -> dict:
    """Report file content changes, independent of generation timestamps."""
    def file_hashes(manifest):
        try:
            return {item["relative_path"]: item["sha256"] for item in manifest["files"]}
        except (KeyError, TypeError) as error:
            raise ValueError("Invalid manifest file entries") from error

    old = file_hashes(previous)
    new = file_hashes(current)
    return {
        "changed": old != new,
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "modified": sorted(name for name in old.keys() & new.keys() if old[name] != new[name]),
        "unchanged": sorted(name for name in old.keys() & new.keys() if old[name] == new[name]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, help="Save JSON to a new file; stdout is the default")
    parser.add_argument("--compare", type=Path, help="Compare with an existing manifest JSON")
    args = parser.parse_args()
    try:
        manifest = generate_manifest(args.directory)
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(json.dumps(manifest, indent=2) + "\n")
        if args.compare:
            previous = json.loads(args.compare.read_text(encoding="utf-8"))
            result = {"manifest": manifest, "comparison": compare_manifests(previous, manifest)}
        else:
            result = manifest
    except (OSError, ValueError) as error:
        parser.exit(2, f"Manifest error: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
