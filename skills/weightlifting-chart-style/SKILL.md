---
name: weightlifting-chart-style
description: Build or refactor editorial weightlifting, strength, bodyweight, or DEXA charts in this repository. Use this skill whenever a task adds a lifting analysis card, asks for the warm paper chart style, changes the DEXA topography or Pareto-frontier visuals, or migrates an existing chart to shared styling.
---

# Weightlifting chart style

Create a self-explanatory analytical card without changing what the analysis says.

## Start with the evidence

1. Read `docs/chart-style.md` and `src/chart_style.py`.
2. Read the closest existing generator. Use `src/dexa/charts.py` for topography or trajectories, `src/generate_bench_frontier_update.py` for frontier cards, and `src/dexa/forecast_charts.py` for stacked panels and modeled bands.
3. Inventory the current information before editing: plotted rows, highlighted points, labels, units, limits, title, subtitle, metadata, legend, annotations, and footer semantics.
4. If a preserved baseline exists, inspect its dimensions and appearance. Never edit a baseline image.

## Build the chart

Use `chart_canvas` with the closest frame preset, or `stacked_canvas` when the card needs a column of panels over one shared x axis. Use `add_header`, `style_axes`, `add_footer`, and `save_chart` for framing. Keep calculations and chart-specific marks in the generator.

Use the shared palette by meaning, not by convenience. Neutral marks provide context. Use `PALETTE.frontier` for an established Pareto frontier or a modeled series, and `PALETTE.advance` for a new checkpoint. Use positive and negative colors for trend residuals, and cut and bulk colors for phase paths and phase labels. Use `PALETTE.reference` for a reference construct plotted beside a model rather than produced by it. Annotate the latest scan, new frontier point, or other claim close to its mark.

If no palette entry carries the meaning you need, add one field with a name that states the meaning. Do not reuse a documented color for a second concept, and do not add a field that duplicates an existing hex.

The footer must explain the model and reading direction in plain terms. A reader should understand trimming, contour assumptions, trend residuals, or Pareto dominance from the image alone. Both footer strings share one row, so check that the widest values a generator can produce still leave a gap between them. A layout test that measures rendered text extents is cheaper than finding the collision in a published image.

## Preserve information

These rules are non-negotiable during a style migration:

- Keep every substantive observation, frontier point, trend, contour, reference band, and highlighted segment.
- Keep axis meaning, units, limits, and direction cues.
- Keep dates, sample counts, workout counts, attempt counts, and fit statistics.
- Keep direct labels, annotations, legends, and model footers. Reword only when the new text is at least as precise.
- Keep output filename, pixel dimensions, aspect ratio, and DPI unless the task documents an improvement.
- During a migration, render the existing source data. Never replace it with a synthetic history merely to make the generator run. Synthetic data belongs in focused tests or a clearly labeled new-chart prototype.
- Do not replace a domain calculation with visual shorthand.
- Do not churn notebooks or unrelated generators.
- Never commit source personal data, generated outputs, baseline images, or comparison artifacts.

## Verify the result

Run focused semantic tests and the full relevant test suite. Run both affected generators when inputs are available.

For the established cards, run:

```bash
PYTHONPATH=src:. python scripts/compare_charts.py --generate
```

Inspect the side-by-side sheets and diff images under `.artifacts/chart-comparisons`.

The command reads the Matplotlib version out of each PNG and gates on what those two renderers support. One renderer on both sides gets the strict `0.01` fidelity threshold. Different renderers, or a PNG that does not name one, get only a `0.15` gross-change ceiling and a refusal to certify, because a Matplotlib upgrade re-flows every string and reads as several percent on its own. Rerun under the baseline renderer, or read the sheets and pass `--accept-renderer-drift`. Never reach for `--accept-renderer-drift` to get past a difference you have not looked at, and never regenerate a baseline to make a comparison pass.

Passing this broad gate does not prove semantic correctness. Treat a missing point, label, unit, legend entry, state color, or footer claim as a failure even when the image looks polished.
