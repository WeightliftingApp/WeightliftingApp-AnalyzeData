# Integration review

This branch, `codex/forecast-style-review`, sits on top of
`integrated-low-risk-upgrades` and carries five previously separate projects
plus the work described here. Read this before merging anything.

**Do not merge this branch blindly.** The primary checkout at
`~/Desktop/Repos/WeightliftingApp-AnalyzeData` is dirty: 38 entries in
`git status --porcelain`. Five are modifications to tracked files:
`.gitignore`, `README.md`, `src/analysis_utils.py`,
`src/analyze_bodyweight_strength_evals.ipynb`, and
`tests/test_analysis_utils.py`. Of the 33 untracked entries, 26 are generated
files under `outputs/`. The other seven are source: `scripts/analyze_dexa.py`,
`src/analyze_training_program.ipynb`, `src/analyze_training_program.py`,
`src/generate_bench_frontier_update.py`, `src/training_program_analysis.py`,
`tests/test_analyze_dexa.py`, and `tests/test_training_program_analysis.py`.

Seven of those paths are also changed by this branch, so merging without
reconciling them will collide or silently discard work:

| path | primary checkout | this branch |
|---|---|---|
| `.gitignore` | modified | modified |
| `README.md` | modified | modified |
| `src/analysis_utils.py` | modified | modified |
| `tests/test_analysis_utils.py` | modified | modified |
| `scripts/analyze_dexa.py` | untracked | added |
| `src/generate_bench_frontier_update.py` | untracked | added |
| `tests/test_analyze_dexa.py` | untracked | added |

The three untracked-versus-added rows are the sharp ones. The primary checkout
holds its own copy of each file, and a merge will not warn about them the way
it warns about a conflict.

Four untracked paths exist only in the primary checkout and are unrelated to
this branch: the three `training_program` source files and their test. Nothing
here touches them.

Reconcile all of this by hand before merging, and do not run `git checkout` or
`git restore` against that checkout.

## What each project contributes

Project numbers are the ones assigned to the work, not the order it was
integrated. Projects 4 and 5 are not part of this branch and this ledger does
not cover them.

### 1. Bulk ceiling forecaster (`docs/agent-reviews/bulk-ceiling-forecaster.md`)

Adds `src/dexa/forecast.py` and its pipeline, report, and chart, plus
`scripts/forecast_bulk_ceiling.py`. Simulates the bodyweight at which a target
DEXA body-fat reading is reached, with a seeded bootstrap, nested 80% and 95%
prediction bands, a one-sided safety ceiling, and a held-out predictive score.

### 2. Packaging and CI foundation (`docs/agent-reviews/repo-foundation.md`)

Replaces `requirements.txt` with a `pyproject.toml` that declares
`weightlifting-app-analysis`, sets `requires-python >= 3.10`, and splits
`dev` and `notebooks` extras. Adds a GitHub Actions workflow and moves the
suite from `unittest` discovery to `pytest`. This landed first, and every
other project depends on `pip install -e ".[dev]"` working.

### 3. Canonical dataset (`docs/agent-reviews/canonical-dataset.md`)

Adds `src/training_dataset.py`, which flattens a `.wld` export into workout,
exercise, and set DataFrames with pinned dtypes and explicit null semantics.
Documented in `docs/training-dataset.md`. This is the one project a notebook
author touches directly.

### 6. DEXA pipeline split (`docs/agent-reviews/dexa-pipeline-split.md`)

Breaks the single DEXA script into `dexa.ingestion`, `dexa.calculations`,
`dexa.charts`, `dexa.report`, and `dexa.pipeline`. The renderer stopped
writing back to its own inputs, and the report filename now derives from the
latest scan rather than a hardcoded date.

### 7. Shared chart style (`docs/agent-reviews/shared-chart-style.md`)

Adds `src/chart_style.py` (palette, frames, canvas, header, axes, footer,
save), `docs/chart-style.md`, the `weightlifting-chart-style` skill, and
`scripts/compare_charts.py`. Migrates the DEXA topography card and the bench
Pareto card onto the shared frame.

### This pass

Three things. It migrates the forecast chart onto the shared visual system.
It fixes the chart regression gate, which was reporting a regression that did
not happen. It removes real body-composition measurements from tracked test
fixtures.

## The regression gate was measuring the wrong thing

The reported symptom was that `scripts/compare_charts.py --generate` failed on
Python 3.14 with DEXA at 3.53% and bench at 2.13% changed pixels against a 1%
gate, while side-by-side inspection showed matching dimensions and no lost
information.

I decomposed it by rendering the pre-refactor generators, unchanged, under two
Matplotlib versions. The baselines record `Matplotlib version3.10.0` in their
PNG `Software` chunk; the repository now resolves Matplotlib 3.11.1.

| what was compared | Matplotlib | changed-pixel fraction |
|---|---|---|
| pre-refactor code vs its own baseline | 3.10.0 both sides | 0.000000 |
| migrated code vs baseline, DEXA | 3.10.0 both sides | 0.000548 |
| migrated code vs baseline, bench | 3.10.0 both sides | 0.000000 |
| pre-refactor code vs baseline, DEXA | 3.10.0 to 3.11.1 | 0.035192 |
| migrated code vs baseline, DEXA | 3.10.0 to 3.11.1 | 0.035209 |
| migrated code vs baseline, bench | 3.10.0 to 3.11.1 | 0.021284 |

Under Matplotlib 3.10.0 the pre-refactor code reproduces its baseline pixel
for pixel, and the migrated bench card does too. Matplotlib 3.11 ships
FreeType 2.14.3 where 3.10 shipped 2.6.1, which shifts glyph advances by a
fraction of a pixel. Those fractions accumulate along a string, so every
monospace label on a text-heavy editorial card re-flows by a few pixels. The
diff image shows the drift confined to text, with the trend lines, contours,
scan points, and residual bars untouched.

So the migration moved 0.05% of the DEXA card and none of the bench card. The
other 3.5% was the renderer.

The fix makes the gate say which question it can answer:

- Both PNGs name the same renderer: the changed-pixel fraction is a fidelity
  signal, and the strict `0.01` threshold applies unchanged.
- The renderers differ, or either PNG does not name one: only a `0.15`
  gross-change ceiling applies, and the run refuses to certify. It exits
  non-zero with a message naming both renderers, and
  `--accept-renderer-drift` records a reviewer overriding it in the JSON
  report.

Dimensions are gated in both modes. The `0.15` ceiling is four times the
largest typographic drift measured here, so it still catches a blank canvas,
the wrong chart, or an inverted palette, and the report says plainly that it
proves nothing about whether a label survived.

## Judgment calls

**Two unknown renderers are not a match.** An earlier draft let
`None == None` fall through to the strict gate. Absent metadata is not
evidence of a shared renderer, so unknown now routes to the cross-renderer
path. The three original pixel-gate fixtures in `tests/test_compare_charts.py`
were restamped with a matching renderer so they keep exercising the strict
threshold they were written for.

**A new palette field rather than an overloaded one.** The forecast chart
draws a constant fat-free-mass reference line beside the modeled series. No
existing palette entry means that; `PALETTE.latest` is documented as the
latest DEXA scan. I added `PALETTE.reference` (`#ea580c`) rather than reuse a
color that already carries a different meaning. The target and safety
confidence lines use `PALETTE.negative`, the palette's warning red, and the
modeled median, bands, and safety ceiling use `PALETTE.frontier`.

**A stacked canvas rather than a second y axis.** `chart_canvas` yields one
axes. Preserving both forecast panels needed either a two-panel helper or a
hand-built figure that bypasses the shared frame. I added `stacked_canvas` to
`src/chart_style.py`, which reuses the same rc context and facecolors and
returns a tuple of axes. It is the only new abstraction in this pass.

**Reused `PARETO_AXES` rather than a third axis preset.** The forecast needs
`axis_below=True` so the grid sits under the filled bands, which rules out
`TOPOGRAPHY_AXES`. `PARETO_AXES` already has it. Tick size drops from 10.5 to
9.5, which is not in the preserved list and makes the three cards more
consistent.

**Header metadata split across two rows.** The original subtitle carried the
interval count, the resampling unit count, and the anchor scan date in one
sentence. Putting all three in one right-aligned metadata row collided with
the title at a two-decimal target such as 22.5%. Splitting them across the two
rows the frame already provides keeps every number and clears the title.

**Footer compacted to fit one row.** `add_footer` puts the model note and the
reading key on one line. The original bottom text was a single left-aligned
sentence, so it had the full width. Moving "modeled estimates, not
measurements" to the reading key on the right, shortening
`SPARSE: n RESAMPLING UNITS` to `SPARSE: n UNITS` (the header metadata already
names them as resampling units), and using `DRAWS` for the simulation count
(the word `--simulations` uses in its own help text) leaves a 238 px gap at the
widest note the generator can produce, against a 40 px floor.

**Synthetic replacements chosen to keep closed forms exact.** The test
fixtures that held real scans now use 200/220/210 lb with 180/187/184.8 lb
fat-free, which give exactly 10%, 15%, and 12% body fat, and 180/0.8 = 225 lb
for the constant fat-free-mass ceiling. Round numbers make the arithmetic
checkable by eye.

## Rejected alternatives

- **Regenerate the baselines.** This would make the gate green while erasing
  the pre-refactor evidence, which is the whole point of keeping them.
- **Pin Matplotlib to 3.10.** It does not import on Python 3.14 (deep-copy
  recursion in `matplotlib`), it freezes the repository on an old release, and
  it avoids the question instead of answering it.
- **Loosen the threshold to 0.05.** The number would have no justification, it
  would hide a real 4% regression under a matched renderer, and it would still
  be wrong for a card with more or less text than these two.
- **A displacement-tolerant pixel metric.** I built and measured one: for each
  pixel, count it changed only when no value within a radius of the other
  image explains it. Residual drift for the identical-code renderer change was
  0.0235 at radius 1, 0.0137 at radius 2, 0.0092 at radius 3, and 0.0068 at
  radius 4. Long strings shift by more than any defensible radius, so there is
  no principled threshold. Dropped as false precision.
- **Simulating a million draws in the layout test.** The first version took
  19 seconds. The test now builds a small forecast and uses
  `dataclasses.replace` on its assumptions to widen the footer string, which
  measures the same text in 0.1 seconds.
- **Rewriting the older review docs to use `.venv`.** Those commands record
  what was actually run at the time. I added a note saying what supersedes
  them instead of falsifying the record.

## Shortcuts

- The bench Pareto baseline cannot be reproduced under Matplotlib 3.10 from
  git history: `src/generate_bench_frontier_update.py` first appears in the
  same commit that introduced the shared style, so there is no pre-refactor
  source to rerun. Its 0.000000 strict-mode reading is against the migrated
  code, not against a reconstructed original.
- I did not migrate `plot_composition_history`. It keeps its dark theme and is
  out of scope for this pass, exactly as the shared-chart-style review left it.
- I did not touch the notebooks.
- I did not run the skill evaluation suite in `skills/weightlifting-chart-style/evals/`.

## Issues found

- `scripts/convert_weight_xlsx.py` and `scripts/convert_dexa_xlsx.py` hardcode
  absolute paths under `/Users/chappyasel/`. Both predate this integration, so
  I left them alone. They will not run on any other machine.
- `docs/agent-reviews/dexa-pipeline-split.md` mentions the `2026-08-21` scan
  date several times, in output filenames that genuinely contain it. Removing
  those would make the document wrong. The baseline directory name
  `.artifacts/chart-baselines/2026-08-21-pre-shared-style` has the same
  property.
- Reading the DEXA weight log emits two `openpyxl` warnings about unsupported
  workbook extensions. Both generators complete and neither saves the workbook.

## Ambiguities

- The project numbering (1, 2, 3, 6, 7) comes from outside this repository, so
  nothing in the git history confirms it. The mapping used here is the assigned
  project list: 1 bulk ceiling forecaster, 2 packaging and CI foundation, 3
  canonical dataset, 6 DEXA pipeline split, 7 shared chart style. Projects 4
  and 5 are not on this branch and nothing here changes them.
- "Preserve output dimensions unless a documented reason requires otherwise"
  left font sizes open. I read dimensions as canvas size and DPI, both
  preserved at 2200 by 1800 and 200. Tick, metadata, and footer sizes moved.
- The AGENTS instructions arrived in the session rather than as a tracked
  `AGENTS.md`, so a later reader of this repository will not find that file. I
  followed the supplied instructions together with `CLAUDE.md` at the
  repository root.

## Files changed in this pass

| file | change |
|---|---|
| `src/chart_style.py` | added `PALETTE.reference`, `FORECAST_FRAME`, `EDITORIAL_RC`, `stacked_canvas` |
| `src/dexa/forecast_charts.py` | migrated to the shared frame, palette, fonts, and save helper |
| `scripts/compare_charts.py` | renderer detection, two gate modes, `--accept-renderer-drift` |
| `tests/test_chart_semantics.py` | six forecast semantic tests, three forecast layout tests |
| `tests/test_compare_charts.py` | eleven new tests for renderer detection and both gate modes, three existing fixtures restamped |
| `tests/test_forecast_bulk_ceiling.py` | real scan values replaced with synthetic ones |
| `tests/test_analyze_dexa.py` | real scan rows replaced with synthetic ones |
| `docs/chart-style.md` | forecast reference, `stacked_canvas`, the two gate modes |
| `skills/weightlifting-chart-style/SKILL.md` | same, plus footer layout guidance |
| `README.md` | `source venv` corrected to `source .venv`, example bodyweight generalized |
| `docs/agent-reviews/canonical-dataset.md` | absolute personal path removed |
| `docs/agent-reviews/bulk-ceiling-forecaster.md` | note that `requirements.txt` is gone |

## Automated checks and outcomes

Run from the worktree root with `.venv` built by
`python3 -m venv .venv && python -m pip install -e ".[dev]"`, on Python 3.14.5
with Matplotlib 3.11.1, NumPy 2.5.2, pandas 3.0.5, and Pillow 12.3.0.

```bash
.venv/bin/python -m pytest -q
# 207 passed, 46 subtests passed

git diff --check
# exit 0, no whitespace errors

PYTHONPATH=src:. .venv/bin/python scripts/compare_charts.py --generate
# exit 1, by design: cross-renderer, matplotlib 3.10.0 -> matplotlib 3.11.1
#   dexa  0.035209   bench 0.021284   both under the 0.15 gross-change ceiling
#   dimensions match on both

PYTHONPATH=src:. .venv/bin/python scripts/compare_charts.py --accept-renderer-drift
# exit 0, accepted_renderer_drift: true recorded in the JSON report

.venv/bin/python scripts/analyze_dexa.py --output-dir .artifacts/smoke-dexa
# wrote the Markdown report and both PNGs

.venv/bin/python scripts/forecast_bulk_ceiling.py --output-dir .artifacts/smoke-forecast \
  --target-body-fat-pct 18 --simulations 2000 \
  --current-bodyweight-lb 216 --weekly-bulk-rate-lb 0.5
# wrote the report, the probability curve CSV, and a 2200x1800 chart
```

The strict path was verified separately in a throwaway Python 3.13 environment
with Matplotlib 3.10.0, which is the renderer the baselines record:

```
matplotlib 3.10.0 -> matplotlib 3.10.0   mode strict
  dexa-lean-mass-vs-bodyweight.png        0.000548   under the 0.01 gate
  bench-strength-eval-update-2026-08-21   0.000000   under the 0.01 gate
```

`tests/test_chart_semantics.py` passes under both renderers, 12 tests each,
which matters because the layout tests measure rendered text extents.

Source CSVs were not modified. SHA-256 hashes of `data/dexa.csv` and
`data/dexa_regions.csv` matched before and after every run, and
`git status --porcelain data/` reports nothing. The hash values stay in the
ignored run artifacts rather than in this tracked document, since they
fingerprint private data.

## Manual review steps

1. Build the environment and run the suite:
   `python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]" && .venv/bin/python -m pytest`.
2. Generate the forecast card into an ignored directory and look at it:
   `.venv/bin/python scripts/forecast_bulk_ceiling.py --output-dir .artifacts/forecast-review`.
   Check that it is 2200 by 1800, that both panels are present, that the 80%
   band nests inside the 95% band, that the target line, the current scan dot,
   the constant fat-free-mass line, and the safety ceiling are all labelled,
   and that the two footer columns do not touch.
3. Run `PYTHONPATH=src:. .venv/bin/python scripts/compare_charts.py --generate`
   and read the message. It should name both renderers and refuse to certify.
4. Open the contact sheets and diffs under `.artifacts/chart-comparisons`. The
   diff images should show drift on text only, with the marks clean.
5. Confirm nothing under `.artifacts/` or `data/` is staged:
   `git status --short`.

## Edge cases covered

- A forecast whose safety ceiling is not identified below the weight cap
  states it in an annotation instead of drawing a line.
- A forecast whose constant fat-free-mass ceiling sits above the cap drops
  that reference line from both panels.
- A sparse record adds the `SPARSE: n UNITS` warning to the model footer; a
  denser one omits it.
- A two-decimal body-fat target (22.5%) keeps the title clear of the metadata
  column and keeps the lower y-axis label inside its own panel.
- A ten-digit seed beside a seven-figure draw count still leaves 238 px
  between the two footer columns.
- A PNG with no `Software` chunk is treated as an unknown renderer, not as a
  match.
- A dimension change fails the gate in both modes, including with
  `--accept-renderer-drift`.

## Rollback

The whole pass is one commit on `codex/forecast-style-review`. `git revert` it
to restore the bespoke forecast styling, the unconditional 1% gate, and the
previous test fixtures. Nothing outside the repository changed, no CSV was
written, and everything generated during review lives under ignored
`.artifacts/`, which can be deleted.

To roll back only the gate change while keeping the chart migration, revert
`scripts/compare_charts.py` and `tests/test_compare_charts.py`. The two are
independent.

## Known limits

- The strict path cannot run on Python 3.14, because Matplotlib 3.10 does not
  import there. Anyone who needs a certified comparison needs Python 3.13 or
  older with `matplotlib==3.10.0`.
- The `0.15` gross-change ceiling is calibrated on two cards from one
  Matplotlib upgrade. A future upgrade with larger metric changes, or a card
  with far more text, could exceed it without anything being wrong.
- The layout tests assert against DejaVu Sans Mono metrics. They pass on
  FreeType 2.6.1 and 2.14.3 with a wide margin, but a font substitution would
  change the numbers.
- `--accept-renderer-drift` is an honour system. It records the override in
  the JSON report; it cannot tell whether anyone looked at the sheets.
- The forecast chart has no preserved baseline, so it has no pixel comparison
  at all. Its semantic and layout tests are the only automated coverage.

## Next steps

1. Reconcile the dirty primary checkout before merging.
2. Consider capturing a forecast-card baseline once the chart settles, so it
   joins the comparison set.
3. Decide whether CI should run `scripts/compare_charts.py`. It cannot today,
   because the baselines are ignored local fixtures.
4. Give `scripts/convert_weight_xlsx.py` and `scripts/convert_dexa_xlsx.py`
   configurable paths.
5. Run the skill evaluation suite against the updated
   `weightlifting-chart-style` skill, now that it covers stacked panels,
   palette extension, and the renderer-aware gate.
