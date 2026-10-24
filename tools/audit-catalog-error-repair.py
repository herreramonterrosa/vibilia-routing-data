"""Check that a targeted repair preserved every other published measurement."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def measurement_hash(record, fields):
    selected = {key: record[key] for key in fields if key in record}
    return sha(json.dumps(selected, sort_keys=True, separators=(",", ":")).encode())


def key(record):
    return record["exampleId"] + "/" + record["method"]


def without_recovery_metadata(record):
    # Recovery legitimately adds/replaces only the links to immutable origin
    # evidence and its current revalidation. Every measurement field remains.
    return {k: v for k, v in record.items() if k not in ("origin", "revalidation")}


CONSTRAINT_FIELDS = (
    "sourceSha256", "family", "dimension", "profile", "vehicles", "minimumVehicles",
    "capacity", "originalServiceTotal", "maxRouteDuration", "objective", "rounding",
    "integerScale", "budgetSeconds", "repetition",
)
EXPECTED_SERIES = {
    "catalog-2026-10-23-error-repair": 6,       # A: first repair attempt
    "catalog-2026-10-23-pyvrp-repair": 3,       # B: repaired Pyodide bridge
    "catalog-2026-10-23-vroom-deadline": 1,    # D: verified VROOM delivery
    "catalog-2026-10-23-remaining-repair": 32, # E: remaining exact pairs
}
BASE_SERIES_IDS = ("A", "B", "D", "E")
REVIEWED_DELIVERY_RETRIES = {
    "cvrplib-ags-antwerp1/vroom",
    "cvrplib-xl-xl-n3334-k934/vroom",
    "cvrplib-xl-xl-n3888-k1010/vroom",
    "cvrplib-xl-xl-n3975-k687/vroom",
}


def prior_reference(report_sha256, record):
    return {"reportSha256": report_sha256, "measuredAt": record["measuredAt"], "outcome": record["outcome"]}


def same_constraints(record, previous):
    assert all(record.get(field) == previous.get(field) for field in CONSTRAINT_FIELDS), \
        "Constraints changed: " + key(record)


def published_records(root, manifest):
    """Read immutable scenario files without collapsing duplicate observations."""
    records = {}
    total_valid = 0
    without_solution = []
    for example_id, info in manifest["scenarios"].items():
        data = (root / info["path"]).read_bytes()
        assert sha(data) == info["sha256"] and len(data) == info["bytes"], "Scenario integrity failed"
        scenario = json.loads(data)
        assert scenario["exampleId"] == example_id, "Scenario identity differs from manifest"
        valid = False
        for suite in scenario["suites"]:
            assert suite["runCount"] == len(suite["records"]), "Published suite count differs"
            for record in suite["records"]:
                assert record["exampleId"] == example_id, "Published record belongs to another scenario"
                name = example_id + "/" + str(suite["budgetSeconds"]) + "/" + record["method"]
                assert name not in records, "Duplicate published measurement: " + name
                records[name] = record
                total_valid += int(record["valid"])
                valid |= record["valid"]
        if not valid:
            without_solution.append(example_id)
    return records, total_valid, without_solution


def progress(root, baseline_path):
    baseline = load(baseline_path)
    targets = set(baseline["runKeys"])
    previous = {key(run): run for run in load(root / baseline["source"]["reportPath"])["runs"]}
    latest = load(root / "benchmarks/catalog-comparison/latest.json")
    report = load(root / latest["reportPath"])
    fresh = [run for run in report["runs"] if not run.get("origin")]
    assert not {key(run) for run in fresh} - targets, "Unexpected execution outside repair scope"
    completed = [run for run in report["runs"] if key(run) in targets and run["measuredAt"] > previous[key(run)]["measuredAt"]]
    return {
        "completed": len(completed),
        "remaining": len(targets) - len(completed),
        "outcomes": dict(Counter(run["outcome"] for run in completed)),
        "byMethod": {
            method: dict(Counter(run["outcome"] for run in completed if run["method"] == method))
            for method in ("vroom", "jsprit", "pyvrp")
        },
        "active": report["scheduling"]["activeRun"],
        "currentScopePending": report["scheduling"]["queuedRetries"],
        "lastCompleted": [
            {field: run.get(field) for field in ("name", "method", "outcome", "elapsedMs", "cost", "usedVehicles", "reason")}
            for run in sorted(completed, key=lambda run: run["measuredAt"], reverse=True)[:2]
        ],
    }


def audit(root, baseline_path):
    baseline = load(baseline_path)
    original_bytes = (root / baseline["source"]["reportPath"]).read_bytes()
    assert sha(original_bytes) == baseline["reportSha256"], "Original report changed"
    original = json.loads(original_bytes)
    original_audit = (root / baseline["source"]["auditPath"]).read_bytes()
    assert sha(original_audit) == baseline["auditSha256"], "Original audit changed"
    assert json.loads(original_audit)["reportSha256"] == sha(original_bytes)
    previous = {key(run): run for run in original["runs"]}
    for name, run in previous.items():
        assert sha(json.dumps(run, sort_keys=True, separators=(",", ":")).encode()) == baseline["sourceRuns"][name]
    targets = set(baseline["runKeys"])
    assert targets == {name for name, run in previous.items() if run["outcome"] == "error"}
    assert len(targets) == 38 and len(previous) - len(targets) == 4681, "Original repair scope differs"

    latest = load(root / "benchmarks/catalog-comparison/latest.json")
    report_bytes = (root / latest["reportPath"]).read_bytes()
    report = json.loads(report_bytes)
    proof = load(root / latest["auditPath"])
    assert proof["valid"] and not proof["issues"], "Independent audit failed"
    assert proof["reportSha256"] == sha(report_bytes), "New report differs from audit"
    assert proof["verifiedFileHashes"] == report["sha256"], "Configuration audit differs"
    current = {key(run): run for run in report["runs"]}
    assert len(current) == len(report["runs"]), "Duplicate observations"
    assert current.keys() == previous.keys(), "Catalog observation coverage changed"
    assert set(report["retryScope"]) <= targets, "Repair scope includes an unrelated observation"
    assert report["protocol"] == original["protocol"], "Measurement protocol changed"
    assert report["environment"] == original["environment"], "Measurement environment changed"

    series_path = baseline_path.with_name("repair-series.json")
    series = load(series_path)
    assert series.get("schemaVersion") == 2, "Repair series requires explicit v2 execution scopes"
    assert len(series["reports"]) >= 4, "Base repair series is incomplete"
    assert tuple(entry["id"] for entry in series["reports"][:4]) == BASE_SERIES_IDS, "Base repair cohort order differs"
    attempts = {}
    registered_reports = set()
    registered_cohorts = set()
    series_counts = {}
    recovered_observations = []
    ledger = {name: (baseline["reportSha256"], run) for name, run in previous.items()}
    valid_ever = {name for name, run in previous.items() if run["valid"]}
    reviewed_delivery = set()
    entry_ids = set()
    expected_extra_attempts = 0
    for position, entry in enumerate(series["reports"]):
        entry_id = entry["id"]
        assert isinstance(entry_id, str) and entry_id and entry_id not in entry_ids, "Duplicate repair entry ID"
        entry_ids.add(entry_id)
        expected_keys = entry["expectedFreshRunKeys"]
        assert isinstance(expected_keys, list) and expected_keys and len(set(expected_keys)) == len(expected_keys), \
            "Fresh execution scope must be an explicit nonempty unique list"
        assert set(expected_keys) <= targets, "Expected fresh execution is outside the original 38 errors"
        assert set(entry["retryFrom"]) == set(expected_keys), "Retry references differ from the explicit execution scope"
        reviews = entry.get("reviewedRetries", [])
        assert isinstance(reviews, list), "Reviewed retries must be explicit evidence entries"
        review_by_key = {review["runKey"]: review for review in reviews}
        assert len(review_by_key) == len(reviews) and set(review_by_key) <= set(expected_keys), "Duplicate or unrelated review"
        if position >= 4:
            assert entry_id not in BASE_SERIES_IDS and not reviews, \
                "Later cohorts may retry technical errors only, without no-solution exceptions"
            expected_extra_attempts += len(expected_keys)
        source_bytes = (root / entry["reportPath"]).read_bytes()
        source_proof_bytes = (root / entry["reportPath"]).with_name("audit.json").read_bytes()
        assert sha(source_bytes) == entry["reportSha256"], "Repair series report changed"
        assert sha(source_proof_bytes) == entry["auditSha256"], "Repair series audit changed"
        source_report = json.loads(source_bytes)
        source_proof = json.loads(source_proof_bytes)
        assert source_proof["valid"] and not source_proof["issues"]
        assert source_proof["reportSha256"] == entry["reportSha256"]
        assert source_proof["verifiedFileHashes"] == source_report["sha256"], "Repair configuration audit differs"
        assert source_report["protocol"] == original["protocol"], "Repair attempt protocol changed"
        assert source_report["environment"] == original["environment"], "Repair attempt environment changed"
        label = source_report["label"]
        assert label not in series_counts, "Duplicate repair cohort label"
        if position < 4:
            expected_label, expected_count = list(EXPECTED_SERIES.items())[position]
            assert label == expected_label and len(expected_keys) == expected_count, \
                "Base repair series must preserve A=6, B=3, D=1, E=32"
        else:
            assert label not in EXPECTED_SERIES, "Later repair cannot replace a base cohort"
        cohort = source_report["cohortId"]
        assert cohort not in registered_cohorts, "Repair cohort registered twice"
        registered_cohorts.add(cohort)
        registered_reports.add(entry["reportSha256"])
        source_runs = {key(run): run for run in source_report["runs"]}
        assert len(source_runs) == len(source_report["runs"]), "Duplicate repair-series observations"
        assert source_runs.keys() == previous.keys(), "Repair-series observation coverage changed"
        assert set(source_report["retryScope"]) <= targets, "Repair-series scope includes an unrelated observation"
        assert set(expected_keys) <= set(source_report["retryScope"]), "Fresh attempts were not in the configured retry scope"
        if position >= 4:
            assert set(expected_keys) == set(source_report["retryScope"]), "Later cohort must finish its entire explicit error scope"

        # Canonical records alone cannot reveal a result overwritten during a
        # resumed cohort. Include immutable archived attempts as well, verifying
        # their content-addressed file names before deduplicating exact copies.
        observations = list(source_report["runs"])
        for path in sorted((root / entry["reportPath"]).parent.joinpath("attempts").glob("*.json")):
            archived_bytes = path.read_bytes()
            assert sha(archived_bytes) == path.name.rsplit("--", 1)[-1].removesuffix(".json"), \
                "Archived attempt hash differs: " + str(path)
            observations.append(json.loads(archived_bytes))
        cohort_attempts = set()
        for run in observations:
            name = key(run)
            assert name in previous, "Unknown archived or current observation: " + name
            same_constraints(run, previous[name])
            if name not in targets:
                assert run.get("origin"), "A protected observation was executed again: " + name
                assert without_recovery_metadata(run) == without_recovery_metadata(previous[name]), \
                    "Protected repair-series observation changed: " + name
            if run.get("origin"):
                recovered_observations.append(run)
                continue
            assert name in targets, "Unexpected fresh execution outside the original 38 errors: " + name
            assert run["measuredAt"] > previous[name]["measuredAt"], "Fresh execution predates repair: " + name
            marker = run["retryAttempt"]
            assert marker["cohortId"] == cohort and marker["finishedAt"], "Incomplete or foreign archived retry: " + name
            identity = (cohort, name, run["measuredAt"])
            if identity in attempts:
                assert attempts[identity] == run, "Repair attempt changed between its archive and canonical record"
            else:
                attempts[identity] = run
            cohort_attempts.add(identity)
        series_counts[label] = len(cohort_attempts)
        by_name = Counter(name for _, name, _ in cohort_attempts)
        assert by_name == Counter(expected_keys), "Actual fresh attempts differ from the explicit execution scope"
        for identity in sorted(cohort_attempts, key=lambda value: value[2]):
            run = attempts[identity]
            name = key(run)
            prior_sha, prior = ledger[name]
            assert name not in valid_ever, "An already valid observation was executed again: " + name
            assert run["retryAttempt"]["startedAt"] >= prior["measuredAt"], "Retry precedes its prior observation"
            reference = prior_reference(prior_sha, prior)
            assert entry["retryFrom"][name] == reference, "Retry does not reference the latest prior attempt: " + name
            assert prior["valid"] is False and prior["cost"] is None and prior.get("reason"), \
                "Retry requires an actual unsuccessful prior observation: " + name
            if prior["outcome"] in ("error", "resource_limit"):
                assert name not in review_by_key, "Technical retries must not carry unrelated no-solution reviews"
            else:
                review = review_by_key.get(name)
                assert position in (2, 3) and prior["outcome"] == "no_solution" and name in REVIEWED_DELIVERY_RETRIES, \
                    "Only four previously reviewed VROOM no-solution results may be retried"
                assert review and review.get("prior") == reference and review.get("kind") == "vroom-incumbent-delivery", \
                    "No-solution retry lacks its exact prior observation and delivery review: " + name
                assert isinstance(review.get("reason"), str) and review["reason"].strip(), "Missing review reason"
                assert name not in reviewed_delivery, "No-solution review was reused"
                reviewed_delivery.add(name)
            ledger[name] = (entry["reportSha256"], run)
            if run["valid"]:
                valid_ever.add(name)
    assert sha(report_bytes) in registered_reports, "Final report is missing from repair series"
    assert all(series_counts.get(label) == count for label, count in EXPECTED_SERIES.items()), "Base cohort attempt counts differ"
    assert len(attempts) == 42 + expected_extra_attempts, "Unexpected repair attempt count"
    assert {key(run) for run in attempts.values()} == targets, "Some original errors were never remeasured"
    assert reviewed_delivery == REVIEWED_DELIVERY_RETRIES, "The four explicit VROOM delivery reviews differ"
    # Recovered copies, including those archived before replacement, must be
    # identical to either the protected original or a registered fresh attempt.
    for run in recovered_observations:
        name = key(run)
        source = previous[name]
        if run["measuredAt"] > source["measuredAt"]:
            identity = (run["origin"]["cohortId"], name, run["measuredAt"])
            assert identity in attempts, "Recovered repair has no registered execution: " + name
            source = attempts[identity]
        assert without_recovery_metadata(run) == without_recovery_metadata(source), \
            "Recovered repair-series observation changed: " + name
    for name in targets:
        valid_seen = False
        ordered = sorted((run for run in attempts.values() if key(run) == name), key=lambda run: run["measuredAt"])
        for run in ordered:
            assert not valid_seen, "An already valid repair result was executed again: " + name
            valid_seen = run["valid"]

    checks = {key(check): check for check in proof["runs"]}
    assert len(checks) == len(proof["runs"]) and checks.keys() == current.keys(), "Audit observation coverage differs"
    for name, run in current.items():
        assert checks[name]["valid"], "Invalid audited observation: " + name
        same_constraints(run, previous[name])
        if name not in targets:
            assert run.get("origin"), "A protected observation was rerun: " + name
            assert without_recovery_metadata(run) == without_recovery_metadata(previous[name]), "Protected observation changed: " + name
        else:
            assert run["measuredAt"] > previous[name]["measuredAt"], "Target was not measured again: " + name
            marker = run["retryAttempt"]
            assert marker["finishedAt"], "Incomplete targeted retry: " + name
            if run.get("origin"):
                origin = run["origin"]
                evidence = report["originEvidence"][origin["reportSha256"]]
                source_bytes = (root / evidence["reportPath"]).read_bytes()
                assert sha(source_bytes) == origin["reportSha256"], "Repair origin report changed"
                source = json.loads(source_bytes)
                source_run = next(item for item in source["runs"] if key(item) == name)
                assert not source_run.get("origin"), "Repair origin is not an original measurement"
                # The run hash uses JavaScript's JSON encoding, and is independently checked by recovery.
                assert without_recovery_metadata(run) == without_recovery_metadata(source_run), "Recovered repair changed"
                assert marker["cohortId"] == source["cohortId"], "Repair marker belongs to another cohort"
            else:
                assert marker["cohortId"] == report["cohortId"], "Fresh repair marker belongs to another cohort"
            if run["valid"]:
                assert checks[name]["solutionValid"] and checks[name]["checkedCost"] == run["cost"]
                assert checks[name]["vehiclesUsed"] == run["usedVehicles"]

    baseline_manifest_bytes = baseline_path.with_name("manifest.json").read_bytes()
    assert sha(baseline_manifest_bytes) == baseline["manifestSha256"], "Original publication manifest changed"
    baseline_records, _, _ = published_records(root, json.loads(baseline_manifest_bytes))
    assert baseline_records.keys() == baseline["publishedMeasurements"].keys(), "Original published coverage differs"
    assert all(
        measurement_hash(record, baseline["measurementFields"]) == baseline["publishedMeasurements"][name]
        for name, record in baseline_records.items()
    ), "Original publication measurements differ from baseline"
    manifest = load(root / "manifest.json")
    current_records, total_valid, without_solution = published_records(root, manifest)
    assert current_records.keys() == baseline_records.keys(), "Published measurement coverage changed"
    allowed = {
        previous[name]["exampleId"] + "/" + str(previous[name]["budgetSeconds"]) + "/" + previous[name]["method"]
        for name in targets
    }
    changed = {
        name for name, record in current_records.items()
        if measurement_hash(record, baseline["measurementFields"]) != baseline["publishedMeasurements"][name]
    }
    assert changed <= allowed, "A protected published measurement changed: " + str(changed - allowed)
    assert changed == allowed, "Some repaired measurements were not exported"
    for name, record in current_records.items():
        if name not in allowed:
            assert without_recovery_metadata(record) == without_recovery_metadata(baseline_records[name]), \
                "Protected published record changed: " + name
    assert len(current_records) == 4773 and len(current_records) - len(allowed) == 4735, \
        "Protected published measurement count differs"
    return {
        "valid": True,
        "reportPath": latest["reportPath"],
        "reportSha256": sha(report_bytes),
        "baselineSha256": sha(baseline_path.read_bytes()),
        "repairSeriesSha256": sha(series_path.read_bytes()),
        "targetedExecutions": len(targets),
        "completedRepairAttempts": len(attempts),
        "repairAttemptsByCohort": series_counts,
        "protectedCatalogObservations": len(previous) - len(targets),
        "targetOutcomes": dict(Counter(current[name]["outcome"] for name in targets)),
        "remainingErrors": [
            {"runKey": name, "reason": current[name]["reason"]}
            for name in sorted(targets) if current[name]["outcome"] == "error"
        ],
        "scenarios": len(manifest["scenarios"]),
        "publishedMeasurements": len(current_records),
        "protectedPublishedMeasurements": len(current_records) - len(changed),
        "validRouteSets": total_valid,
        "scenariosWithoutValidRoutes": without_solution,
        "manifestSha256": sha((root / "manifest.json").read_bytes()),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args()
    data_root = Path(__file__).resolve().parent.parent
    check = progress if args.progress else audit
    print(json.dumps(check(data_root, args.baseline.resolve()), indent=2))
