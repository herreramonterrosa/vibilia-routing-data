# Catalog error repair — 2026-10-23

This additive archive preserves the exact evidence for the repair of 38 technical errors: 20 VROOM, 15 jsprit, and 3 PyVRP observations. It does not replace the 2026-10-22 workspace snapshot or the earlier 544-measurement numeric archive. The SPA continues to load the root `manifest.json` and `scenarios/`.

## Scope and results

The final independent audit is `audit.json`, SHA-256 `186b634b34c42389aa8a3b1fbb256d09202411fd6c4a4c470f39cb76d591e38a`. It confirms that all 38 original errors were remeasured, the other 4,681 catalog observations were preserved, and no already-valid repair result was recalculated. Fleet, minimum nonempty route count, capacities, route bounds, service times, objective, rounding and original 60-second budgets were unchanged.

- Repaired observations now feasible: `14`.
- Completed within budget without a complete solution: `24`.
- Actual resource limits: `0`.
- Remaining technical errors: `0`.
- Total fresh repair attempts across the series: `46`.
- Final viewer export: `832` scenarios, `4773` measurements, `3627` valid route sets.

A deadline without a complete incumbent does not prove infeasibility. Incomplete or invalid routes are excluded from saved solution drawings.

## Evidence retained

The 6 registered cohorts are preserved under their original `benchmarks/catalog-comparison/` paths:

1. `catalog-2026-10-23-error-repair-dbe6ea58fb41cad6` — initial repair attempt. It was interrupted to address a remaining VROOM initialization deadline issue; its checkpoint and attempts remain evidence, including the historical active-run marker.
2. `catalog-2026-10-23-pyvrp-repair-fe5eb87edd34a97b` — PyVRP repair measurements.
3. `catalog-2026-10-23-vroom-deadline-a060e9c4b96a557c` — focused VROOM deadline measurement.
4. `catalog-2026-10-23-remaining-repair-c41de18a23393a50` — remaining targeted retries, retaining completed results through verified origins.
5. `catalog-2026-10-23-vroom-memory-repair-49a72024d7fa615f` — VROOM memory repair, included only after its exact report and audit hashes are registered in `repair-series.json`.

The archive also preserves the `repair-2026-10-23-baseline/` directory, the original baseline report and audit from `catalog-2026-10-21-second-pass-a38cd2c7548776b1`, the final `latest.json`, `execution.json` and `execution.log`, and the final independent repair audit. Source caches and unrelated benchmark directories are excluded. Origin report/audit copies already inside the registered cohorts remain byte-for-byte intact. Cohort discovery follows only the registry, with an explicit repair-label allowlist; an unregistered directory is never archived.

6. catalog-2026-10-23-vroom-memory-admission-d5a6e542696129a4 — final retry of XL-n6168 only, using concurrency admitted by actual free heap capacity. It ended within budget without a complete solution.

The initial four cohorts contain 42 finished attempts. The memory repair adds three attempts and the final admission repair adds one, totaling 46 over 38 distinct pairs. Every additional attempt followed an unsuccessful observation; no valid result was rerun. Two separate diagnostic reproductions of the still-failing XL-n6168 captured real heap-growth denial at the engine's 2 GiB maximum and are retained under the baseline directory.

Application source commits are 8fd3a9de1ccd4e4f4a57c98007582a1293b74fce, 4690802 and 3d6e1c0. VROOM now removes redundant immutable evaluation tables, compacts pending insertions and regulates concurrent searches using real heap capacity. jsprit avoids dense JSON copies and observes cooperative deadlines. PyVRP's pinned Pyodide runtime uses unsigned pointers for ASCII conversion above 2 GiB. Independent route validation and the original fleet/route constraints remain enforced.

The final export preserves all 4,773 measurements, with only the 38 targeted records updated. The other 4,735 published records retain their complete measurement contents; 3,627 route sets are valid. The number of examples without any saved valid route fell from 12 to 10. The earlier 544-measurement history and previous workspace archive remain unchanged.

## Integrity and recovery

`manifest.json` lists `28515` original files totaling `3850250850` bytes, with each original path, byte length and SHA-256. `87` archives total `400039264` bytes. Every compressed part is at most 25 MiB and has its own SHA-256. Creation verifies every archived member against its original file before publishing the directory.

From the data repository root, verify without restoring:

```sh
python3 tools/restore-benchmark-workspace.py --manifest history/benchmark-workspace/2026-10-23-error-repair/manifest.json --verify-only
```

Restore only this evidence into an empty workspace directory:

```sh
python3 tools/restore-benchmark-workspace.py --manifest history/benchmark-workspace/2026-10-23-error-repair/manifest.json --destination /absolute/path/to/repair-workspace
```

The existing restore tool rejects conflicting destination files, unsafe paths, duplicate members, and checksum mismatches. Use the earlier workspace snapshot when restoring shared source caches for a full rerun. No measurements are executed during archival or restoration.

The exact final comparison publication is also preserved as a verified compressed file indexed by [comparison-publication.json](comparison-publication.json). Its original 120,894,980-byte JSON exceeds GitHub's individual-file limit. Decompression restores the original bytes and SHA-256; it does not replace the root saved-route dataset. Future full publications remain in the ignored comparisons workspace.
