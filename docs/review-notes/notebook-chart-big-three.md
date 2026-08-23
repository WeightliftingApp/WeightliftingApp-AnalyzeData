# Big three notebook chart review

## Scope

Migrated both chart cells in `src/analyze_big_three.ipynb` to the shared notebook frame. The data loading, PR progression, July 1 interpolation, asymptotic fit, recent-rate projection, annotations, legend text, date formatting, and printed progress report remain in place.

## Shortcuts

- Reused one `notebook_frame((10, 6))` because both original cells used that figure size.
- Reused one exercise-to-color mapping so each lift keeps the same categorical color across both cards.
- Kept both cards single-panel. Their marks share one date and weight scale, so `stacked_canvas` would add separation without clarifying the analysis.
- Passed empty metadata rows to `add_header` because the original charts had no header metadata.

## Issues

- The execution kernel uses Matplotlib 3.5.1. The assigned originals use 3.10.0. Inline output cropping and glyph layout therefore differ.
- The assigned originals are 875 by 547 pixels and 850 by 530 pixels. This execution produced 694 by 409 pixels and 680 by 409 pixels at the same 10 by 6 figure size. The integration branch owns the shared frame DPI fix, so this notebook does not override DPI.
- Several annotations overlap in the dense 2019 to 2023 region. The same crowding appears in the originals. Moving labels would be a separate readability edit and could change the established annotation placement.

## Ambiguities

- The originals used Matplotlib's default color cycle. The shared style forbids that dependency, so the migration maps the three lifts to `CATEGORICAL_COLORS` in their existing order.
- The first chart used red stars for every July checkpoint. `PALETTE.advance` retains that red checkpoint emphasis. The second chart keeps stars in each lift's series color because those colors distinguish overlapping annual histories.
- The first title had no subtitle. The new subtitle states that the lines are lifetime running maxima and that stars are July 1 snapshots. It does not change the chart's claim.

## Judgment calls

- Kept the exact original titles. The second title's original explanatory line now occupies the shared subtitle row verbatim.
- Added model and reading footers without removing any existing labels. The first explains July interpolation. The second identifies the bounded historical fit and the diamonds where projections begin.
- Let `style_legend` retain Matplotlib's automatic placement. On the projection card it selects the upper-left open area under the shared frame instead of the original lower-center position.

## Checks

- Executed the notebook in place with the real ignored `data/example-chappy.wld` input.
- Confirmed both chart cells produced PNG outputs and the progress report still prints 500 lb bench, 600 lb squat, and 580 lb deadlift via conventional.
- Parsed the notebook as JSON and parsed every Python code cell with `ast.parse`, excluding the IPython-only install cell.
- Compared both outputs against the assigned pre-shared-style originals. The plotted PR paths, annual stars, numeric annotations, projection endpoints, labels, units, legends, and date ranges are present.
- Ran `git diff --check`.

## Review steps

1. Open cells 3 and 4 in `src/analyze_big_three.ipynb` and confirm both stored chart outputs render.
2. Compare cell 3 with `analyze_big_three_3_0.png` in the assigned baseline directory. Check all three PR paths and every red July star label.
3. Compare cell 4 with `analyze_big_three_4_0.png`. Check the faint PR paths, faint asymptotic curves, annual stars, projection-start diamonds, dashed one-year projections, and all three legend rates.
4. Confirm both x axes still use dates, both y axes still use pounds, and the second card retains angled date labels.
5. Confirm the printed current stats below cell 4 match the values above.

## Edge cases

- A lift with no matching records remains absent from both charts.
- A July 1 date with no later PR still uses the last prior record, as before.
- A lift with fewer than two July snapshots still receives no historical fit or projection.
- Failed asymptotic fits still print the existing warning and leave the observed series intact.
- Conventional and sumo deadlifts remain grouped, while the printed current stat names the variant that set the latest record.

## Next steps

- Re-execute after integration picks up the coordinator's shared frame DPI change, then inspect the stored PNG dimensions under the integration renderer.
- Revisit annotation collision handling only as a separate analysis-preserving chart task.
