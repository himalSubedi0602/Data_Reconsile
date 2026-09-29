"""SHA-256 fingerprints of the raw data files.

config/raw_checksums.json records the expected checksum of every file in data/raw/.
A checksum reveals nothing about a file's contents, so that file is safe to commit.

    python -m recon.checksums verify   # exit code 1 if any raw file changed
    python -m recon.checksums update   # record the current files (after a deliberate new export)
"""

import hashlib
import json
import sys
from pathlib import Path

from recon.config import DEFAULT_CONFIG, load_config

MANIFEST = Path("config/raw_checksums.json")


def sha256_of(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def checksums_of_dir(raw_dir) -> dict[str, str]:
    """Checksum of every file in raw_dir, keyed by path relative to raw_dir."""
    raw_dir = Path(raw_dir)
    return {
        p.relative_to(raw_dir).as_posix(): sha256_of(p)
        for p in sorted(raw_dir.rglob("*"))
        if p.is_file() and not p.name.startswith(".")
    }


def compare(expected: dict[str, str], actual: dict[str, str]) -> list[str]:
    """One human-readable line per difference; empty if the files match exactly."""
    problems = []
    for name in sorted(expected.keys() | actual.keys()):
        if name not in actual:
            problems.append(f"MISSING:  {name} is recorded but not found in the raw folder")
        elif name not in expected:
            problems.append(f"NEW:      {name} is in the raw folder but has no recorded checksum")
        elif expected[name] != actual[name]:
            problems.append(f"CHANGED:  {name} does not match its recorded checksum")
    return problems


def read_manifest(path=MANIFEST) -> dict[str, str]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["files"]


def write_manifest(checksums: dict[str, str], path=MANIFEST):
    Path(path).write_text(
        json.dumps({"algorithm": "sha256", "files": checksums}, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv not in (["verify"], ["update"]):
        print(__doc__)
        return 2
    raw_dir = load_config(DEFAULT_CONFIG).raw_dir
    actual = checksums_of_dir(raw_dir)

    if argv == ["update"]:
        write_manifest(actual)
        print(f"Recorded checksums of {len(actual)} files in {MANIFEST}. Commit this file.")
        return 0

    problems = compare(read_manifest(), actual)
    if problems:
        print("Raw data does not match config/raw_checksums.json:")
        print("\n".join("  " + p for p in problems))
        return 1
    print(f"All {len(actual)} raw files match their recorded checksums.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
