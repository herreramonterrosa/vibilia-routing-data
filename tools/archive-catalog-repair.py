#!/usr/bin/env python3
"""Archive only the 2026-10-23 catalog repair; default is a metadata-only plan.

Run --write only after the benchmark, publication and independent repair audit.
The manifest is compatible with tools/restore-benchmark-workspace.py.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import tarfile
import tempfile


CATALOG = Path("benchmarks/catalog-comparison")
REPAIR_LABELS = (
    "catalog-2026-10-23-error-repair",
    "catalog-2026-10-23-pyvrp-repair",
    "catalog-2026-10-23-vroom-deadline",
    "catalog-2026-10-23-remaining-repair",
    "catalog-2026-10-23-vroom-memory-repair",
    "catalog-2026-10-23-vroom-memory-admission",
)
BASELINE = CATALOG / "repair-2026-10-23-baseline"
ORIGINAL = CATALOG / "catalog-2026-10-21-second-pass-a38cd2c7548776b1"
MAX_COMPRESSED = 25 * 1024 * 1024
TARGET_RAW = 32 * 1024 * 1024


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha_stream(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(block)
    return result.hexdigest()


def digest(path):
    with path.open("rb") as stream:
        return sha_stream(stream)


def registered_series(root):
    """Read only the small registry. No discovery glob or report hashing here."""
    series = load(root / BASELINE / "repair-series.json")
    assert series.get("schemaVersion", 1) in (1, 2), "Unsupported repair-series schema"
    reports = series.get("reports")
    assert isinstance(reports, list) and reports, "Repair series has no registered reports"
    pattern = re.compile(
        re.escape(CATALOG.as_posix()) + r"/(?P<cohort>(?:" +
        "|".join(re.escape(label) for label in REPAIR_LABELS) + r")-[0-9a-f]{16})/report\.json"
    )
    cohorts, hashes = [], set()
    for entry in reports:
        match = pattern.fullmatch(entry.get("reportPath", ""))
        assert match, f"Report is outside the explicit repair-label allowlist: {entry.get('reportPath')}"
        for field in ("reportSha256", "auditSha256"):
            assert re.fullmatch(r"[0-9a-f]{64}", entry.get(field, "")), f"Invalid registry checksum: {field}"
        cohort = match["cohort"]
        assert cohort not in cohorts and entry["reportSha256"] not in hashes, "Duplicate repair cohort/report"
        cohorts.append(cohort)
        hashes.add(entry["reportSha256"])
    return series, cohorts


def selected_files(root, audit, cohorts, allow_missing_audit=False):
    paths = set()
    for relative in [*(CATALOG / name for name in cohorts), BASELINE]:
        folder = root / relative
        assert folder.is_dir() and not folder.is_symlink(), folder
        for path in folder.rglob("*"):
            assert not path.is_symlink(), f"Symlinks are not archival evidence: {path}"
            if path.is_file():
                paths.add(path)
    for relative in (
        ORIGINAL / "report.json", ORIGINAL / "audit.json",
        CATALOG / "latest.json", CATALOG / "execution.json", CATALOG / "execution.log",
    ):
        path = root / relative
        assert path.is_file(), f"Required provenance is missing: {relative}"
        paths.add(path)
    if audit.exists():
        paths.add(audit)
    else:
        assert allow_missing_audit, f"Final independent repair audit is missing: {audit}"
    for path in paths:
        assert path.resolve().is_relative_to(root) and stat.S_ISREG(path.lstat().st_mode), path
    return sorted(paths)


def stamp(root, paths):
    return {path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns) for path in paths}


def require_completed(root, audit):
    execution = load(root / CATALOG / "execution.json")
    assert execution.get("state") == "complete" and execution.get("finishedAt"), "Benchmark is not complete"
    assert not (root / CATALOG / "execution.lock").exists(), "Benchmark execution lock is still present"
    series, cohorts = registered_series(root)
    latest = load(root / CATALOG / "latest.json")
    assert latest["directory"] == (CATALOG / cohorts[-1]).as_posix(), "Latest cohort is not the final registered repair cohort"
    assert latest["reportPath"] == series["reports"][-1]["reportPath"], "Latest report is not the final registered repair report"
    final_report = load(root / latest["reportPath"])
    assert final_report["scheduling"]["activeRun"] is None, "Final cohort still has an active execution"
    summary = load(audit)
    assert summary.get("valid") is True and summary.get("targetedExecutions") == 38, "Repair audit is not final/valid"
    assert summary["reportPath"] == latest["reportPath"], "Audit belongs to a different final report"
    return latest, summary, series, cohorts


def verify_archives(folder, manifest):
    expected = {row["path"]: row for row in manifest["files"]}
    seen = set()
    for archive in manifest["archives"]:
        path = folder / archive["path"]
        assert path.stat().st_size <= MAX_COMPRESSED and digest(path) == archive["sha256"], path
        with tarfile.open(path, "r:gz") as source:
            for member in source:
                assert member.isfile() and member.name in expected and member.name not in seen, member.name
                row = expected[member.name]
                assert member.size == row["bytes"], member.name
                with source.extractfile(member) as stream:
                    assert sha_stream(stream) == row["sha256"], member.name
                seen.add(member.name)
    assert seen == set(expected), "Incomplete archive"


def write_archive(root, destination, audit, paths):
    assert not destination.exists(), f"Refusing to replace archive: {destination}"
    initial_stamp = stamp(root, paths)
    latest, summary, series, cohorts = require_completed(root, audit)
    rows = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)} for path in paths]
    by_path = {row["path"]: row for row in rows}
    baseline = load(root / BASELINE / "baseline.json")
    assert by_path[(ORIGINAL / "report.json").as_posix()]["sha256"] == baseline["reportSha256"]
    assert by_path[(ORIGINAL / "audit.json").as_posix()]["sha256"] == baseline["auditSha256"]
    assert by_path[latest["reportPath"]]["sha256"] == summary["reportSha256"]
    assert by_path[(BASELINE / "baseline.json").as_posix()]["sha256"] == summary["baselineSha256"]
    assert by_path[(BASELINE / "repair-series.json").as_posix()]["sha256"] == summary["repairSeriesSha256"]
    for entry in series["reports"]:
        assert by_path[entry["reportPath"]]["sha256"] == entry["reportSha256"]
        assert by_path[str(Path(entry["reportPath"]).with_name("audit.json"))]["sha256"] == entry["auditSha256"]
    manifest = {
        "schemaVersion": 1,
        "kind": "catalog-error-repair",
        "description": "Exactly the cohorts registered in repair-series.json under the explicit repair-label allowlist, baseline, original baseline report/audit, final execution pointers/log and independent final audit. Current SPA exports and unrelated raw workspaces are excluded.",
        "archivedAt": datetime.now(timezone.utc).isoformat(),
        "sourceCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "cohortDirectories": [(CATALOG / name).as_posix() for name in cohorts],
        "repairSeriesSha256": by_path[(BASELINE / "repair-series.json").as_posix()]["sha256"],
        "finalReportPath": latest["reportPath"],
        "repairAuditPath": audit.relative_to(root).as_posix(),
        "maxCompressedPartBytes": MAX_COMPRESSED,
        "archives": [], "files": rows,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".catalog-repair-", dir=destination.parent) as temporary:
        staging = Path(temporary)

        def pack(chunk):
            candidate = staging / "candidate.tar.gz"
            with tarfile.open(candidate, "w:gz", compresslevel=6, dereference=True) as output:
                for row in chunk:
                    output.add(root / row["path"], arcname=row["path"], recursive=False)
            if candidate.stat().st_size > MAX_COMPRESSED:
                candidate.unlink()
                assert len(chunk) > 1, f"A single compressed file exceeds 25 MiB; no oversized archive was published: {chunk[0]['path']}"
                midpoint = len(chunk) // 2
                pack(chunk[:midpoint])
                pack(chunk[midpoint:])
                return
            target = staging / f"part-{len(manifest['archives']) + 1:03}.tar.gz"
            candidate.rename(target)
            manifest["archives"].append({"path": target.name, "bytes": target.stat().st_size, "sha256": digest(target)})

        chunk, size = [], 0
        for row in rows:
            if chunk and size + row["bytes"] > TARGET_RAW:
                pack(chunk)
                chunk, size = [], 0
            chunk.append(row)
            size += row["bytes"]
        if chunk:
            pack(chunk)
        manifest.update(fileCount=len(rows), originalBytes=sum(row["bytes"] for row in rows),
                        compressedBytes=sum(row["bytes"] for row in manifest["archives"]))
        verify_archives(staging, manifest)
        require_completed(root, audit)
        assert stamp(root, selected_files(root, audit, registered_series(root)[1])) == initial_stamp, "Source evidence changed while archiving"
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        staging.rename(destination)
    return {key: manifest[key] for key in ("fileCount", "originalBytes", "compressedBytes")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--audit", type=Path, required=True, help="Final JSON emitted by audit-catalog-error-repair.py")
    parser.add_argument("--archive", type=Path, default=Path("history/benchmark-workspace/2026-10-23-error-repair"))
    parser.add_argument("--write", action="store_true", help="Hash, compress and independently verify after all measurements finish")
    args = parser.parse_args()
    root = args.root.resolve()
    audit = (root / args.audit).resolve()
    destination = (root / args.archive).resolve()
    assert audit.is_relative_to(root) and not audit.is_relative_to(destination), "Audit must be inside data root, outside destination"
    assert destination.is_relative_to(root / "history/benchmark-workspace"), "Archive must be in this data repository's benchmark history"
    _, cohorts = registered_series(root)
    paths = selected_files(root, audit, cohorts, allow_missing_audit=not args.write)
    result = write_archive(root, destination, audit, paths) if args.write else {
        "mode": "plan-only-no-hashes-no-compression", "fileCount": len(paths),
        "originalBytes": sum(path.stat().st_size for path in paths),
        "missingFinalAudit": not audit.exists(), "maxCompressedPartBytes": MAX_COMPRESSED,
        "archive": str(destination), "registeredCohorts": len(cohorts),
        "selectedRoots": [(CATALOG / name).as_posix() for name in cohorts] + [BASELINE.as_posix()],
        "additionalProvenance": [str(ORIGINAL / "report.json"), str(ORIGINAL / "audit.json"),
                                 str(CATALOG / "latest.json"), str(CATALOG / "execution.json"), str(CATALOG / "execution.log"), str(args.audit)],
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
