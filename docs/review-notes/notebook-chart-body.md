# Notebook chart body migration

## Result

Migrated nine chart cells across the five assigned notebooks. Every current chart now uses the shared editorial frame, axes treatment, palette, header, and footer. Legends use `style_legend` where the chart has one. The calculations, source rows, printed analysis, marks, labels, units, limits, date formatting, annotations, and multi-axis relationships remain intact.

No source data, shared style code, tests, other notebooks, or standalone generated outputs changed.

## Chart inventory

| Notebook and cell | Original figure size | Preserved chart content | Shared-style treatment |
| --- | --- | --- | --- |
| `analyze_presses`, cell 3 | `(15, 8)` | Monthly press counts by year, every annotated cell, zero-filled months, the `vmax=30` cap, month and year axes, and the occurrence colorbar | `notebook_frame`, `chart_canvas`, `PALETTE.positive` heatmap ramp, `NOTEBOOK_AXES`, header, and footer |
| `analyze_top_prs`, cell 5 | `(15, 6)` | Raw monthly 1RM and volume PR counts, both three-month rolling means, four legend entries, January year ticks, and count units | `notebook_frame`, `chart_canvas`, two categorical series colors, `NOTEBOOK_AXES`, styled legend, header, and footer |
| `analyze_users`, cell 4 | `(12, 6)` | Fifty bins over 0 to 500 lb, every nonzero bar-count label, mean, 90th, 99th, and 99.9th percentile lines, and all legend values | `notebook_frame`, `chart_canvas`, neutral histogram bars, categorical statistic lines, `NOTEBOOK_AXES`, styled legend, header, and footer |
| `analyze_weight_distribution`, cell 2 | `(10, 8)` | One density ridge per valid year, the five-observation year filter calculated in cell 1, each yearly mean line, year labels, overlap, opacity, linewidth, and weight units | `notebook_frame`, `frame_figure`, categorical year colors, `NOTEBOOK_AXES` on every JoyPy axis, header, and footer |
| `analyze_wilks`, cell 0 | `(15, 6)` | Recorded weekly averages, weekly linear interpolation, pound units, three-month date ticks, and `%b '%y` labels | `notebook_frame`, `chart_canvas`, categorical bodyweight color, `NOTEBOOK_AXES`, header, and footer |
| `analyze_wilks`, cell 1 | `(15, 6)` | Interpolated and recorded bodyweight, every bench and squat 1RM estimate, circle and square markers, dual pound axes, date formatting, and conditional legend entries | Preserved twin axis with shared styling on both axes, categorical colors, styled legend, header, and footer |
| `analyze_wilks`, cell 2 | `(15, 6)` | Bodyweight, bench and squat 1RMs, the 2020 men's Wilks multiplier based at 210 lb, three aligned axes, the `0.9` to `1.1` Wilks limit, date formatting, and conditional legend entries | Preserved all three axes, used `PALETTE.frontier` for the modeled multiplier, and reserved right margin for the outward third axis |
| `analyze_wilks`, cell 3 | `(15, 6)` | Original and Wilks-adjusted bench and squat estimates, nearest-weight matching within 14 days, every dotted original-to-adjusted connector, dual axes, date formatting, and conditional legend entries | Preserved the twin axis, assigned five categorical colors, styled both axes and the legend, and documented the match window in the footer |
| `analyze_wilks`, cell 4 | `(12, 8)` | The full printed diminishing-returns analysis, required lift percentage series, all five bench-example series, both panel titles, axes, and pound and percentage units | Replaced manual subplots with `stacked_canvas` over the same bodyweight x axis, used the modeled-series color above and categorical bench colors below, then added shared axes, legend, header, and footer |

## Image comparison

The read-only baseline contains ten PNGs for these notebooks. Nine correspond to the nine current chart cells. `analyze_users_3_2.png` is a stale earlier histogram, so `analyze_users` has two baseline PNGs for one current chart. Fresh execution correctly leaves only the styled cell 4 histogram. The integration gallery maps that stale baseline to `analyze_users_4_0.png`, which keeps the full 27-image gallery reviewable.

| Notebook | Baseline PNGs | After PNGs | Review result |
| --- | ---: | ---: | --- |
| `analyze_presses` | 1 | 1 | Same 9 by 12 count grid, annotations, zeroes, and capped colorbar |
| `analyze_top_prs` | 1 | 1 | Same four series, monthly points, rolling means, legend, and yearly ticks |
| `analyze_users` | 2, including 1 stale duplicate | 1 | Current histogram preserves all bins, bar labels, percentile lines, and legend values |
| `analyze_weight_distribution` | 1 | 1 | Same nine year ridges and mean markers |
| `analyze_wilks` | 5 | 5 | Same time-series rows, lift observations, Wilks line and limit, adjusted points and connectors, and diminishing-return series |
| Total | 10 | 9 | Nine current chart slots reviewed against all ten baseline images |

The after images are in `.artifacts/notebook-chart-body-after`. Side-by-side sheets are in `.artifacts/notebook-chart-body-comparisons`. Both directories are ignored.

Current raster bounds differ from the baseline even though every source `figsize` is unchanged. The baseline used Matplotlib 3.10.0. This execution used 3.11.1, and the pre-merge `chart_canvas` does not pass `frame.dpi` to Matplotlib. The coordinator has a central fix and will re-execute after merge. Current dimensions are:

| Image | Baseline | Current after |
| --- | --- | --- |
| Press heatmap | 1358 by 790 | 1353 by 743 |
| Top PRs | 1489 by 590 | 1371 by 568 |
| Current users histogram | 1023 by 555 | 1133 by 568 |
| Weight ridgeline | 989 by 831 | 941 by 743 |
| Wilks cells 0 through 3 | 1489 by 590 each | 1394, 1433, 1408, and 1433 by 570 |
| Wilks cell 4 | 1189 by 790 | 1114 by 743 |

## Shortcuts and compatibility work

- The four notebooks with a first-cell `%pip install -r ../requirements.txt` still point to a removed file. I left those unrelated setup cells unchanged. The execution script removed that cell in memory, ran the remaining cells in sequence, restored the untouched setup cell, and wrote the executed notebook back in place.
- I created temporary ignored symlinks from this worktree to the real `weight.csv` and user WLD archive in the main checkout. I removed both links after execution. No personal input is present in the worktree or Git status.
- JoyPy 0.2.6 assumes pandas returns a list of axes. Pandas 3 returns a generator, which raised `TypeError: 'generator' object is not subscriptable`. The ridgeline cell wraps pandas' `flatten_axes` result in `list` before calling JoyPy. This is a library compatibility shim only; density inputs and JoyPy arguments are unchanged.
- JoyPy owns its figure creation, so its cell cannot enter `chart_canvas` without replacing JoyPy's plotting calculation. It uses `notebook_frame`, `frame_figure`, shared colors, `NOTEBOOK_AXES`, `style_axes`, `add_header`, and `add_footer` directly on the returned figure and axes.

## Judgment calls and ambiguities

- The dual-axis Wilks charts retain twin axes because bodyweight and lift estimates need date alignment. Splitting those measures would weaken the comparison. The three-axis chart also retains its outward Wilks axis and original `0.9` to `1.1` limit.
- The final Wilks figure now uses `stacked_canvas` because both panels measure against the same starting-bodyweight values. Its two original panel titles and y axes remain.
- Ordinary exercise, statistic, year, and lift series use `CATEGORICAL_COLORS`. The Wilks multiplier and diminishing-return percentage are modeled series, so they use `PALETTE.frontier`. The press heatmap uses a light ramp ending at `PALETTE.positive` while retaining the original green reading direction and cap.
- `style_axes` adds a grid, which is not useful over heatmap cells. The heatmap calls `style_axes` and then disables the grid; all other shared axis settings remain.
- No assigned notebook is chart-free, so every assigned notebook now imports or uses shared style code.

## Commands and results

- `uv venv .venv` and `uv pip install --python .venv/bin/python -e '.[notebooks,dev]' ipykernel`: created the ignored review environment with Matplotlib 3.11.1, pandas 3.0.5, JoyPy 0.2.6, and notebook tooling.
- Custom `.venv/bin/python` `NotebookClient` loop with a 900-second cell timeout and `src` as the working directory: executed all five notebooks in place against real local inputs. PNG counts were 1, 1, 1, 1, and 5. No executed cell has an error output.
- `.venv/bin/jupyter nbconvert --to markdown --output-dir .artifacts/notebook-chart-body-after ...`: extracted nine current PNGs and their Markdown references.
- Pillow contact-sheet script: paired the ten assigned baseline PNGs with the nine current PNGs under `.artifacts/notebook-chart-body-comparisons` and recorded renderer and dimension metadata.
- Manual inspection of all five contact sheets: verified chart count, plotted observations, labels, legends, limits, date formatting, marker shapes, and reading direction.
- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_chart_style.py -q`: 6 passed.
- Focused notebook validation script: `nbformat.validate` passed for all five notebooks; all code cells parsed; PNG output cells matched `[3]`, `[5]`, `[4]`, `[2]`, and `[0, 1, 2, 3, 4]`; every chart cell contained its original `notebook_frame` size and required shared-style calls.
- `git diff --check`: passed.

## Review instructions

1. Open the five sheets in `.artifacts/notebook-chart-body-comparisons` and compare each before image on the left with its after image on the right.
2. In `analyze_users.png`, treat `analyze_users_3_2.png` as the stale duplicate histogram. Review the current chart against `analyze_users_4_0.png`.
3. Check the Wilks sheet at full size. Confirm that the right lift axis and outer Wilks axis remain readable, the multiplier stays within `0.9` to `1.1`, and the adjusted markers retain their dotted connectors.
4. Re-execute after merging the central `chart_canvas` DPI fix, then regenerate the integration gallery. Expect dimensions to change; do not accept a missing label, point, connector, legend entry, axis, or footer as renderer drift.

## Edge cases and next steps

- The PR notebook builds months through `datetime.now()`, as it did before. A later execution can add trailing zero months without a code change.
- The user histogram depends on the complete local user archive. Empty input would still make the original mean and percentile calculations fail; this migration did not invent fallback data.
- The ridgeline still filters out years with fewer than five weekly observations. Categorical colors repeat after seven years, while direct year labels keep each ridge identifiable.
- The Wilks adjustment still omits lifts without a bodyweight match inside 14 days. It preserves `NaN` gaps rather than manufacturing a weight.
- After the coordinator merges the central DPI fix, rerun all five notebooks and refresh the ignored after images and gallery comparisons. No notebook-local DPI workaround should be added.
