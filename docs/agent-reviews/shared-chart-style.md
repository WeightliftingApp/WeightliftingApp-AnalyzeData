# Shared chart style review

## Shortcuts

- I kept the existing DEXA composition chart and save path intact. Redesigning that chart would have exceeded the two reference cards and created unrelated visual churn.
- I drafted three skill eval prompts but did not run the skill evaluation, as requested.
- I did not edit notebooks. The reusable code and deterministic tests cover the migration.

## Issues

- The baseline directory arrived untracked. Adding `.artifacts/` to `.gitignore` protects the baselines and every generated comparison without moving or rewriting them.
- The weight log emits two `openpyxl` warnings about unsupported workbook extensions during read-only loading. Both generators still complete, and the loader does not save the workbook.
- The refactored images have slight antialiasing drift around text and contour labels. Visual inspection found no missing or shifted content. Coarse metrics stay below a 0.004 changed-pixel fraction at a per-pixel threshold of 8.

## Ambiguities

- "Migrate `src/dexa/charts.py`" could have implied restyling both DEXA outputs. I treated the lean-mass topography as the target reference and left composition data, presentation, and saving intact.
- The bench annotation hardcoded `315×14`. I now derive weight and reps from the highlighted attempt. The current output text remains `315×14`, while future updates cannot silently display the wrong set.
- A later DEXA report follow-up exists on the base line of work. This branch does not touch report prose or calculations beyond the already seeded bodyweight helper.

## Judgment calls

- `src/chart_style.py` owns paper and panel colors, semantic palette entries, fixed frame presets, axes cleanup, header and footer placement, and saving. Plot marks and domain calculations stay with each generator.
- The module exposes two frame presets and two axis presets instead of a long list of layout arguments at each call site. This keeps the interface small while preserving the exact portrait and wide-card geometry.
- Bench loading and rendering now have separate functions. Tests can render a complete frontier card from synthetic attempts without reading personal files.
- Semantic tests inspect Matplotlib artists and text. Pixel tests cover dimensions and broad drift, not exact raster output.

## Rejected alternatives

- Global `matplotlib.rcParams` mutations were rejected because they would leak styling into notebooks and unrelated charts.
- A generic plotting framework for lines, scatters, frontiers, and annotations was rejected. It would move domain meaning into style code and make the module shallow.
- Exact PNG equality was rejected because equivalent Matplotlib output can vary at antialiased edges after refactoring.
- Rebuilding the dark composition chart in the paper style was rejected because the task names the topography and bench cards as the authority.

## Comparison results

Command:

```bash
PYTHONPATH=src:. python scripts/compare_charts.py --generate
```

Results:

| Chart | Before | After | Mean absolute channel difference | RMS difference | Changed pixels over 8 |
| --- | --- | --- | ---: | ---: | ---: |
| DEXA lean mass vs bodyweight | 2000×1600 | 2000×1600 | 0.2350 | 5.0362 | 0.003999 |
| Bench frontier update | 2400×1350 | 2400×1350 | 0.2058 | 4.5074 | 0.003890 |

The contact sheets and diff images are under `.artifacts/chart-comparisons`. Both side-by-side sheets retain the same points, annotations, metadata, axes, legends, and footers. The directory remains ignored.

## Files examined

- `src/dexa/charts.py`
- `src/dexa/calculations.py`
- `src/dexa/pipeline.py`
- `scripts/analyze_dexa.py`
- `src/generate_bench_frontier_update.py`
- `src/analysis_utils.py`
- `tests/test_analyze_dexa.py`
- `tests/test_analysis_utils.py`
- `.gitignore`
- The two authoritative PNGs in `.artifacts/chart-baselines/2026-08-21-pre-shared-style`

## Edge cases

- Headers reject a third metadata row instead of overlapping text.
- Saving creates missing parent directories and closes the figure.
- The comparison tool normalizes unequal dimensions onto equal white canvases before measuring and fails clearly when either image is missing.
- The bench renderer still requires exactly one newly added frontier coordinate and rejects an update point that is not Pareto-optimal.
- Trailing bodyweight requires a valid weigh-in on every day in the seven-day window. Missing calendar days cannot pull older measurements into the average.
- Chart semantic tests cover dynamic set labels, frontier counts, DEXA scan labels, trend and contour artists, axes, legend text, and footer claims.

## Next steps

- A paired Superset evaluation ran all three prompts with and without the skill. The skill passed 18 of 18 objective checks; the baseline passed 16 of 18. It prevented synthetic data substitution during a DEXA migration and preserved the shared blue frontier and red advance semantics on a new deadlift card. Mean wall time was effectively unchanged.
- The installed `skill-creator` package lacks its documented benchmark aggregation and review-viewer scripts. Raw outputs, grading files, timing, paired charts, and a direct benchmark remain under the ignored `skills/weightlifting-chart-style-workspace/iteration-1` directory.
- If the later DEXA report follow-up lands first, rebase or cherry-pick this chart commit and rerun the full tests plus `scripts/compare_charts.py --generate`.
