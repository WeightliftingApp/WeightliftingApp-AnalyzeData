---
name: weightlifting-chart-style
description: Build or refactor editorial weightlifting, strength, bodyweight, or DEXA charts in this repository. Use this skill whenever a task adds a lifting analysis card, asks for the warm paper chart style, changes the DEXA topography or Pareto-frontier visuals, or migrates an existing chart to shared styling.
---

# Weightlifting chart style

Create a self-explanatory analytical card without changing what the analysis says.

## Start with the evidence

1. Read `docs/chart-style.md` and `src/chart_style.py`.
2. Read the closest existing generator. Use `src/dexa/charts.py` for topography or trajectories and `src/generate_bench_frontier_update.py` for frontier cards.
3. Inventory the current information before editing: plotted rows, highlighted points, labels, units, limits, title, subtitle, metadata, legend, annotations, and footer semantics.
4. If a preserved baseline exists, inspect its dimensions and appearance. Never edit a baseline image.

## Build the chart

Use `chart_canvas` with the closest frame preset. Use `add_header`, `style_axes`, `add_footer`, and `save_chart` for framing. Keep calculations and chart-specific marks in the generator.

Use the shared palette by meaning, not by convenience. Neutral marks provide context. Use `PALETTE.frontier` for an established Pareto frontier and `PALETTE.advance` for its new checkpoint. Use positive and negative colors for trend residuals, and cut and bulk colors for phase paths and phase labels. Annotate the latest scan, new frontier point, or other claim close to its mark.

The footer must explain the model and reading direction in plain terms. A reader should understand trimming, contour assumptions, trend residuals, or Pareto dominance from the image alone.

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

Inspect the side-by-side sheets and diff images under `.artifacts/chart-comparisons`. Report dimensions and coarse metrics, but do not require exact pixel identity after a deliberate refactor. Treat a missing point, label, unit, legend entry, or footer claim as a failure even when the image looks polished.
