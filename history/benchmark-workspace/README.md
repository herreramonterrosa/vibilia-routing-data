# Benchmark workspace archive

The 2026-10-22 snapshot preserves 17,582 original files (743,936,924 bytes), including raw solver results, resumable catalog checkpoints, source caches and previous audit evidence. Twenty compressed archives total 86,237,634 bytes. The per-file manifest records every original path, length and SHA-256; each archive has its own SHA-256. Current manifest.json, scenarios/ and the earlier 544-measurement history were not replaced.

Verify from the repository root:

```sh
python3 tools/restore-benchmark-workspace.py --verify-only
```

Restore raw working files into this data checkout:

```sh
python3 tools/restore-benchmark-workspace.py
```

Existing identical files are preserved. A conflicting existing file stops restoration before any writes. Archives contain regular files only; traversal and symlink escapes are rejected. The app defaults to this sibling checkout, or the VIBILIA_ROUTING_DATA_DIR environment variable. Raw work files stay out of app Git and are ignored here; publish new viewer exports with the app export command and commit the manifest/scenarios changes here. The snapshot is independent from the routes loaded by the SPA.
