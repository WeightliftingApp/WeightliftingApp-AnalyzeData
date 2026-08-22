"""Render the DEXA muscle-gain estimate as a local Markdown report."""

from __future__ import annotations

import numpy as np

from .muscle_gain import (
    MuscleGainEstimate,
    TrainingEvidence,
    leave_one_scan_out_adjusted_gains,
)


def _half_pound(value: float) -> float:
    return round(value * 2.0) / 2.0


def _signed_half(value: float) -> str:
    return f"{_half_pound(value):+.1f}"


def _scan_inventory(estimate: MuscleGainEstimate) -> str:
    rows = []
    for scan in estimate.totals.itertuples(index=False):
        rows.append(
            f"| {scan.date.date()} | {scan.weight_lb:.1f} | "
            f"{scan.lean_soft_tissue_lb:.1f} | {scan.bone_mineral_content_lb:.1f} | "
            f"{scan.fat_free_mass_lb:.1f} | {scan.fat_mass_lb:.1f} |"
        )
    return "\n".join(rows)


def _window_rows(estimate: MuscleGainEstimate) -> str:
    rows = []
    for window in estimate.windows:
        rows.append(
            f"| {window.label} | {window.start_date} to {window.end_date} "
            f"({window.years:.2f} y) | {window.weight_change_lb:+.1f} | "
            f"{window.lean_soft_tissue_change_lb:+.1f} | "
            f"{window.bone_mineral_content_change_lb:+.1f} | "
            f"{window.fat_free_mass_change_lb:+.1f} | "
            f"{window.fat_mass_change_lb:+.1f} |"
        )
    return "\n".join(rows)


def _regional_section(estimate: MuscleGainEstimate) -> str:
    regional = estimate.regional
    if regional is None:
        return "Regional data did not contain at least four matched arm and leg scans."
    converted = 1.12 * regional.adjusted_appendicular_change_lb
    return f"""Four scans have both arm and leg regions. Arms plus legs rose **{regional.observed_appendicular_change_lb:+.1f} lb** from {regional.start_date} to {regional.end_date}, but those endpoints also differ in bodyweight. Fitting the same bodyweight-plus-time model to the four appendicular scans gives **{regional.adjusted_appendicular_change_lb:+.1f} lb** at a common bodyweight. The arm and leg components are {regional.adjusted_arm_change_lb:+.1f} and {regional.adjusted_leg_change_lb:+.1f} lb.

Applying the `1.12 x appendicular lean` coefficient from a cross-sectional MRI equation gives **{converted:+.1f} lb** as a named sensitivity case. It is not part of the main estimate. The equation predicts muscle level across people and has not been validated as an individual longitudinal conversion. [Kim et al., 2002](https://doi.org/10.1093/ajcn/76.2.378) and [McCarthy et al., 2023](https://doi.org/10.1038/s41598-023-29827-y) found similar cross-sectional slopes, while longitudinal DXA-versus-MRI agreement was much weaker in a small training study. [Tavoian et al., 2019](https://doi.org/10.1038/s41598-019-46428-w)"""


def _training_section(training: TrainingEvidence | None) -> str:
    if training is None:
        return "No training export was supplied. Strength and volume were not used."
    rows = []
    for comparison in training.comparisons:
        rows.append(
            f"| {comparison.exercise} | {comparison.baseline_p95_one_rm_lb:.0f} | "
            f"{comparison.latest_p95_one_rm_lb:.0f} | {comparison.change_pct:+.0f}% | "
            f"{comparison.baseline_workouts} / {comparison.latest_workouts} |"
        )
    table = "\n".join(rows)
    return f"""The log begins on {training.first_workout_date}. It contains **{training.workouts_before_baseline:,} workouts before the first DEXA** and **{training.workouts_during_scan_window:,} workouts during the scan window**. Chappy was already well trained at baseline, so a modest muscle-gain estimate is more plausible than a novice-scale one.

The table compares the 95th percentile of recorded estimated 1RM values in the 365 days before each endpoint. Requiring 1 to 12 reps and using a percentile reduces dependence on one exceptional set.

| Exercise | Baseline e1RM p95 | Latest e1RM p95 | Change | Workouts baseline / latest |
|---|---:|---:|---:|---:|
{table}

Strength improved across these lifts, which supports some positive adaptation. Technique, exercise exposure, neural adaptation, body proportions, and effort also change strength. None of these values enters the muscle-mass calculation, and pounds added to a lift are not converted to pounds of muscle."""


def render_muscle_gain_report(
    estimate: MuscleGainEstimate,
    training: TrainingEvidence | None = None,
    chart_filename: str = "muscle-gain-estimate.png",
) -> str:
    """Render a report that keeps observed lean and estimated muscle separate."""
    full = estimate.earliest_to_latest
    recent = estimate.recent
    leave_one_out = leave_one_scan_out_adjusted_gains(estimate.totals)
    endpoint_adjusted = (
        full.lean_soft_tissue_change_lb
        - estimate.bodyweight_slope * full.weight_change_lb
    )
    totals = estimate.totals
    closest = totals.iloc[
        (totals.iloc[:-1]["weight_lb"] - totals.iloc[-1]["weight_lb"]).abs().argmin()
    ]
    latest = totals.iloc[-1]
    closest_adjusted = (
        latest["lean_soft_tissue_lb"]
        - closest["lean_soft_tissue_lb"]
        - estimate.bodyweight_slope * (latest["weight_lb"] - closest["weight_lb"])
    )
    q50 = 0.50 * estimate.full_span_adjusted_lean_gain_lb
    q75 = 0.75 * estimate.full_span_adjusted_lean_gain_lb
    q100 = estimate.full_span_adjusted_lean_gain_lb
    measurement_change_95 = (
        1.96 * np.sqrt(2.0) * estimate.assumed_scan_error_sd_lb
    )
    central = _half_pound(estimate.muscle_gain_median_lb)
    low = _half_pound(estimate.muscle_gain_low_95_lb)
    high = _half_pound(estimate.muscle_gain_high_95_lb)
    regional_case = (
        "Unavailable"
        if estimate.regional is None
        else f"{1.12 * estimate.regional.adjusted_appendicular_change_lb:+.1f} lb"
    )

    return f"""# How much skeletal muscle did Chappy gain?

## Bottom line

The central estimate is **{central:.1f} lb of net skeletal muscle gained** from {full.start_date} to {full.end_date}. A defensible 95% interval is **{low:+.1f} to {high:+.1f} lb**.

That interval includes zero and a small loss. The central case is a modest gain, but these scans do not establish that a gain occurred. The **{full.lean_soft_tissue_change_lb:+.1f} lb** shown by the raw lean-soft-tissue endpoints is not a muscle estimate. Chappy was {full.weight_change_lb:+.1f} lb heavier at the latest scan, and DEXA lean soft tissue includes water, glycogen, organs, skin, connective tissue, and gut contents. It is not skeletal muscle.

![DEXA muscle-gain estimate]({chart_filename})

## What the scans observed

| Window | Dates | Bodyweight | Lean soft tissue | Bone mineral | Fat-free mass | Fat mass |
|---|---|---:|---:|---:|---:|---:|
{_window_rows(estimate)}

The earliest-to-latest window answers the full-history question. The recent window uses the scan nearest three years before the latest scan, which is {recent.start_date}. It guards against making the answer depend on the unusually lean first endpoint.

### Scan inventory

| Date | Bodyweight | Lean soft tissue | Bone mineral | Fat-free mass | Fat mass |
|---|---:|---:|---:|---:|---:|
{_scan_inventory(estimate)}

All masses are pounds. Fat-free mass equals lean soft tissue plus bone mineral content in this export.

## How the estimate works

The estimator fits all {len(totals)} scans at once:

`lean soft tissue = intercept + bodyweight coefficient x bodyweight + time coefficient x years + residual`

The fitted bodyweight coefficient is **{estimate.bodyweight_slope:.3f} lb of lean soft tissue per pound of bodyweight**. The time coefficient is **{estimate.annual_adjusted_lean_slope_lb:.2f} lb per year**, or **{estimate.full_span_adjusted_lean_gain_lb:.1f} lb** over the full {full.years:.2f}-year span at a common bodyweight of {estimate.reference_weight_lb:.1f} lb. This common-weight trend is the observed lean-mass component the model tries to interpret. It is not yet called muscle.

The seeded uncertainty calculation uses {estimate.assumptions.simulations:,} draws. Each scan gets **{estimate.assumed_scan_error_sd_lb:.2f} lb** of standard deviation, based on 0.76 kg total-lean RMS-SD from 609 repeat Hologic scans taken 3 to 51 days apart. That implies a two-endpoint 95% measurement span of about **+/-{measurement_change_95:.1f} lb**. [Powers et al., 2015](https://doi.org/10.1016/j.jocd.2013.09.010) The remaining **{estimate.residual_state_sd_lb:.2f} lb** residual standard deviation covers ordinary unmatched scan state and model misspecification without adding the full experimental dehydration and glycogen shifts again.

No study validates one personal conversion from total DEXA lean change to muscle change. The model therefore draws the skeletal-muscle share uniformly from a declared **50% to 100%** range. The midpoint is 75%. These are judgment cases, not published probabilities. Combining that interpretation range with scan and regression uncertainty produces the reported interval. Results are rounded to 0.5 lb.

## Sensitivity cases

| Case | Result | Reading |
|---|---:|---|
| Raw earliest-to-latest lean soft tissue | {full.lean_soft_tissue_change_lb:+.1f} lb | Observed DEXA compartment, not muscle |
| Raw recent-window lean soft tissue | {recent.lean_soft_tissue_change_lb:+.1f} lb | Endpoint-dependent and bodyweight-confounded |
| Endpoint change adjusted by fitted bodyweight slope | {endpoint_adjusted:+.1f} lb | Uses only the first and last readings after estimating the slope from all scans |
| Closest-bodyweight pair, {closest.date.date()} to {latest.date.date()} | {closest_adjusted:+.1f} lb | The scans differ by {latest.weight_lb-closest.weight_lb:+.1f} lb of bodyweight |
| All-scan common-weight lean trend | {estimate.full_span_adjusted_lean_gain_lb:+.1f} lb | Main observed-lean input before muscle interpretation |
| Muscle share at 50% / 75% / 100% | {q50:+.1f} / {q75:+.1f} / {q100:+.1f} lb | Judgment cases, not validated conversions |
| Leave one scan out | {min(leave_one_out):+.1f} to {max(leave_one_out):+.1f} lb lean | Shows dependence on any one scan |
| Regional appendicular conversion | {regional_case} | `1.12 x` bodyweight-adjusted arms-plus-legs trend; sparse cross-sectional sensitivity |

## Regional check

{_regional_section(estimate)}

## Strength and training history

{_training_section(training)}

## Limits that matter

- Hydration and glycogen can move DEXA lean tissue by several pounds without new muscle protein. Active men lost 1.69 kg of DEXA lean tissue after exercise and heat dehydration, then gained 2.36 kg after carbohydrate supercompensation. [Toomey et al., 2017](https://doi.org/10.1007/s00421-017-3552-x)
- Food and gut content matter. Afternoon feeding changed total and regional lean readings, while an overnight fast returned them to baseline. [Shiel et al., 2017](https://doi.org/10.1249/MSS.0000000000001148)
- Device, software, positioning, and region placement matter. A GE Lunar-to-Hologic comparison found systematic appendicular-lean differences despite high correlation. [Park et al., 2021](https://doi.org/10.3803/EnM.2021.1274) The source files do not identify scanner, software, operator, preparation, or positioning, so the model cannot test protocol continuity.
- Body size matters twice. Larger bodies can have larger absolute scan error, and gaining bodyweight adds non-muscle lean tissue. The regression's bodyweight term is an empirical correction, not a physiological law.
- The linear time trend is a summary of nine irregularly spaced scans. It cannot locate when muscle changed, and bodyweight and time remain partly confounded.
- The 95% interval is model-based, not a calibrated clinical interval. The lean-to-muscle share is the weakest assumption.

## What would narrow the interval most

Another strength metric would not help much. The best next measurement is a standardized repeat body-composition visit with duplicate rested, morning, overnight-fasted scans. Match hydration, carbohydrate intake, recent training, scanner, software, positioning, and region placement. Pair the DEXA visit with MRI muscle volume of the thighs and upper arms if the target is skeletal muscle rather than lean tissue. Duplicate DEXA would estimate this scanner's repeatability; MRI would address the lean-to-muscle ambiguity.

## Reproduction

```bash
PYTHONPATH=src:. python scripts/estimate_dexa_muscle_gain.py \\
  --totals /absolute/path/to/dexa.csv \\
  --regions /absolute/path/to/dexa_regions.csv \\
  --training-log /absolute/path/to/export.wld \\
  --output-dir .artifacts/dexa-muscle-gain
```

The source CSV and training export are read only. The command writes the report and chart to the ignored artifact directory.
"""
