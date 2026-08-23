# Workout notebook chart migration review

## Inventory and migrated cells

The audit found five chart-producing cells. All five now use `notebook_frame((15, 6))`, `chart_canvas`, `NOTEBOOK_AXES`, a shared palette, `add_header`, `add_footer`, and `style_axes`.

| Notebook | Cell | Preserved analysis | Style changes |
| --- | ---: | --- | --- |
| `src/analyze_workout_intensity.ipynb` | 2 | All workouts since 2018-10-01, the 30-day time-based rolling mean of workout duration, quarterly date ticks, minutes, and the three printed summary statistics | Uses `PALETTE.frontier`, shared axes, an editorial header, workout and date metadata, and a footer that defines the rolling window and reading direction |
| `src/analyze_workout_intensity.ipynb` | 3 | Weekly bodyweight interpolation, measured bodyweight points, workout-level volume/hour and sets/hour points, both 30-day rolling ratios, the three aligned time axes, the 12,000 to 50,000 volume/hour limit, the 15 to 30 sets/hour limit, six-month date ticks, the stale-weight warning, and all five legend entries | Uses three categorical colors, shared axes on all three y-axes, `style_legend`, an editorial header, and a footer that distinguishes rolling lines from individual workouts |
| `src/analyze_workouts.ipynb` | 2 | One workout-count bar per calendar year, every year from 2017 through 2026, and the original axis meanings | Uses the first categorical color plus the shared frame, header, axes, and footer |
| `src/analyze_workouts.ipynb` | 3 | Every recorded duration, the original percentile calculation from 0 through 100, sorted order, minutes, and point markers | Uses the first categorical color plus the shared frame, header, axes, and footer |
| `src/analyze_workouts.ipynb` | 5 | One point per workout, workout duration in minutes, total volume, and the first-degree `numpy.polyfit` trend line | Uses `PALETTE.neutral_point` and `PALETTE.trend` plus the shared frame, header, axes, and footer |

`src/analyze_workout_streaks.ipynb` has no chart-producing cells and no image outputs. I restored it exactly to the branch version after the execution audit. It has no chart-style import.

## Shortcuts not taken

- No calculation, filter, observation, axis unit, date formatter, explicit limit, legend entry, warning, annotation, or printed analysis was removed.
- No synthetic data was introduced. Execution used the real ignored workout and bodyweight inputs supplied for this task.
- No shared style code, tests, source data, standalone generated files, or other notebooks were edited. The five notebook chart outputs were re-rendered in place as requested.
- The chart-free streak notebook did not receive a cosmetic import.

## Issues, ambiguities, and judgment calls

- The intensity comparison keeps three y-axes because all three measures must align in time. Splitting the panels would make the bodyweight, volume/hour, and sets/hour relationship harder to read. `style_axes` hides right spines by default, so the two colored right spines are restored after styling. The third axis keeps its original `1.08` offset, and the figure reserves right margin so both scales remain inside the card.
- The charts use categorical colors for bodyweight, volume/hour, sets/hour, yearly counts, and sorted durations because none of those series has a documented semantic color. The duration-volume scatter uses neutral points and the shared trend color.
- The notebooks retain their original `(15, 6)` figure size. The read-only baseline was rendered by Matplotlib 3.10.0. This worktree rendered with Matplotlib 3.5.1, and its current `chart_canvas` does not apply `frame.dpi`. As a result, the ignored after PNGs are smaller than the baseline exports. A central `chart_canvas` fix exists on the integration branch and must be present before the coordinator re-executes these notebooks. I did not add a notebook-level DPI workaround.
- The five baseline images measure 1488x590, 1498x590, 1490x590, 1489x590, and 1264x547. The local after images measure 987x416, 1014x412, 993x409, 993x409, and 1011x409. Image counts match exactly: intensity 2 to 2, workouts 3 to 3, streaks 0 to 0. The size differences come from the renderer and the missing shared DPI application, plus the new editorial margins. They are not data or chart-count differences.
- Full execution updates time-sensitive cadence text. To avoid unrelated churn, the committed `analyze_workouts.ipynb` preserves the branch execution state for its non-chart cadence cell. Setup-cell execution state is also preserved. The five chart cells keep their newly rendered styled outputs.

## Commands and results

```text
jq ... src/analyze_workout_intensity.ipynb src/analyze_workouts.ipynb src/analyze_workout_streaks.ipynb
  Inventoried every code cell and image output before editing: 2, 3, and 0 charts.

jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 <notebook>
  Executed all three assigned notebooks against real local inputs. All completed without notebook errors.

jupyter nbconvert --to markdown --output-dir .artifacts/notebook-chart-workouts/after <notebook>
  Extracted five after PNGs. The streak notebook extracted none.

python image-count and Pillow dimension checks
  Baseline and after counts match 2, 3, and 0. Renderer and dimensions are recorded above.

manual baseline-to-after visual review of all five PNG pairs
  Every baseline observation, line, bar, point cloud, axis meaning, explicit limit, date format, and legend entry remains visible. The intended layout differences are the paper frame, editorial header and footer, shared palette, open top and right plot spines, and extra right margin on the three-axis card.

python AST and repository import checks
  All code cells parse. `chart_style` and the workout schema import successfully.

python -m pytest tests/test_chart_style.py -q
  The first invocation omitted `PYTHONPATH` and failed during collection because `chart_style` was not importable from the repository root.

PYTHONPATH=src:. python -m pytest tests/test_chart_style.py -q
  6 passed. Matplotlib emitted 18 deprecation warnings from the installed Pyparsing compatibility layer.

git diff --check
  Passed with no whitespace errors.

jq empty <all three assigned notebooks>
python nbformat.validate checks
  All three notebooks are valid JSON and valid nbformat v4 documents.

focused chart-cell helper and output audit
  Every migrated cell uses the required shared helpers and keeps exactly one image output. The streak notebook has no image output and no chart-style import.
```

The temporary ignored `data/weight.csv` symlink pointed to the supplied real input only during execution. It was removed before staging. No personal input or ignored artifact is part of the commit.

## Review instructions

1. Merge the integration branch change that makes `chart_canvas` honor `frame.dpi`.
2. Re-execute `src/analyze_workout_intensity.ipynb` and `src/analyze_workouts.ipynb` against the real ignored inputs.
3. Confirm that the notebooks contain two and three image outputs respectively, while `src/analyze_workout_streaks.ipynb` contains zero.
4. Compare the regenerated images with the baseline under `/Users/chappyasel/.superset/worktrees/a5219cfc-cea4-4ccb-88ab-b417cabb46a9/integrated-low-risk-upgrades/.artifacts/chart-baselines/2026-08-22-notebooks-pre-shared-style` and with this worktree's ignored `.artifacts/notebook-chart-workouts/after` images.
5. On the three-axis intensity card, check the bodyweight scale on the left, both colored scales on the right, the five-entry legend, both rolling lines, both point clouds, measured and interpolated bodyweight, and the two explicit right-axis limits.
6. Check that the printed duration summary and stale-bodyweight warning still appear beneath their chart cells.

## Edge cases and next steps

- A workout with zero recorded duration still produces an infinite per-hour value exactly as before. This migration does not alter data cleaning.
- The yearly 2026 bar is a partial-year count, as it was before the migration.
- The percentile calculation still assumes at least two workouts. No guard was added because that would change analysis behavior.
- The bodyweight series still stops at the final measured bodyweight week rather than extending to the latest workout.
- After the shared DPI fix is merged, re-execution is the only required follow-up. If the regenerated pixel dimensions still differ, inspect the renderer metadata and contact sheets before accepting the drift.
