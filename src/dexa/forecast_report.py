"""Pure Markdown rendering for the bulk-ceiling forecast."""

from __future__ import annotations

import numpy as np

from .forecast import (
    CONSERVATIVE_MEASUREMENT_ERROR_PP,
    DEFAULT_EXTRAPOLATION_MARGIN_LB,
    DEFAULT_SIMULATIONS,
    MINIMUM_INTERVAL_GAIN_LB,
    PREDICTION_COVERAGE,
    PREDICTION_COVERAGE_INNER,
    RESAMPLE_UNIT_BLOCK,
    SAFETY_CONFIDENCE,
    SPARSE_INTERVAL_THRESHOLD,
    BulkCeilingForecast,
)

# Weights the summary table reports on, relative to the current scan.
SUMMARY_OFFSETS_LB = (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0)


def _index_at(forecast: BulkCeilingForecast, weight_lb: float) -> int:
    return int(np.abs(forecast.weight_grid_lb - weight_lb).argmin())


def _summary_rows(forecast: BulkCeilingForecast) -> str:
    rows = []
    for offset in SUMMARY_OFFSETS_LB:
        weight = forecast.current_weight_lb + offset
        if weight > forecast.resolved_max_weight_lb:
            continue
        index = _index_at(forecast, weight)
        rows.append(
            f"| {weight:.1f} lb | {offset:+.0f} lb | "
            f"{forecast.body_fat_median_pct[index]:.1f}% | "
            f"{forecast.body_fat_low_80_pct[index]:.1f}% to "
            f"{forecast.body_fat_high_80_pct[index]:.1f}% | "
            f"{forecast.body_fat_low_95_pct[index]:.1f}% to "
            f"{forecast.body_fat_high_95_pct[index]:.1f}% | "
            f"{forecast.probability_under_target[index]:.1%} |"
        )
    return "\n".join(rows)


def _interval_rows(forecast: BulkCeilingForecast) -> str:
    block_of = {
        member: position
        for position, block in enumerate(forecast.resampling_blocks, start=1)
        for member in block
    }
    rows = []
    for position, interval in enumerate(forecast.intervals):
        rows.append(
            f"| {position + 1} | {interval.label} | "
            f"{interval.start_weight_lb:.1f} to {interval.end_weight_lb:.1f} lb | "
            f"{interval.weight_gain_lb:+.1f} lb | "
            f"{interval.fat_free_gain_lb:+.1f} lb | "
            f"{interval.lean_fraction:.3f} | {block_of[position]} |"
        )
    return "\n".join(rows)


def _predictive_rows(forecast: BulkCeilingForecast) -> str:
    score = forecast.predictive_score
    if score is None:
        return ""
    rows = []
    for fold in score.folds:
        rows.append(
            f"| {fold.interval_label} | {fold.target_weight_lb:.1f} lb | "
            f"{fold.observed_body_fat_pct:.2f}% | "
            f"{fold.predicted_median_pct:.2f}% | "
            f"{fold.predicted_low_80_pct:.2f}% to {fold.predicted_high_80_pct:.2f}% | "
            f"{fold.observed_percentile:.0%} | "
            f"{'yes' if fold.inside_80 else 'no'} | "
            f"{'yes' if fold.inside_95 else 'no'} |"
        )
    return "\n".join(rows)


def _jackknife_rows(forecast: BulkCeilingForecast) -> str:
    jackknife = forecast.jackknife
    if jackknife is None:
        return "Refit sensitivity was not run for this report."
    rows = ["| Interval dropped | Mean `k` | Safety ceiling |", "|---|---:|---:|"]
    for label, mean, ceiling in zip(
        jackknife.dropped_label,
        jackknife.mean_lean_fraction,
        jackknife.safety_ceiling,
    ):
        rows.append(f"| {label} | {mean:.4f} | {ceiling.describe_short()} |")
    return "\n".join(rows)


def _sensitivity_rows(forecast: BulkCeilingForecast) -> str:
    sensitivity = forecast.sensitivity
    if sensitivity is None:
        return "Sensitivity refits were not run for this report."
    baseline = forecast.safety_ceiling
    rows = [
        "| Run | Safety ceiling | Shift |",
        "|---|---:|---:|",
        f"| Headline, every term on | {baseline.describe_short()} | |",
    ]
    for label, estimate in (
        (
            "Future-bulk deviation off (`--partition-noise-scale 0`)",
            sensitivity.zero_partition_noise,
        ),
        (
            "Measurement error off (`--measurement-error-pp 0`)",
            sensitivity.zero_measurement_error,
        ),
    ):
        if estimate.identified and baseline.identified:
            shift = f"{estimate.raw_lb - baseline.raw_lb:+.2f} lb"
        else:
            shift = "not comparable"
        rows.append(f"| {label} | {estimate.describe_short()} | {shift} |")
    return "\n".join(rows)


def _reference_position(forecast: BulkCeilingForecast) -> str:
    """Say where the constant fat-free mass reference landed against the model."""
    reference = forecast.constant_ffm_ceiling_lb
    opening = (
        f"The constant fat-free mass reference sits at {reference:.1f} lb. It "
        "needs no model, no resampling, and no measurement-error assumption."
    )
    low = forecast.prediction_low_95
    ceiling = forecast.safety_ceiling
    if low.identified and reference <= low.raw_lb:
        return (
            f"{opening} Here it is the strictest of the three figures, which is "
            "the usual case and the reason it is included. When the modeled "
            "numbers feel too clever, this is the one to fall back on."
        )
    if ceiling.identified and reference <= ceiling.raw_lb:
        return (
            f"{opening} Here it lands below the {SAFETY_CONFIDENCE:.0%} safety "
            "ceiling but above the bottom of the prediction interval, so it is "
            "the middle of the three."
        )
    if not ceiling.identified:
        return (
            f"{opening} The safety ceiling was not identified below the "
            f"{forecast.resolved_max_weight_lb:.1f} lb cap, so the two cannot be "
            "ranked on this run."
        )
    return (
        f"{opening} Here it lands above the {SAFETY_CONFIDENCE:.0%} safety "
        f"ceiling of {ceiling.describe_short()}, so it is not the conservative "
        "figure this time. That happens when the current reading is close to the "
        "target: measurement error on that reading alone can put the true value "
        "nearer the target than the printout says, and the modeled ceiling prices "
        "that in while the constant fat-free mass calculation does not. Take the "
        "lower of the two."
    )


def _planning_section(forecast: BulkCeilingForecast) -> str:
    plan = forecast.planning
    lines = [
        "| Field | Value |",
        "|---|---:|",
        f"| Current bodyweight | {plan.current_bodyweight_lb:.1f} lb |",
        f"| Source | {plan.bodyweight_source} |",
    ]
    if plan.weekly_bulk_rate_lb is None:
        lines.append("| Weekly bulk rate | not supplied |")
    else:
        lines.append(f"| Weekly bulk rate | {plan.weekly_bulk_rate_lb:.2f} lb/week |")

    if plan.headroom_lb is None:
        lines.append("| Headroom to the safety ceiling | unavailable |")
    else:
        lines.append(
            f"| Headroom to the safety ceiling | {plan.headroom_lb:+.1f} lb |"
        )

    if plan.weeks_to_ceiling is None:
        lines.append("| Weeks to the safety ceiling | unavailable |")
    elif plan.weeks_to_ceiling == 0.0:
        lines.append("| Weeks to the safety ceiling | already at or past it |")
    else:
        lines.append(
            f"| Weeks to the safety ceiling | {plan.weeks_to_ceiling:.1f} weeks |"
        )
    table = "\n".join(lines)

    notes = []
    if plan.is_scan_fallback:
        notes.append(
            "No current bodyweight was supplied, so headroom is measured from the "
            "DEXA scan weight itself. Pass `--current-bodyweight-lb` (or "
            "`--weight-log`) to measure it from where the scale actually reads "
            "today."
        )
    else:
        notes.append(
            "The forecast still anchors body composition on the DEXA scan. A "
            "supplied current bodyweight moves only where headroom is measured "
            "from, never the modeled ceiling, so a large gap between the two "
            "means the composition behind the ceiling is stale."
        )
    if plan.unavailable_reason is not None:
        notes.append(f"Duration is unavailable because {plan.unavailable_reason}.")
    if plan.weekly_bulk_rate_lb is None:
        notes.append(
            "No rate is assumed. Pass `--weekly-bulk-rate-lb` to convert headroom "
            "into weeks."
        )
    return table + "\n\n" + "\n\n".join(notes)


def _simulation_note(forecast: BulkCeilingForecast) -> str:
    if forecast.simulations_is_default:
        return (
            f"Checked against runs at four and ten times this count, where the "
            f"reported quantiles move by under 0.1 lb."
        )
    return (
        f"Overridden from the default of {DEFAULT_SIMULATIONS:,}. The stability "
        "check behind the default does not cover this count."
    )


def _cap_note(forecast: BulkCeilingForecast) -> str:
    if forecast.max_weight_is_default:
        largest = max(
            interval.weight_gain_lb for interval in forecast.intervals
        )
        return (
            f"Current scan weight plus {DEFAULT_EXTRAPOLATION_MARGIN_LB:g} lb, "
            f"against a largest observed bulk of {largest:.1f} lb."
        )
    return "Supplied on the command line, overriding the default margin."


def _noise_share_note(forecast: BulkCeilingForecast) -> str:
    observed = forecast.lean_fraction_sd
    implied = forecast.measurement_implied_lean_fraction_sd
    deconvolved = forecast.deconvolved_lean_fraction_sd
    share = forecast.noise_variance_share
    if deconvolved is None:
        return (
            f"At {forecast.assumptions.measurement_error_pp:g} pp of scan error, "
            f"noise alone implies a standard deviation in `k` of {implied:.3f}, "
            f"which is at or above the {observed:.3f} actually observed. At this "
            "error setting the two cannot be separated, and the double-count "
            "cannot be sized. That is a reason to prefer the DXA-specific default "
            "over a wider conservative setting, not a finding about the body."
        )
    return (
        f"At {forecast.assumptions.measurement_error_pp:g} pp of scan error, noise "
        f"alone implies a standard deviation in `k` of {implied:.3f}, against "
        f"{observed:.3f} actually observed across the intervals. Scan noise "
        f"therefore accounts for roughly {share:.0%} of the observed variance, "
        f"and about {deconvolved:.3f} of the spread survives after removing it. "
        "Real interval-to-interval variation in partitioning is present, so the "
        "residual term is doing genuine work and is not merely re-adding noise. "
        "The double-count is real but modest: the model resamples the full "
        f"{observed:.3f} spread and then adds scan error on top."
    )


def render_markdown(
    forecast: BulkCeilingForecast,
    chart_filename: str = "bulk-ceiling-forecast.png",
    curve_filename: str = "bulk-ceiling-probability-curve.csv",
) -> str:
    """Render the forecast report without reading or writing files."""
    settings = forecast.assumptions
    target = settings.target_body_fat_pct
    safety_pct = f"{SAFETY_CONFIDENCE:.0%}"
    outer_pct = f"{PREDICTION_COVERAGE:.0%}"
    inner_pct = f"{PREDICTION_COVERAGE_INNER:.0%}"

    if forecast.is_sparse:
        warning = (
            f"> **Sparse data warning.** This forecast rests on "
            f"{forecast.interval_count} positive-weight DEXA intervals, which "
            f"carry only {forecast.resampling_unit_count} independent resampling "
            f"units once intervals sharing a scan are grouped. That is below the "
            f"{SPARSE_INTERVAL_THRESHOLD} intervals this report treats as the "
            "point where resampling starts to behave. A single unusual bulk moves "
            "the whole answer. Treat the numbers below as an ordering of options "
            "rather than as calibrated probabilities.\n>\n"
            "> This is decision support built from personal scan history. It is "
            "not medical advice."
        )
    else:
        warning = (
            f"> This forecast rests on {forecast.interval_count} positive-weight "
            f"DEXA intervals carrying {forecast.resampling_unit_count} independent "
            "resampling units. This is decision support built from personal scan "
            "history. It is not medical advice."
        )

    if forecast.excluded_intervals:
        excluded_note = ", ".join(
            f"{interval.label} ({interval.weight_gain_lb:+.1f} lb)"
            for interval in forecast.excluded_intervals
        )
    else:
        excluded_note = (
            f"None. Every positive-weight interval cleared the "
            f"{MINIMUM_INTERVAL_GAIN_LB:g} lb minimum gain."
        )

    if forecast.has_shared_endpoints:
        block_note = (
            f"The {forecast.interval_count} intervals form "
            f"{forecast.resampling_unit_count} blocks because some consecutive "
            "bulks meet at the same scan and therefore share that scan's "
            "measurement error. Blocks resample together, so one scan's noise is "
            "never counted as two independent observations. The effective sample "
            f"size is {forecast.resampling_unit_count}, not "
            f"{forecast.interval_count}."
        )
    else:
        block_note = (
            f"No two intervals share a scan, so all {forecast.interval_count} "
            "resample independently."
        )

    if forecast.has_shared_endpoints:
        dependence_note = (
            "Intervals share scans. Consecutive bulks that meet at the same scan "
            "inherit that scan's measurement error in both of their ratios, so "
            "they are not independent observations. Blocking handles the "
            "resampling side of this, but it does not make the underlying sample "
            f"any larger: the effective sample size is "
            f"{forecast.resampling_unit_count}, not {forecast.interval_count}. The "
            "held-out folds inherit the same dependence, so the coverage numbers "
            "above are optimistic."
        )
    else:
        dependence_note = (
            f"The sample is small. No two intervals share a scan here, so all "
            f"{forecast.interval_count} resample independently, but "
            f"{forecast.interval_count} units is still far too few to calibrate a "
            "tail probability."
        )

    if forecast.has_shared_endpoints:
        fold_dependence_note = (
            "The folds are also not independent of each other here, because some "
            "neighbouring bulks share a scan."
        )
    else:
        fold_dependence_note = (
            "No two bulks in this record share a scan, so the folds are at least "
            "independent of each other."
        )

    score = forecast.predictive_score
    if score is not None:
        covered_80 = sum(1 for fold in score.folds if fold.inside_80)
        covered_95 = sum(1 for fold in score.folds if fold.inside_95)
    if score is None:
        predictive_section = "The held-out predictive check was not run."
    else:
        predictive_section = f"""Each bulk is held out in turn. The model is resampled on the remaining bulks only, anchored on the held-out bulk's own starting scan, and asked what a scan would read at that bulk's actual ending weight. The observed reading is then placed inside that predictive distribution. Unlike a refit, this can be wrong.

| Held-out bulk | End weight | Observed | Predicted median | Predicted {inner_pct} range | Observed percentile | In {inner_pct}? | In {outer_pct}? |
|---|---:|---:|---:|---:|---:|---:|---:|
{_predictive_rows(forecast)}

- {inner_pct} coverage: **{score.coverage_80:.0%}** across {len(score.folds)} folds
- {outer_pct} coverage: **{score.coverage_95:.0%}** across {len(score.folds)} folds
- Median absolute error: **{score.median_absolute_error_pp:.2f} pp**
- Mean signed error: {score.mean_error_pp:+.2f} pp, where positive means the scans read fatter than the model predicted

{len(score.folds)} folds cannot validate a {outer_pct} interval. Seeing {covered_95} of {len(score.folds)} inside the {outer_pct} band, and {covered_80} of {len(score.folds)} inside the {inner_pct} band, is what you would see from a well calibrated model and also from a badly overwide one. The difference is not resolvable at this sample size. The median absolute error is the part worth reading, because it is a direct statement of typical accuracy in percentage points. {fold_dependence_note}"""

    return f"""# Bulk ceiling forecast, {target:g}% body fat

Modeled from the {forecast.current_date} DEXA scan. All figures below are modeled estimates, not measurements.

{warning}

## Bottom line

| Figure | Weight | What it means |
|---|---:|---|
| Constant fat-free mass reference | **{forecast.constant_ffm_ceiling_lb:.1f} lb** | Deterministic. Where {target:g}% arrives if not one further ounce of fat-free mass is gained. No simulation involved. |
| One-sided {safety_pct} safety ceiling | **{forecast.safety_ceiling.describe()}** | Heaviest weight where the model still gives at least a {safety_pct} chance that a scan reads under {target:g}%. |
| Median crossing weight | {forecast.median_crossing.describe()} | Half the simulated paths cross {target:g}% below this weight. |
| Two-sided {inner_pct} prediction interval | {forecast.prediction_low_80.describe()} to {forecast.prediction_high_80.describe()} | Central {inner_pct} of simulated crossing weights. |
| Two-sided {outer_pct} prediction interval | {forecast.prediction_low_95.describe()} to {forecast.prediction_high_95.describe()} | Central {outer_pct} of simulated crossing weights. |

The answer to "how heavy can I bulk and stay under {target:g}% with {safety_pct} confidence" is **{forecast.safety_ceiling.describe()}**.

Figures shown as "above" a weight are censored at the {forecast.resolved_max_weight_lb:.1f} lb extrapolation cap. They are never clamped to the cap and printed as if exact. At the cap itself the modeled probability of still reading under {target:g}% is {forecast.probability_at_cap:.1%}.

## Why the two {outer_pct} numbers differ

The {safety_pct} safety ceiling and the bottom of the {outer_pct} prediction interval answer different questions, and they are not the same number.

- The {outer_pct} prediction interval is two-sided. It runs from the 2.5% quantile to the 97.5% quantile of the crossing weight. Its lower end, {forecast.prediction_low_95.describe()}, is a 97.5% one-sided guarantee, so it is stricter than what was asked for.
- The one-sided {safety_pct} safety ceiling is the 5% quantile, {forecast.safety_ceiling.describe()}. At that weight, {safety_pct} of simulated paths have not yet reached {target:g}%.
- The {inner_pct} interval runs from the 10% to the 90% quantile. Its lower end, {forecast.prediction_low_80.describe()}, is a 90% one-sided guarantee and is therefore looser than the safety ceiling.

Reading the bottom of a two-sided interval as a one-sided guarantee at the same number quietly changes what is being promised. All three appear above so the choice is explicit.

{_reference_position(forecast)}

## Planning

{_planning_section(forecast)}

## Current scan

| Field | Value |
|---|---:|
| Scan date | {forecast.current_date} |
| Bodyweight | {forecast.current_weight_lb:.1f} lb |
| Fat-free mass | {forecast.current_fat_free_mass_lb:.1f} lb |
| Body fat | {forecast.current_body_fat_pct:.2f}% |
| Headroom to {target:g}% | {target - forecast.current_body_fat_pct:.2f} pp |

## Modeled body fat by bodyweight

| Bodyweight | vs scan | Median | {inner_pct} range | {outer_pct} range | Probability under {target:g}% |
|---:|---:|---:|---:|---:|---:|
{_summary_rows(forecast)}

The full curve at {settings.grid_step_lb:g} lb resolution is in `{curve_filename}`.

![Bulk ceiling forecast]({chart_filename})

## The data behind the forecast

Fat-free mass is bodyweight minus fat mass, so body fat is `1 - fat_free_mass / weight`. The model tracks the fraction of each added pound that arrives as fat-free mass, written `k` below.

| # | Interval | Weight | Weight gain | Fat-free gain | k | Block |
|---:|---|---|---:|---:|---:|---:|
{_interval_rows(forecast)}

{block_note}

- Mean of the interval ratios: **{forecast.mean_lean_fraction:.4f}**
- Pooled ratio, total fat-free gain over total weight gain: {forecast.pooled_lean_fraction:.4f}
- Sample standard deviation across intervals: {forecast.lean_fraction_sd:.4f}
- Intervals excluded for a gain below {MINIMUM_INTERVAL_GAIN_LB:g} lb: {excluded_note}

## Formulas

Holding `k` constant over the projected gain:

```text
fat_free_mass(W) = FFM0 + k * (W - W0)
body_fat(W)      = 1 - fat_free_mass(W) / W
crossing weight  = (FFM0 - k * W0) / (1 - t - k)
```

Setting `k = 0` collapses the last line to `FFM0 / (1 - t)`, the constant fat-free mass reference. When `k >= 1 - t`, fat-free mass arrives fast enough that the target is never reached and the crossing weight is infinite.

## Assumptions

| Assumption | Value | Why |
|---|---|---|
| Target body fat | {target:g}% | Requested. |
| Simulations | {settings.simulations:,} | {_simulation_note(forecast)} |
| Seed | {settings.seed} | Fixed so the report reproduces exactly. |
| Measurement error | {settings.measurement_error_pp:g} pp, one standard deviation | DXA-specific between-day body-fat TEM from Velasquez et al. 2026, reported there as 0.37 to 0.38 pp. The wider 0.37 to 1.24 pp range from the same paper spans every method it tested and its upper end is bioimpedance, not DXA. {CONSERVATIVE_MEASUREMENT_ERROR_PP:g} pp is available as a deliberate conservative override. Applied independently to the current scan and to the future scan. |
| Resampling unit | {settings.resample_unit} | Blocks group intervals that share a scan, because their ratios share that scan's error. `interval` treats all intervals as independent and is kept only for comparison. |
| Future-bulk deviation scale | {settings.partition_noise_scale:g} | Multiplier on the resampled interval-to-interval spread of `k`. |
| Extrapolation cap | {forecast.resolved_max_weight_lb:.1f} lb | {_cap_note(forecast)} |
| Bodyweight error | Treated as zero | Scale weight is accurate to a fraction of a pound next to DEXA composition error, and bodyweight is the decision variable rather than an estimate. |
| Population priors | None used | No external body-composition prior is mixed in. Only this scan history is resampled. |
| Prior on the true current value | Flat | With a flat prior, the posterior for the true body fat is a normal centred on the reading, which is what the simulation draws. |

### What each assumption is worth

{_sensitivity_rows(forecast)}

### How uncertainty enters

Each of the {settings.simulations:,} draws combines three things, matching the NIST definition of a prediction interval for a future observation:

1. Parameter uncertainty in `k`. Resample the {forecast.resampling_unit_count} blocks with replacement and take the mean of every interval they contain.
2. Deviation of one future bulk from that mean. Draw one centred residual from the observed intervals. This is the term that makes the result a prediction interval rather than a confidence interval.
3. Measurement error, twice. Once on the current scan that anchors the projection, once on the future scan that would read the result. A scan reading `e` high crosses the target as soon as true body fat reaches `t - e`.

The future-scan error is drawn once per path so each path stays monotone in weight and has one crossing point. The marginal probability at any given weight is identical either way.

### How much of the spread in `k` is scan noise

{_noise_share_note(forecast)}

## Held-out predictive check

{predictive_section}

## Leave-one-out refit sensitivity

This is not validation. Every refit below is scored on data it was fitted to, so it measures how much one interval moves the answer and nothing more. The held-out check above is the part that can fail.

{_jackknife_rows(forecast)}

## Limits

The probabilities are not calibrated, for reasons worth being specific about.

{dependence_note}

`k` is assumed constant across the whole projected gain. In practice partitioning gets worse as body fat rises, so the true crossing weight is probably lower than the median here. The model does not encode that.

Every headline number is extrapolation. The heaviest scan on file is {max(interval.end_weight_lb for interval in forecast.intervals):.1f} lb, and the safety ceiling sits above it.

Censoring is real. {forecast.above_cap_fraction:.1%} of simulated paths cross the target above the {forecast.resolved_max_weight_lb:.1f} lb cap, and {forecast.never_crosses_fraction:.1%} never cross at all. Those paths make the upper ends of both intervals censored rather than missing.

Intervals are not equal in size. They span {min(interval.weight_gain_lb for interval in forecast.intervals):.1f} to {max(interval.weight_gain_lb for interval in forecast.intervals):.1f} lb of gain. The resampling does not weight by size or by elapsed time.

Scans are not perfectly comparable. Hydration, glycogen, food, caffeine, and positioning all move a reading, and the scans behind these intervals were not all taken under matched conditions.

## Sources

- NIST/SEMATECH e-Handbook of Statistical Methods, prediction intervals for a
  future observation: https://itl.nist.gov/div898/handbook/pmd/section1/pmd132.htm
- Velasquez et al. 2026, between-day reliability of body-composition methods.
  The DXA body-fat TEM is 0.37 to 0.38 pp; the 1.24 pp upper end of the
  all-method range is bioimpedance, not DXA:
  https://pubmed.ncbi.nlm.nih.gov/42298959/
- BodySpec DEXA accuracy guide, a vendor claim of roughly +/-0.5 pp
  repeatability under consistent preparation:
  https://www.bodyspec.com/blog/post/bodyspec_dexa_scan_accuracy_guide
"""
