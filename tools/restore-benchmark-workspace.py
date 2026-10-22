#!/usr/bin/env python3
"""Verify or restore the archived benchmark workspace, without overwriting changes."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] / "history/benchmark-workspace/2026-10-22/manifest.json")
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    destination = args.destination.resolve()
    expected = {row["path"]: row for row in manifest["files"]}
    seen = set()
    # First verify every archive and existing destination. Nothing is written on failure.
    for archive in manifest["archives"]:
        path = args.manifest.parent / archive["path"]
        assert digest(path.read_bytes()) == archive["sha256"], f"Archive checksum: {path}"
        with tarfile.open(path, "r:gz") as source:
            for member in source:
                assert member.isfile() and member.name in expected and member.name not in seen, member.name
                target = (destination / member.name).resolve()
                assert target.is_relative_to(destination), member.name
                row = expected[member.name]
                data = source.extractfile(member).read()
                assert len(data) == row["bytes"] and digest(data) == row["sha256"], member.name
                if target.exists() and not args.verify_only:
                    assert target.is_file() and digest(target.read_bytes()) == row["sha256"], f"Refusing to overwrite changed file: {target}"
                seen.add(member.name)
    assert seen == set(expected), "Incomplete archive"
    if not args.verify_only:
        for archive in manifest["archives"]:
            with tarfile.open(args.manifest.parent / archive["path"], "r:gz") as source:
                for member in source:
                    target = destination / member.name
                    if not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with target.open("xb") as output:
                            output.write(source.extractfile(member).read())
    print(json.dumps({"verifiedFiles": len(seen), "bytes": sum(row["bytes"] for row in expected.values()), "restored": not args.verify_only}))


if __name__ == "__main__":
    main()
