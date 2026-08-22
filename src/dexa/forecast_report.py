"""Pure Markdown rendering for the bulk-ceiling forecast."""

from __future__ import annotations

import numpy as np

from .forecast import (
    MINIMUM_INTERVAL_GAIN_LB,
    PREDICTION_COVERAGE,
    SAFETY_CONFIDENCE,
    SPARSE_INTERVAL_THRESHOLD,
    BulkCeilingForecast,
)

# Weights the summary table reports on, relative to the current scan.
SUMMARY_OFFSETS_LB = (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0)


def _probability_at(forecast: BulkCeilingForecast, weight_lb: float) -> float:
    index = int(np.abs(forecast.weight_grid_lb - weight_lb).argmin())
    return float(forecast.probability_under_target[index])


def _body_fat_at(forecast: BulkCeilingForecast, weight_lb: float) -> tuple[float, float, float]:
    index = int(np.abs(forecast.weight_grid_lb - weight_lb).argmin())
    return (
        float(forecast.body_fat_median_pct[index]),
        float(forecast.body_fat_low_pct[index]),
        float(forecast.body_fat_high_pct[index]),
    )


def _interval_rows(forecast: BulkCeilingForecast) -> str:
    rows = []
    for position, interval in enumerate(forecast.intervals, start=1):
        rows.append(
            f"| {position} | {interval.start_date} to {interval.end_date} | "
            f"{interval.start_weight_lb:.1f} to {interval.end_weight_lb:.1f} lb | "
            f"{interval.weight_gain_lb:+.1f} lb | "
            f"{interval.fat_free_gain_lb:+.1f} lb | "
            f"{interval.lean_fraction:.3f} |"
        )
    return "\n".join(rows)


def _summary_rows(forecast: BulkCeilingForecast) -> str:
    rows = []
    for offset in SUMMARY_OFFSETS_LB:
        weight = forecast.current_weight_lb + offset
        if weight > forecast.resolved_max_weight_lb:
            continue
        probability = _probability_at(forecast, weight)
        median, low, high = _body_fat_at(forecast, weight)
        rows.append(
            f"| {weight:.1f} lb | {offset:+.0f} lb | {median:.1f}% | "
            f"{low:.1f}% to {high:.1f}% | {probability:.1%} |"
        )
    return "\n".join(rows)


def _upper_bound_text(forecast: BulkCeilingForecast) -> str:
    if not forecast.prediction_high_censored:
        return f"{forecast.prediction_high_lb:.1f} lb"
    return (
        f"above {forecast.resolved_max_weight_lb:.1f} lb "
        f"(unclipped draw quantile {forecast.prediction_high_raw_lb:.1f} lb)"
    )


def _reference_position(forecast: BulkCeilingForecast) -> str:
    """Say where the constant fat-free mass reference landed against the model.

    It is usually the strictest of the three, because assuming zero fat-free
    gain is pessimistic. It is not always. When the current reading sits close
    to the target, measurement error on that reading can pull the modeled
    safety ceiling below it.
    """
    reference = forecast.constant_ffm_ceiling_lb
    opening = (
        f"The constant fat-free mass reference sits at {reference:.1f} lb. It "
        "needs no model, no resampling, and no measurement-error assumption."
    )
    if reference <= forecast.prediction_low_lb:
        return (
            f"{opening} Here it is the strictest of the three figures, which is "
            "the usual case and the reason it is included. When the modeled "
            "numbers feel too clever, this is the one to fall back on."
        )
    if reference <= forecast.safety_ceiling_lb:
        return (
            f"{opening} Here it lands below the "
            f"{SAFETY_CONFIDENCE:.0%} safety ceiling but above the bottom of "
            "the prediction interval, so it is the middle of the three."
        )
    return (
        f"{opening} Here it lands **above** the {SAFETY_CONFIDENCE:.0%} safety "
        f"ceiling of {forecast.safety_ceiling_lb:.1f} lb, so it is not the "
        "conservative figure this time. That happens when the current reading "
        "is close to the target: measurement error on that reading alone can "
        "put the true value nearer the target than the printout says, and the "
        "modeled ceiling prices that in while the constant fat-free mass "
        "calculation does not. Take the lower of the two."
    )


def _sensitivity_rows(forecast: BulkCeilingForecast) -> str:
    """Show the safety ceiling with each noise term switched off."""
    sensitivity = forecast.sensitivity
    if sensitivity is None:
        return "Sensitivity refits were not run for this report."
    baseline = forecast.safety_ceiling_lb
    rows = [
        "| Run | Safety ceiling | Shift |",
        "|---|---:|---:|",
        f"| Headline, every term on | {baseline:.2f} lb | |",
        f"| Future-bulk deviation off (`--partition-noise-scale 0`) | "
        f"{sensitivity.zero_partition_noise_lb:.2f} lb | "
        f"{sensitivity.zero_partition_noise_lb - baseline:+.2f} lb |",
        f"| Measurement error off (`--measurement-error-pp 0`) | "
        f"{sensitivity.zero_measurement_error_lb:.2f} lb | "
        f"{sensitivity.zero_measurement_error_lb - baseline:+.2f} lb |",
    ]
    return "\n".join(rows)


def _backtest_note(forecast: BulkCeilingForecast) -> str:
    """Describe what leave-one-out refitting does, since no holdout exists."""
    base = (
        f"With {forecast.interval_count} intervals there is no holdout to score "
        "against, so nothing here has been validated against unseen data."
    )
    jackknife = forecast.jackknife
    if jackknife is None:
        return base
    lowest = min(jackknife.safety_ceiling_lb)
    highest = max(jackknife.safety_ceiling_lb)
    return (
        f"{base} Leave-one-interval-out refits are the closest available check. "
        f"Dropping any single interval moves the mean `k` by up to "
        f"{jackknife.lean_fraction_spread:.3f} and lands the safety ceiling "
        f"between {lowest:.1f} lb and {highest:.1f} lb, a spread of "
        f"{jackknife.safety_ceiling_spread_lb:.1f} lb. That spread is the honest "
        "summary of how much one scan pair is worth here."
    )


def _no_noise_note(forecast: BulkCeilingForecast) -> str:
    """State where the safety ceiling lands with the future-bulk term switched off."""
    sensitivity = forecast.sensitivity
    if sensitivity is None:
        return "a higher weight; rerun with the flag to see where"
    shift = sensitivity.zero_partition_noise_lb - forecast.safety_ceiling_lb
    return (
        f"{sensitivity.zero_partition_noise_lb:.1f} lb, {shift:+.1f} lb from the "
        "headline figure"
    )  # the same shift the sensitivity table above reports


def render_markdown(
    forecast: BulkCeilingForecast,
    chart_filename: str = "bulk-ceiling-forecast.png",
    curve_filename: str = "bulk-ceiling-probability-curve.csv",
) -> str:
    """Render the forecast report without reading or writing files."""
    settings = forecast.assumptions
    target = settings.target_body_fat_pct
    safety_pct = f"{SAFETY_CONFIDENCE:.0%}"
    coverage_pct = f"{PREDICTION_COVERAGE:.0%}"

    warning = (
        f"> **Sparse data warning.** This forecast rests on "
        f"**{forecast.interval_count} positive-weight DEXA intervals**. That is "
        f"below the {SPARSE_INTERVAL_THRESHOLD} intervals this report treats as "
        "the point where resampling starts to behave. Every interval is one "
        "resampling unit, so a single unusual bulk moves the whole answer. Treat "
        "the numbers below as an ordering of options, not as calibrated "
        "probabilities.\n>\n"
        "> This is decision support built from personal scan history. It is not "
        "medical advice."
        if forecast.is_sparse
        else "> This is decision support built from personal scan history. It is "
        "not medical advice."
    )

    excluded_note = (
        "None. Every positive-weight interval cleared the "
        f"{MINIMUM_INTERVAL_GAIN_LB:g} lb minimum gain."
        if not forecast.excluded_intervals
        else ", ".join(
            f"{interval.start_date} to {interval.end_date} "
            f"({interval.weight_gain_lb:+.1f} lb)"
            for interval in forecast.excluded_intervals
        )
    )

    gains = [interval.weight_gain_lb for interval in forecast.intervals]
    smallest_gain_lb = min(gains)
    largest_gain_lb = max(gains)
    typical_gain_lb = float(np.median(gains))
    heaviest_scan_lb = max(
        interval.end_weight_lb for interval in forecast.intervals
    )
    heaviest_scan_lb = max(heaviest_scan_lb, forecast.current_weight_lb)

    backtest_note = _backtest_note(forecast)
    no_noise_note = _no_noise_note(forecast)
    sensitivity_rows = _sensitivity_rows(forecast)
    reference_position = _reference_position(forecast)

    censoring_note = (
        f"{forecast.above_cap_fraction:.1%} of simulated paths cross the target "
        f"above the {forecast.resolved_max_weight_lb:.1f} lb extrapolation cap, and "
        f"{forecast.never_crosses_fraction:.1%} never cross at all. Those paths are "
        "reported at the cap rather than dropped, so the upper end of the interval "
        "is censored, not missing."
    )

    return f"""# Bulk ceiling forecast, {target:g}% body fat

Modeled from the {forecast.current_date} DEXA scan. All figures below are modeled estimates, not measurements.

{warning}

## Bottom line

| Figure | Weight | What it means |
|---|---:|---|
| Constant fat-free mass reference | **{forecast.constant_ffm_ceiling_lb:.1f} lb** | Deterministic. Where {target:g}% arrives if not one further ounce of fat-free mass is gained. No simulation involved. |
| One-sided {safety_pct} safety ceiling | **{forecast.safety_ceiling_lb:.1f} lb** | Heaviest weight where the model still gives at least a {safety_pct} chance that a scan reads under {target:g}%. |
| Median crossing weight | {forecast.median_crossing_lb:.1f} lb | Half the simulated paths cross {target:g}% below this weight. |
| Two-sided {coverage_pct} prediction interval | {forecast.prediction_low_lb:.1f} lb to {_upper_bound_text(forecast)} | Central {coverage_pct} of simulated crossing weights. |

The answer to "how heavy can I bulk and stay under {target:g}% with {safety_pct} confidence" is **{forecast.safety_ceiling_lb:.1f} lb**, which is {forecast.headroom_lb:+.1f} lb from the current {forecast.current_weight_lb:.1f} lb scan.

## Why the two {coverage_pct} numbers differ

The {safety_pct} safety ceiling and the bottom of the {coverage_pct} prediction interval answer different questions, and they are not the same number.

- The **{coverage_pct} prediction interval** is two-sided. It runs from the 2.5% quantile to the 97.5% quantile of the crossing weight. Its lower end, {forecast.prediction_low_lb:.1f} lb, is a 97.5% one-sided guarantee, so it is stricter than what was asked for.
- The **one-sided {safety_pct} safety ceiling** is the 5% quantile, {forecast.safety_ceiling_lb:.1f} lb. At that weight, {safety_pct} of simulated paths have not yet reached {target:g}%.

Reading the bottom of a two-sided {coverage_pct} interval as "the {safety_pct} safe weight" quietly buys {forecast.safety_ceiling_lb - forecast.prediction_low_lb:.1f} lb of extra caution. Both figures appear above so the choice is explicit.

{reference_position}

## Current scan

| Field | Value |
|---|---:|
| Scan date | {forecast.current_date} |
| Bodyweight | {forecast.current_weight_lb:.1f} lb |
| Fat-free mass | {forecast.current_fat_free_mass_lb:.1f} lb |
| Body fat | {forecast.current_body_fat_pct:.2f}% |
| Headroom to {target:g}% | {target - forecast.current_body_fat_pct:.2f} pp |

## Modeled body fat by bodyweight

| Bodyweight | vs current | Median body fat | {coverage_pct} range | Probability under {target:g}% |
|---:|---:|---:|---:|---:|
{_summary_rows(forecast)}

The full curve at {settings.grid_step_lb:g} lb resolution is in `{curve_filename}`.

![Bulk ceiling forecast]({chart_filename})

## The data behind the forecast

Fat-free mass is bodyweight minus fat mass, so body fat is `1 - fat_free_mass / weight`. The model tracks the fraction of each added pound that arrives as fat-free mass, written `k` below.

| # | Interval | Weight | Weight gain | Fat-free gain | k |
|---:|---|---|---:|---:|---:|
{_interval_rows(forecast)}

- Mean of the interval ratios: **{forecast.mean_lean_fraction:.4f}** (this is what the resampling draws from)
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
| Simulations | {settings.simulations:,} | Quantiles move by less than 0.1 lb between {settings.simulations:,} and four times that count. |
| Seed | {settings.seed} | Fixed so the report reproduces exactly. |
| Measurement error | {settings.measurement_error_pp:g} pp, one standard deviation | Midpoint of the 0.37 to 1.24 pp between-day body-fat TEM reported by the 2026 reliability study. Applied independently to the current scan and to the future scan. |
| Future-bulk deviation scale | {settings.partition_noise_scale:g} | Multiplier on the resampled interval-to-interval spread of `k`. |
| Extrapolation cap | {forecast.resolved_max_weight_lb:.1f} lb | Current weight plus 60 lb, more than twice the largest bulk in the record. |
| Bodyweight error | Treated as zero | Scale weight is accurate to a fraction of a pound next to DEXA composition error, and bodyweight is the decision variable rather than an estimate. |
| Population priors | None used | No external body-composition prior is mixed in. Only this scan history is resampled. |
| Prior on the true current value | Flat | With a flat prior, the posterior for the true body fat is a normal centred on the reading, which is what the simulation draws. |

### What each assumption is worth

{sensitivity_rows}

### How uncertainty enters

Each of the {settings.simulations:,} draws combines three things, matching the NIST definition of a prediction interval for a future observation:

1. **Parameter uncertainty in `k`.** Resample the {forecast.interval_count} intervals with replacement and take their mean.
2. **Deviation of one future bulk from that mean.** Draw one centred residual from the same intervals. This is the term that makes the result a prediction interval rather than a confidence interval.
3. **Measurement error, twice.** Once on the current scan that anchors the projection, once on the future scan that would read the result. A scan reading `e` high crosses the target as soon as true body fat reaches `t - e`.

The future-scan error is drawn once per path so each path stays monotone in weight and has one crossing point. The marginal probability at any given weight is identical either way.

### Known conservatism

The observed `k` values are each computed from two DEXA readings, so their spread already contains measurement noise. Step 2 above resamples that spread and step 3 adds measurement error again. That double-counts, and it widens the interval rather than narrowing it.

The size of the double-count is worth stating plainly. At {settings.measurement_error_pp:g} pp of scan error and a typical {typical_gain_lb:.1f} lb interval, scan noise alone implies a standard deviation in `k` of **{forecast.measurement_implied_lean_fraction_sd:.3f}**. That is larger than the **{forecast.lean_fraction_sd:.3f}** actually observed across the {forecast.interval_count} intervals. Read literally, the interval-to-interval variation in `k` is consistent with pure scan noise, and there is no evidence in this record of real variation in how this body partitions a bulk. Subtracting one variance from the other would give a negative number, which is why the model does not try. `--partition-noise-scale 0` tests the other end and moves the safety ceiling to {no_noise_note}.

## Limits

- **Not backtested.** {backtest_note}
- **`k` is assumed constant across the whole projected gain.** In practice partitioning gets worse as body fat rises, so the true crossing weight is probably lower than the median here. The model does not encode that.
- **Linear extrapolation past the record.** The heaviest scan on file is {heaviest_scan_lb:.1f} lb. Every figure above {heaviest_scan_lb:.1f} lb is extrapolation, and that includes all four headline numbers.
- **Censoring.** {censoring_note}
- **Intervals are not equal in size.** They span {smallest_gain_lb:.1f} to {largest_gain_lb:.1f} lb of gain. The resampling treats each as one exchangeable unit and does not weight by size or by elapsed time.
- **Scan-to-scan comparability.** Hydration, glycogen, food, caffeine, and positioning all move a reading. Some intervals bridge scans taken under different fasting and caffeine conditions.

## Sources

- NIST/SEMATECH e-Handbook of Statistical Methods, prediction intervals for a
  future observation: https://itl.nist.gov/div898/handbook/pmd/section1/pmd132.htm
- BodySpec DEXA accuracy guide, roughly +/-0.5 pp repeatability under consistent
  preparation: https://www.bodyspec.com/blog/post/bodyspec_dexa_scan_accuracy_guide
- 2026 reliability study, between-day body-fat TEM of 0.37 to 1.24 pp and fat or
  fat-free mass TEM of 0.26 to 0.90 kg: https://pubmed.ncbi.nlm.nih.gov/42298959/
"""
