# DEXA pipeline split review

## Shortcuts

- I moved the two chart implementations without redesigning their style. The later chart-styling task can work from `src/dexa/charts.py` without also untangling report logic.
- The tracked renderer is data-only for every scan. I kept the former 2026-08-21 report only under ignored `.artifacts/` for local comparison.
- The direct script adds `src` to `sys.path`. This keeps `python scripts/analyze_dexa.py` working before or without an editable install. Normal package imports still follow the repository's `src` layout.

## Issues found

- The old `main()` upserted the 2026-08-21 total and regional payloads every time it generated a report. A report run could therefore rewrite its own inputs.
- The old module mixed CSV mutation, calculations, plotting, report rendering, repository paths, and console output. Testing a calculation imported all of those concerns.
- The prose after the regional table contains measurements that are absent from both CSVs. It is valid for the current 2026-08-21 report, but it cannot describe an arbitrary future scan correctly until ingestion captures those fields.
- The first split left that prose in the normal template, so a future scan would have inherited stale BF, FFMI, BMI, VAT, BMD, symmetry, cut, and recommendation claims. The renderer now omits every claim that the CSV inputs cannot support.
- The lean-mass chart footer said `1 TO 9` even when the input contained a different number of scans.

## Ambiguities

- "DEXA ingestion" could mean either reading the analysis CSVs or importing a new scan into them. I treated ingestion here as validated, read-only loading. I removed the embedded scan import because the task requires normal analysis to avoid mutation. A future import command can own scan writes explicitly.
- "Preserve current results" could require identical pixels or only matching measurements. I compared SHA-256 hashes and decoded pixel arrays. Both seeded charts match exactly in the current environment.

## Judgment calls

- `src/dexa/ingestion.py` owns CSV reads and required-column checks.
- `src/dexa/calculations.py` owns DataFrame-to-result calculations and performs no file operations.
- `src/dexa/charts.py` owns both chart writers and receives output paths from its caller.
- `src/dexa/report.py` turns an analysis result into a string and performs no file operations.
- `src/dexa/pipeline.py` is the only package module that coordinates reads and writes. It never writes either input path.
- The Markdown filename now derives its date from the latest scan. For the seeded data it remains `dexa-analysis-2026-08-21.md`. Both PNG names are unchanged.
- The script re-exports the three previously tested calculation functions so existing imports from `scripts.analyze_dexa` keep working.
- Values present in `DexaAnalysis`, including body fat, FFMI, BMI, interval changes, regional changes, and current mass, always come from the loaded data.
- No personal supplemental measurements or recommendations are committed as source defaults. Current and future scans use the same neutral report path.
- The chart footer derives its final sequence number from `len(points)`.
- The CLI warns on stderr that report outputs may contain personal health data.
- Local image comparisons live under ignored `.artifacts/dexa-pipeline-split/`. They do not mix with deliberate files already tracked under `outputs/`.

## Rejected alternatives

- I did not keep the dated payload behind a default-on flag. That would leave mutation in the normal report path.
- I did not put `dexa` at the repository root. The integration packaging work uses `package-dir = src`, so a root package would be absent from editable installs.
- I did not create a generic upsert API without a current caller. Explicit scan import deserves its own command, validation, and tests.
- I did not commit a date-keyed supplemental context. Even an exact-date map would preserve personal VAT, BMD, limb, and recommendation data in tracked source.
- I did not ignore `outputs/` wholesale. The repository has deliberate analysis artifacts there.

## Commands run

```text
PYTHONPATH=src MPLBACKEND=Agg python -m unittest tests.test_analyze_dexa -v
# 11 tests passed

PYTHONPATH=src MPLBACKEND=Agg python -m unittest discover -s tests -v
# 24 tests passed

MPLBACKEND=Agg python scripts/analyze_dexa.py --output-dir <temporary-directory>
# Wrote the Markdown report and both PNG charts

shasum -a 256 .artifacts/dexa-pipeline-split/{before,after}/dexa-analysis-2026-08-21.md data/dexa.csv data/dexa_regions.csv
# Former rich Markdown: 1d56b55af165e7c689a8555b110032188ec38d3a48eb89ce8b2b5f516d9592b1
# Data-only Markdown: cb17e97756540c57c5fc8277de368d288501f0dc42540e25e447fac6530ca6c8
# totals input: ddcb6e5155aa6beffa66fab3eaa8c00aa9a77bccc564440bbfd9728cd1b003df
# regions input: 6d543783580f2a697812de05630c0bbc44fe6114668c177ec480a3b7deecf27b

shasum -a 256 .artifacts/dexa-pipeline-split/{before,after}/*.png
# Composition before and after: 26fa592894aa6f745dd2909713fa1dcd5ae2b248a4b0a4320fc4bc089a5dee65
# Lean-mass before and after: 7d1b47ff209af71fde3c1e543baf66d622b0757803851404d0c43607d4a192da

# Decoded with matplotlib.image.imread and compared with numpy.
# Both images: pixels_equal=True, max_delta=0.0
```

## Edge cases

- Analysis rejects fewer than two total-body scans.
- Analysis rejects a region present in the latest scan but absent from the previous scan.
- CSV ingestion reports missing required columns with the source path and column names.
- Equal-weight intervals remain `BASELINE` with no efficiency, matching the previous calculation.
- A zero total-weight change between the latest scans leaves the calculation's fat-share value undefined. The renderer does not use fat share and describes unchanged mass directly.
- Every scan omits VAT, total BMD, A/G ratio, side-specific symmetry, demographic ranking, cut assessment, and recommendations because the CSVs do not provide enough data for those claims.
- Report prose describes weight, fat, and lean changes by direction. It does not assume every interval is a cut.

## Output compatibility notes

- The seeded data-only Markdown keeps the calculated metric table and output filename. It intentionally removes the richer personal interpretation. The former report remains only in ignored `.artifacts/` for local comparison.
- Seeded chart hashes match before and after the footer fix. Decoded RGBA arrays are pixel-identical with a maximum channel delta of 0.0.
- Output names remain `dexa-analysis-2026-08-21.md`, `dexa-composition-history.png`, and `dexa-lean-mass-vs-bodyweight.png` for the seeded data.
- The CLI no longer prints misleading `Updated` messages for the two source CSVs. It only lists files it wrote.
- Generated outputs, comparison artifacts, and ignored personal CSVs are not part of the commit.
- Markdown reports, charts, and comparison artifacts may contain personal health data. The CLI prints this warning before generation. `.artifacts/` is ignored, but users must still choose output locations and sharing permissions carefully.

## Next steps

- Apply the planned shared chart styling inside `src/dexa/charts.py` while keeping its path-based interface.
- Define an explicit scan-import command if new scans should be added from PDFs or structured payloads.
- If richer reports return, load supplemental health measurements from an explicit ignored input rather than tracked defaults.
