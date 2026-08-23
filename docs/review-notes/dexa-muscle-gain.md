# DEXA muscle-gain estimate review notes

## Result

The estimator's unrounded median is 1.4 lb of net skeletal-muscle change from the earliest to latest scan. The report rounds this to 1.5 lb, with a model-based 95% interval of -3.0 to +6.0 lb. The interval includes zero and a small loss.

The raw DEXA endpoint change is +9.4 lb of lean soft tissue. That figure is not reported as muscle because bodyweight rose 24.0 lb and lean soft tissue includes non-muscle tissue, water, glycogen, and gut contents.

## Approach and judgment calls

The main model fits `lean soft tissue ~ bodyweight + elapsed years` across all nine scans. The time coefficient estimates the lean trend at a common bodyweight. It is 2.0 lb over the 3.93-year span.

The uncertainty model separates two terms:

- Per-scan measurement error is 1.68 lb, converted from the 0.76 kg RMS-SD in Powers et al. The paper used 609 repeat Hologic scans taken 3 to 51 days apart.
- The model residual is 2.41 lb. After subtracting measurement variance, 1.73 lb remains for ordinary unmatched scan state and model error.

The simulation draws the skeletal-muscle share of the common-weight lean trend uniformly from 50% to 100%. The 50%, 75%, and 100% values are judgment cases. No primary study validates them as longitudinal conversion factors. A uniform draw keeps the main interval reproducible without pretending that one case has literature-derived probability.

The appendicular check uses the four dates with both arm and leg values. A bodyweight-plus-time fit gives -0.4 lb of adjusted appendicular lean change. Multiplying by the 1.12 cross-sectional MRI coefficient also gives about -0.4 lb. This is a sensitivity case, not an independent estimate. Four scans with three fitted coefficients are too sparse for a useful regional interval.

The closest-bodyweight endpoint pair gives +1.9 lb of adjusted lean change. Leave-one-scan-out all-scan fits range from +0.9 to +4.4 lb. These checks support the scale of the main estimate but also show how little the record says about small changes.

## Supplemental evidence

The training export begins more than five years before the first DEXA. It records 1,215 workouts before the scan window and 1,066 during it. The 95th percentile of recorded estimated 1RM rose 14% for flat bench, 20% for back squat, and 19% for overhead press between the 365-day endpoint windows. This corroborates positive adaptation but does not size muscle gain.

The weekly bodyweight file was inspected but excluded from the estimate. It does not identify tissue composition and ends before the latest DEXA scan. DEXA bodyweight already enters every modeled scan.

## Shortcuts and ambiguities

- Scanner model, software version, operator, scan preparation, positioning, and region-placement continuity are absent from the exports. The model assumes no systematic device break. This is the largest untestable measurement assumption.
- The linear bodyweight term treats the within-person scan history as the source of the body-size correction. It cannot separate every change in water, glycogen, organ mass, and muscle.
- Bodyweight and elapsed time are partly confounded. Nine irregularly spaced observations cannot identify a richer nonlinear model without overfitting.
- The source only has regional measurements on four dates. Android and gynoid regions overlap other anatomical regions, so only arms plus legs are used as the appendicular check.
- No lift or training-volume value is converted to muscle mass.
- The report does not use a medical diagnosis, diet rule, or forecast.

## Edge cases covered

- Fewer than five scans fail because the three-coefficient model would have too little residual information.
- Missing required composition columns, duplicate scan dates, non-finite measurements, negative scan error, invalid muscle-share bounds, and zero-width interpretation ranges fail with explicit errors.
- Missing or sparse regional data returns no regional sensitivity instead of inventing one.
- Missing endpoint strength data omits that lift from the corroboration table.
- The seed fixes every uncertainty draw.

## Commands and results

Focused tests:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest -q \
  tests/test_chart_style.py tests/test_dexa_muscle_gain.py
```

The final focused run passed 16 tests. The chart checks prove that the panels have independent x axes, the upper panel contains every scan, and the complete DEXA and muscle interval endpoints fall inside the lower x limits.

Full suite:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest -q
```

The full suite passed 221 tests and 46 subtests. The virtual environment uses Python 3.11, which satisfies `pyproject.toml`. The shell's default `pytest` uses Python 3.9 and cannot collect an existing Python 3.10 union annotation.

Artifact generation:

```bash
PYTHONPATH=src:. python scripts/estimate_dexa_muscle_gain.py \
  --totals <main-checkout>/data/dexa.csv \
  --regions <main-checkout>/data/dexa_regions.csv \
  --training-log <main-checkout>/data/export.wld \
  --output-dir .artifacts/dexa-muscle-gain
```

The command produced `report.md` and a 2200 by 1800 PNG. Personal inputs were read from explicit paths. They were not copied, linked, staged, or committed.

The chart uses the independent-axis option from central commit `37b3226`, cherry-picked here as `9649fa2`. The final full-size review confirmed nine upper-panel scan points, numeric pounds on the lower axis, a +1.5 lb headline estimate, unclipped y labels, and both caps of the raw DEXA interval visible. The title says the gain is uncertain because the 95% interval crosses zero.

## Review steps

1. Read `.artifacts/dexa-muscle-gain/report.md` and check that every raw DEXA value is labeled lean soft tissue or fat-free mass, never muscle.
2. Inspect `.artifacts/dexa-muscle-gain/muscle-gain-estimate.png` at full size. Confirm the header, both panels, labels, units, interval, latest-scan annotation, and footer are visible.
3. Rerun the command with the same seed and confirm identical estimates.
4. Review the 50% to 100% muscle-share range. Changing that range is a scientific judgment, not a formatting change.
5. Confirm scanner and protocol continuity before treating the same-device error assumption as adequate.
6. Run the focused tests and full test suite under the repository's supported Python version.
7. Use `git status --ignored --short .artifacts data` to confirm personal artifacts and source data remain ignored.

## Next steps

The best new evidence is a standardized repeat visit with duplicate DEXA scans on the same device. Match fasting, hydration, carbohydrate intake, recent training, software, positioning, and region placement. MRI of thigh and upper-arm muscle volume at the same visit would narrow the lean-to-muscle interpretation more than another strength metric.

If future exports record scanner and protocol metadata, add a device-break check before fitting across all dates. If appendicular regions become available on every scan, promote the regional model from a sparse sensitivity to a co-primary view, but keep total lean and appendicular lean dependent rather than averaging them.
