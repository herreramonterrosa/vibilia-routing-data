#!/usr/bin/env python3
"""Archive legacy application benchmark outputs with byte-for-byte checksums."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_files(root):
    selected = set()
    catalog = root / "benchmarks/catalog-comparison"
    for path in catalog.iterdir():
        if path.is_dir() and (path.name.startswith(("catalog-", "prepared-fixes-")) or path.name.endswith("playwright-artifacts") or path.name == "sources"):
            selected.update(p for p in path.rglob("*") if p.is_file())
        elif path.is_file() and path.suffix in (".json", ".log", ".lock"):
            selected.add(path)
    for folder in ("benchmarks/cvrplib-native", "benchmarks/cvrplib-improvements", "benchmarks/route-limits"):
        selected.update(p for p in (root / folder).glob("*.json") if p.name != "suite.json")
    selected.update((root / "benchmarks").glob("*.json"))
    selected.update(p for p in (root / "benchmarks/webgpu-routing/results").rglob("*") if p.is_file())
    selected.update(p for p in (root / "scripts/snapshots").rglob("*") if p.is_file())
    selected.update((root / "mydev/docs").rglob("*.json"))
    selected.update((root / "benchmarks/route-limits").glob("comparison-*.md"))
    return sorted(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    root = args.source.resolve()
    archive = args.archive.resolve()
    assert not archive.is_relative_to(root), "Archive must be outside the app"
    archive.mkdir(parents=True, exist_ok=False)
    files = select_files(root)
    manifest = {"schemaVersion": 1, "description": "Original benchmark outputs and recovery evidence; independent from current viewer manifest/scenarios and historical measurement archive.", "sourceCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(), "archives": [], "files": []}
    chunks = [[]]
    size = 0
    for path in files:
        assert path.resolve().is_relative_to(root) and not path.is_symlink(), path
        row = {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)}
        if chunks[-1] and size + row["bytes"] > 32 * 1024 * 1024:
            chunks.append([])
            size = 0
        chunks[-1].append((path, row))
        size += row["bytes"]
        manifest["files"].append(row)
    for index, chunk in enumerate(chunks):
        target = archive / f"part-{index + 1:03}.tar.gz"
        with tarfile.open(target, "w:gz", compresslevel=6) as output:
            for path, row in chunk:
                output.add(path, arcname=row["path"], recursive=False)
        manifest["archives"].append({"path": target.name, "bytes": target.stat().st_size, "sha256": digest(target)})
        print(f"Archived {index + 1}/{len(chunks)}", flush=True)
    manifest["fileCount"] = len(files)
    manifest["originalBytes"] = sum(row["bytes"] for row in manifest["files"])
    manifest["compressedBytes"] = sum(row["bytes"] for row in manifest["archives"])
    (archive / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({key: manifest[key] for key in ("fileCount", "originalBytes", "compressedBytes")}))


if __name__ == "__main__":
    main()
