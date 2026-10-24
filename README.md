# vibilia-routing-data

This is a static data repository for the instance explorer. It contains saved, independently audited routes and the geometry needed to draw them, with separate historical evidence archives. The route dataset contains no solver binaries, dense cost matrices, or credentials.

The application requests `manifest.json` once, then only the chosen example's `scenarios/<example-id>.<sha256>.json`. The SHA-256 in the manifest verifies the exact response bytes. A scenario contains coordinates, source node IDs, demands, service times, time windows and route bounds, plus each measured method's status, original cost, fleet, actual elapsed time, time budget and measurement provenance. Coordinate-free instances use an explicitly schematic layout. Non-solutions have empty routes and retain their failure status; they do not imply mathematical infeasibility.

## Application on Netlify, data on GitHub

The application remains deployed on Netlify. This public repository only stores data files; it does not deploy a website or require GitHub Pages. The application fetches the selected scenario from GitHub's raw file URLs using this base:

```dotenv
VITE_INSTANCE_RESULTS_BASE_URL=https://raw.githubusercontent.com/herreramonterrosa/vibilia-routing-data/main/
```

Keep `manifest.json` and `scenarios/` at the repository root. A push to `main` makes the new manifest and scenarios available, subject to HTTP cache refresh. Updating only the data does not require rebuilding the application. If a deployment must use one fixed snapshot, replace `main` in the URL with the data repository's full commit SHA and rebuild that app deployment.

Public reads need no GitHub API token. Do not put a private repository token in the SPA. Another static host/CDN with CORS enabled can also serve this same file layout. Prefer a short cache lifetime for `manifest.json` and a long immutable lifetime for content-hashed scenario files when the host permits cache configuration.

## Update without rerunning solvers

Keep this checkout beside the application, each with its own Git history:

```text
projects/
  vibilia-routing/
  vibilia-routing-data/
```

From `vibilia-routing/`, use Node 24 or newer and run:

```sh
pnpm export:instance-solutions
git -C ../vibilia-routing-data status --short
git -C ../vibilia-routing-data add README.md .gitignore manifest.json scenarios
git -C ../vibilia-routing-data commit -m "Update saved routing solutions"
git -C ../vibilia-routing-data push origin main
```

The default export destination is this sibling checkout. Set `VIBILIA_ROUTING_DATA_DIR` to use a different data checkout, including its raw workspace. An explicit `--output` may select another external directory; writing result copies inside the application is rejected, including symbolic-link aliases. The export reads the latest completed audited catalog report from the data checkout's `benchmarks/` workspace, verifies its source and recovery provenance, rechecks stored routes against original constraints and costs, and adds distinct historical measured budgets. It does not run a solver. It writes content-hashed scenario files first and replaces the manifest last. Existing unchanged files are reused; older hashed files are retained so cached manifests continue to resolve. Publish the new manifest and its referenced files together.

Later exports preserve existing `README.md`, `.gitignore` and `history/` contents. Generated publications from the older scripts go to `comparisons/catalog.json` and `comparisons/route-limits.json`, separate from the current routes and historical archive. These generated files remain ignored because a full catalog publication can exceed GitHub's single-file limit. Preserve selected publications as verified compressed historical releases. The application does not fetch them during normal browsing.

Raw benchmark reports, audits and cached sources belong to the ignored `benchmarks/` workspace in this checkout. A lossless archive under `history/benchmark-workspace/` preserves those files with their original paths and SHA-256 hashes, without adding thousands of unpacked generated JSON files to Git. Restore that workspace before exporting from a fresh checkout; the application's route viewer does not need it.

Time measurements retain the original protocol: the recorded solve budget includes preparation, worker/runtime and engine initialization, search and runner validation. Source download/import, matrix construction before the measured solve and the independent audit are outside that historical clock. Do not describe these single measurements as repeatable guarantees or as the speed of the viewer's device. Methods measured under different builds remain explicitly identified by their provenance.

The source SHA-256 and original reference URLs are preserved with each observation. Third-party benchmark instances and references retain their original attribution and terms; this export does not relicense them.

## Historical measurements

An independent [historical archive](history/README.md) preserves 544 additional numeric measurements and a lossless compressed copy of the earlier comparison publication. It retains original budgets, outcomes, quarantine information and provenance. It does not replace the root manifest or current saved routes, and the application does not fetch it during normal browsing.

## Benchmark workspace archive

Legacy reports, checkpoints and audit evidence are preserved byte for byte in [history/benchmark-workspace](history/benchmark-workspace/README.md). The application writes future benchmark outputs directly into this checkout; raw work files are ignored, and viewer exports remain versioned in manifest.json and scenarios/.
