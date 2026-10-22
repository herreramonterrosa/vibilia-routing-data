# Historical numeric measurements

This additive archive preserves the earlier comparison publication without replacing any current saved routes. The application continues to use the root `manifest.json` and `scenarios/`; it does not download this history while browsing examples.

## Contents

- `index.json` exposes the 544 additional measurements absent from the canonical baseline, including each complete original record, its budget, source suite and row location. The 13 relevant suite headers retain their protocol, original run count, environment and provenance. Original quarantine fields are preserved.
- `instance-comparisons.94a4c37e6df09764ba4c89c5f67f6afd37ebd92a20c2f720913d8d6d8c3191f8.json.gz` preserves the exact bytes of the entire earlier `instance-comparisons.json`. It contains all 21 suites, 15,941 record occurrences, 832 coverage entries and the historical CMT5 publication failure, including six execution hashes. Decompression restores all 39,966,885 bytes; the compressed archive is 1,669,550 bytes.

The numeric publication contained no route sequences. Its historical feasible flags describe those original observations; they do not add new validated route drawings to the current viewer. The seven quarantined measurements keep their original exclusion information. Nothing was recalculated or promoted into the canonical results.

## Coverage and identity

The original publication has 5,317 distinct measurement fingerprints. The baseline at commit `16bfd32a2c474242dbc4769232d8c92fdcbeb423` has 4,773, all represented in the archive. The difference is exactly 544: 51 feasible observations, 16 without a solution, 174 errors and 303 resource limits. Their budgets are 10 seconds (28), 30 seconds (104), and 60 seconds (412).

`index.json` documents the fingerprint fields. Missing optional fields compare as null, numbers compare exactly without rounding, and reason strings remain verbatim. This fingerprint only identifies additional observations; it does not imply equality of all metadata. The full compressed source therefore also preserves differing historical annotations, revalidation information and repeated records that are not in the 544-row index. `suiteIndex` and `recordIndex` are zero-based positions in that source.

The index retains the original suite headers, whose `runCount` describes the original suite rather than the number of additional rows listed here. Refer to `summary` for archive-specific counts. The root manifest and every current scenario file were unchanged when this history was published.

## Verify and recover

From the repository root, the following Python code verifies the downloaded archive before recovering the original JSON. It refuses to overwrite an existing recovery file.

```python
from pathlib import Path
import gzip, hashlib, json

index = json.loads(Path("history/index.json").read_text(encoding="utf-8"))
metadata = index["archive"]
compressed = Path("history", metadata["path"]).read_bytes()
assert len(compressed) == metadata["bytes"]
assert hashlib.sha256(compressed).hexdigest() == metadata["sha256"]
original = gzip.decompress(compressed)
assert len(original) == metadata["uncompressedBytes"]
assert hashlib.sha256(original).hexdigest() == metadata["uncompressedSha256"]
with Path("instance-comparisons.restored.json").open("xb") as output:
    output.write(original)
```

Future route exports may update the root manifest and scenarios independently. Preserve `history/`; its baseline commit and content hashes identify the original publication even after current results change.
