# DEXA pipeline split review

## Shortcuts

- I moved the two chart implementations without redesigning their style. The later chart-styling task can work from `src/dexa/charts.py` without also untangling report logic.
- I kept the long-form, scan-specific interpretation in the report template. The CSVs do not contain VAT, BMD, A/G ratio, or left/right limb measurements, so deriving that prose would require a new data format and would change the report.
- The direct script adds `src` to `sys.path`. This keeps `python scripts/analyze_dexa.py` working before or without an editable install. Normal package imports still follow the repository's `src` layout.

## Issues found

- The old `main()` upserted the 2026-08-21 total and regional payloads every time it generated a report. A report run could therefore rewrite its own inputs.
- The old module mixed CSV mutation, calculations, plotting, report rendering, repository paths, and console output. Testing a calculation imported all of those concerns.
- The prose after the regional table contains measurements that are absent from both CSVs. It is valid for the current 2026-08-21 report, but it cannot describe an arbitrary future scan correctly until ingestion captures those fields.

## Ambiguities

- "DEXA ingestion" could mean either reading the analysis CSVs or importing a new scan into them. I treated ingestion here as validated, read-only loading. I removed the embedded scan import because the task requires normal analysis to avoid mutation. A future import command can own scan writes explicitly.
- "Preserve current results" could require byte-identical images or only matching measurements. The seeded run produced the same Markdown SHA-256 and the same chart byte sizes as the baseline, so this implementation meets the stricter interpretation for the current environment.

## Judgment calls

- `src/dexa/ingestion.py` owns CSV reads and required-column checks.
- `src/dexa/calculations.py` owns DataFrame-to-result calculations and performs no file operations.
- `src/dexa/charts.py` owns both chart writers and receives output paths from its caller.
- `src/dexa/report.py` turns an analysis result into a string and performs no file operations.
- `src/dexa/pipeline.py` is the only package module that coordinates reads and writes. It never writes either input path.
- The Markdown filename now derives its date from the latest scan. For the seeded data it remains `dexa-analysis-2026-08-21.md`. Both PNG names are unchanged.
- The script re-exports the three previously tested calculation functions so existing imports from `scripts.analyze_dexa` keep working.

## Rejected alternatives

- I did not keep the dated payload behind a default-on flag. That would leave mutation in the normal report path.
- I did not put `dexa` at the repository root. The integration packaging work uses `package-dir = src`, so a root package would be absent from editable installs.
- I did not create a generic upsert API without a current caller. Explicit scan import deserves its own command, validation, and tests.
- I did not rewrite the report's medical interpretation. That would exceed a pipeline-separation task and risk changing the current result.

## Commands run

```text
PYTHONPATH=src MPLBACKEND=Agg python -m unittest tests.test_analyze_dexa -v
# 7 tests passed

MPLBACKEND=Agg python scripts/analyze_dexa.py --output-dir <temporary-directory>
# Wrote the Markdown report and both PNG charts

shasum -a 256 <temporary-directory>/dexa-analysis-2026-08-21.md data/dexa.csv data/dexa_regions.csv
# Markdown: 1d56b55af165e7c689a8555b110032188ec38d3a48eb89ce8b2b5f516d9592b1
# totals input: ddcb6e5155aa6beffa66fab3eaa8c00aa9a77bccc564440bbfd9728cd1b003df
# regions input: 6d543783580f2a697812de05630c0bbc44fe6114668c177ec480a3b7deecf27b
```

## Edge cases

- Analysis rejects fewer than two total-body scans.
- Analysis rejects a region present in the latest scan but absent from the previous scan.
- CSV ingestion reports missing required columns with the source path and column names.
- Equal-weight intervals remain `BASELINE` with no efficiency, matching the previous calculation.
- A zero total-weight change between the latest scans leaves fat-share undefined. The current report is a cut, so this case remains outside the report wording rather than inventing a percentage.

## Output compatibility notes

- The seeded Markdown is byte-identical to the baseline and retains its 5,838-byte size.
- The seeded composition chart remains 172,369 bytes and the lean-mass chart remains 506,783 bytes in the current environment.
- Output names remain `dexa-analysis-2026-08-21.md`, `dexa-composition-history.png`, and `dexa-lean-mass-vs-bodyweight.png` for the seeded data.
- The CLI no longer prints misleading `Updated` messages for the two source CSVs. It only lists files it wrote.
- Generated outputs and ignored personal CSVs are not part of the commit.

## Next steps

- Apply the planned shared chart styling inside `src/dexa/charts.py` while keeping its path-based interface.
- Define an explicit scan-import command if new scans should be added from PDFs or structured payloads.
- Extend the source schema for VAT, BMD, A/G ratio, and limb-side measurements, then make the remaining report interpretation data-driven.
