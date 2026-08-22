# Bodyweight eval notebook chart review

## Shortcuts

- No synthetic or reduced data was used. Execution read the existing ignored `data/example-chappy.wld` and a temporary ignored symlink to the real `weight.csv`; the symlink was removed after execution.
- Review was limited to the assigned notebook and its six baseline images. No broad notebook or repository sweep was run.

## Issues

- The local notebook renderer is Matplotlib 3.5.1. The assigned baselines use 3.10.0, so glyph placement is not suitable for a strict pixel comparison.
- All six inline images have different tight-crop dimensions after the shared frame moved the title and footer inside the figure. The three original `figsize` values remain unchanged, no DPI workaround was added, and the four saved Pareto cards remain 2400 by 1350 pixels.

## Ambiguities

- The bodyweight-over-time chart needs twin y axes to preserve the time-aligned strength and bodyweight comparison. The migration keeps those twin axes and applies the shared axis treatment to both, with the secondary grid disabled.
- The bodyweight scatter chart had no legend before the migration. It uses the preserved per-panel date colorbars, while `style_legend` is used on the two chart groups that contain legends.

## Judgment calls

- The four ordinary strength series use `CATEGORICAL_COLORS`; combined strength uses `PALETTE.ink`; weekly bodyweight uses `PALETTE.reference`.
- PR date remains a continuous color encoding. Its colormap now runs from `PALETTE.neutral_point` to `PALETTE.latest` instead of using `viridis`.
- Every established Pareto frontier now uses `PALETTE.frontier`, and evaluated checkpoints use `PALETTE.checkpoint`. Lift names still distinguish the four exported cards.
- Shared subtitles and footers explain the existing encodings. Original titles, panel labels, units, annotations, legend text, date formatting, limits, metadata, and Pareto footer wording remain intact.

## Checks

- Executed `src/analyze_bodyweight_strength_evals.ipynb` successfully against the real ignored inputs and retained six refreshed PNG outputs.
- Confirmed four saved Pareto exports at 2400 by 1350 pixels.
- Compared the six refreshed outputs with the assigned originals. The comparison report paired 6 of 6 images with no missing or added images.
- Inspected side-by-side views for both four-panel charts and all four Pareto cards.
- Compared printed text outputs in calculation cells 4, 8, and 9 with `HEAD`; all matched exactly.
- Parsed notebook JSON and every non-magic Python code cell.
- Ran `git diff --check`.

## Review steps

1. Open `.artifacts/chart-comparisons/notebooks/bodyweight-evals/gallery.md`.
2. Check that the first chart retains four running PR step series, four bodyweight traces, latest-point annotations, yearly ticks, and the two legend entries.
3. Check that the second chart retains every PR point, first and latest annotations, per-panel date colorbars, and the 2018 to 2026 direction.
4. Check each Pareto card for the full checkpoint cloud, non-dominated frontier, sparse callouts, evaluation window, workout and attempt counts, limits, and saved filename.
5. If exact raster dimensions matter for inline outputs, rerun under Matplotlib 3.10.0 before judging crop or text flow.

## Edge cases

- Combined PR history and the three lift histories have different y ranges; the migration keeps Matplotlib's original per-panel limits and margins.
- Missing bodyweight values remain excluded by the existing calculations. No filtering logic changed.
- Overhead press retains its 175 to 300 y limit while the other Pareto cards retain 300 to 610.
- Duplicate frontier bodyweight and 1RMe pairs remain removed before plotting and table output.

## Next steps

- Review the side-by-side gallery under Matplotlib 3.10.0 if the integration branch requires exact renderer parity. No notebook code change is needed for that rerun.
