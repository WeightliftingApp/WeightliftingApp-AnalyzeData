# Bulk ceiling forecaster review

A forecaster for the bodyweight at which a target DEXA body-fat reading arrives,
built to answer one question: how heavy can this person bulk and still read under
20% with 95% confidence. Answer on the 2026-08-21 scan: **236.9 lb**, against a
constant fat-free mass reference of 233.2 lb and a median crossing of 252.0 lb.

## Shortcuts

- The forecast reads only the totals CSV. Regional scans carry no information
  about how a bulk partitions bodyweight, and `data/dexa_regions.csv` is not
  present in this worktree anyway, so `scripts/analyze_dexa.py` cannot run here.
  The forecaster needs `date`, `weight_lb`, and `fat_free_mass_lb` and nothing
  else.
- The chart has its own module and its own palette rather than reusing either
  existing chart style. The task defers styling to a later integration pass, and
  the two existing charts do not agree with each other anyway (one is dark, one
  is a light paper style). `src/dexa/forecast_charts.py` takes output paths from
  its caller, so restyling it later touches no maths.
- `scripts/forecast_bulk_ceiling.py` adds `src` to `sys.path`, matching
  `scripts/analyze_dexa.py`. The repo has no editable install.
- I did not compute a probability that accounts for how long a bulk takes. The
  model is entirely in weight space. Time never enters, which means it cannot
  answer "how fast" or "by when".

## Issues found

- **The report originally hardcoded an ordering that is not always true.** The
  first draft asserted that the constant fat-free mass reference sits below both
  modeled figures. A synthetic fixture whose latest scan reads 17.5% body fat,
  close to a 20% target, produced the opposite ordering: the reference landed
  above the 95% safety ceiling. The cause is real, not a rounding artifact. When
  the current reading is near the target, measurement error on that reading alone
  can put the true value nearer the target than the printout says, and the
  modeled ceiling prices that in while the zero-gain calculation does not.
  `_reference_position` now describes the ordering it found and says to take the
  lower of the two. Two tests pin both branches.
- **The observed spread in `k` carries no evidence of real biological
  variation.** At 0.8 pp of assumed scan error and a typical 13.0 lb interval,
  measurement noise alone implies a standard deviation in `k` of 0.187. The five
  intervals actually show 0.133. The measurement-implied figure is larger than
  the total observed figure, so deconvolving would give a negative variance. The
  report states this rather than hiding it. It is the single most important
  honest fact about this dataset and it is computed, not asserted, by
  `measurement_implied_lean_fraction_sd`.
- **The upper end of the two-sided prediction interval is not usable.** The
  unclipped 97.5% draw quantile is 313.1 lb. 18.8% of paths cross above the
  274.8 lb extrapolation cap. Both numbers appear in the report. Clipping without
  saying so would have made the interval look tighter than the model believes.
- **A stray `.artifacts/bulk-check/` directory appeared in the worktree during
  this task** holding a copy of the generated outputs. I did not create it and did
  not delete it, but I added `.artifacts/` to `.gitignore` so it cannot reach a
  commit. It contains DEXA-derived output.

## Ambiguities

- **"95% confidence" is ambiguous, and the ambiguity is expensive.** The task
  asked for the distinction, so the report leads with it. The one-sided 95%
  safety ceiling is the 5% quantile of the crossing weight (236.9 lb). The bottom
  of a two-sided 95% prediction interval is the 2.5% quantile (235.0 lb) and is
  therefore a 97.5% one-sided guarantee. Reading the second as the first costs
  1.9 lb of headroom on this data. Both are in the bottom-line table.
- **"Under 20%" could mean true body fat or what a scan would read.** NIST's
  prediction interval is for a future observation, and a scan reading is the only
  thing that can ever be checked, so the headline models the reading and includes
  future-scan error. A true-value interval would be narrower. Setting
  `--measurement-error-pp 0` produces it: the ceiling moves to 240.4 lb.
- **"Positive-weight historical DEXA intervals" could include a 0.3 lb gain.** A
  ratio computed across a gain that small is almost pure scan noise. Intervals
  below `MINIMUM_INTERVAL_GAIN_LB = 2.0` are separated out and reported rather
  than silently included or silently dropped. On the real record nothing is
  excluded, so this changes no current number.
- **Lean soft tissue or fat-free mass.** Body fat percentage is defined against
  fat mass, so fat-free mass (lean soft tissue plus bone mineral content) is the
  quantity that closes the identity `weight = fat + fat_free`. I checked that
  identity holds to the printed decimal on all nine scans. The existing
  `add_interval_efficiency` uses lean soft tissue for a different purpose and is
  untouched.

## Judgment calls

- **`k`, the fraction of each added pound that arrives as fat-free mass, is the
  single modeled quantity.** It has a closed-form crossing weight, it reduces to
  the constant fat-free mass case at `k = 0`, and it is directly readable off any
  pair of scans. Anything richer would need data the record does not have.
- **The resampling unit is the interval, not the scan.** Each of the five
  intervals is one exchangeable draw. The bootstrap resamples all five with
  replacement and takes the mean, which is the parameter-uncertainty term.
- **A second, separate residual draw makes it a prediction interval.** The
  bootstrap mean alone would give a confidence interval on the long-run `k`, with
  a standard deviation of about 0.059. A future bulk deviates from that mean too.
  Drawing one centred residual from the same five intervals adds that term and
  takes the total to about 0.145. This is the term NIST separates out.
- **Measurement error is parameterized in body-fat percentage points, not in
  pounds of fat-free mass.** The target is stated in percentage points, both
  cited sources report error in percentage points, and the conversion is exact
  (`fat_free = W * (1 - body_fat)`). At 215 lb and 0.8 pp this implies 1.72 lb of
  fat-free error, which is 0.78 kg and sits inside the published 0.26 to 0.90 kg
  fat-free-mass TEM. The two literature figures agree, which is reassuring.
- **0.8 pp is the midpoint of the published 0.37 to 1.24 pp between-day range,
  not BodySpec's 0.5 pp.** BodySpec's figure is a vendor claim under matched
  preparation. The record includes scans taken with 350 mg of caffeine on board
  and scans taken fasted without it, so matched preparation is not what happened.
- **Future-scan error becomes a shifted target.** A scan that reads `e` high
  crosses the target as soon as true body fat reaches `t - e`, so the simulation
  perturbs the target rather than the reading. Same distribution, and it keeps
  the closed form intact.
- **One future-scan error draw per path, not one per weight.** This keeps each
  path monotone in weight and gives it exactly one crossing point. The marginal
  probability at any given weight is unchanged, which the test suite verifies:
  counting uncrossed paths and reading body fat off the paths directly agree to
  within 1e-12, and in practice exactly.
- **A flat prior on the true current body fat.** With a flat prior the posterior
  is a normal centred on the reading, which is what the simulation draws. This is
  a prior, so the report names it in the assumptions table.
- **The extrapolation cap is the current weight plus 60 lb.** The largest bulk in
  the record spans 27.6 lb, so 60 lb is more than twice anything the data covers.
  Draws that cross above the cap are reported at the cap and counted, never
  dropped. `--max-weight-lb` overrides it.
- **Minimum three usable intervals.** Below three the resampled spread rests on a
  single pair of scans and the interval would look far more precise than the data
  supports. The sparse-data warning fires at or below eight.
- **Sensitivity refits run by default.** Leave-one-out and the two zeroed-noise
  runs cost 0.07 s together at 20,000 draws, and they turn three prose claims in
  the report into computed numbers. `with_sensitivity=False` skips them.

## Rejected alternatives

- **A normal-theory prediction interval with a t multiplier.** With five
  observations the t interval is wide and symmetric, and the crossing weight is
  strongly right-skewed because `W*` has `(1 - t - k)` in its denominator.
  Resampling reproduces that skew for free. The 5% quantile is 236.9 lb while the
  95% quantile is 287.4 lb, against a median of 252.0 lb. A symmetric interval
  would be wrong in both directions.
- **Deconvolving measurement noise out of the observed spread in `k`.** The
  arithmetic gives a negative variance on this data, as documented above. The
  model keeps the double-count, which widens the interval, and exposes
  `--partition-noise-scale` so the assumption can be tested rather than trusted.
  Setting it to 0 moves the ceiling to 240.4 lb.
- **A population prior on partitioning ratios.** The task forbids inventing
  priors, and there is no defensible population value for a specific trained
  individual at 25 FFMI. The model uses only this person's scans.
- **Weighting intervals by weight gain or by elapsed time.** The pooled ratio
  (0.4071) and the unweighted mean of interval ratios (0.4119) differ by 0.005,
  so weighting would not move the answer. The unweighted mean is what the
  resampling can treat as exchangeable draws, so that is what it uses. The pooled
  figure is printed as a cross-check.
- **Modeling a declining `k` as body fat rises.** Physiologically real, and it
  would lower the crossing weight. Five intervals cannot identify a slope on `k`,
  and inventing one would be a hidden prior. The report names the omission and
  its direction instead.
- **Making `--output-dir` a required argument.** `scripts/analyze_dexa.py`
  defaults to `outputs/`, so this matches. The generated filenames are gitignored
  under `outputs/bulk-ceiling-*` so the default cannot leak personal data into a
  commit.
- **Reusing `dexa.charts` styling.** The task explicitly defers that to an
  integration pass.

## Formulas

Fat-free mass is bodyweight minus fat mass, so body fat is `1 - FFM / W`.
Holding the partitioning ratio `k` constant over the projected gain:

```text
FFM(W)          = FFM0 + k * (W - W0)
body_fat(W)     = 1 - FFM(W) / W
crossing weight = (FFM0 - k * W0) / (1 - t - k)
```

- `k = 0` gives `W* = FFM0 / (1 - t)`, the constant fat-free mass reference.
  On the current scan, `186.6 / 0.80 = 233.25 lb`.
- `k >= 1 - t` makes the denominator non-positive and the crossing weight
  infinite. Fat-free mass is arriving fast enough that the target never arrives.
- `k >= FFM0 / W0` makes body fat fall as weight rises. Both cases return
  infinity.
- `body_fat(W0) >= t` returns `W0`. The target is already reached.
- Because body fat is monotone in `W` on every path, the probability of still
  reading under target at weight `W` equals the share of paths whose crossing
  weight exceeds `W`. The one-sided safety ceiling is therefore the 5% quantile
  of the crossing weight, and the two-sided 95% interval is the 2.5% to 97.5%
  quantiles of the same array. One simulation, both answers, no chance of them
  disagreeing.

Measurement-implied spread in `k`, used to size the double-count:

```text
sd_measurement(k) = sqrt(2) * (W0 * error_pp / 100) / median_interval_gain
```

## Commands run

```text
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
# numpy 2.5.2, pandas 3.0.5, matplotlib 3.11.1 on Python 3.14.5

MPLBACKEND=Agg PYTHONPATH=src ./venv/bin/python -m unittest tests.test_forecast_bulk_ceiling
# Ran 58 tests, OK

MPLBACKEND=Agg PYTHONPATH=src ./venv/bin/python -m unittest \
  tests.test_analyze_dexa tests.test_analysis_utils tests.test_convert_dexa_xlsx
# Ran 20 tests, OK (no regression in the existing suite)

MPLBACKEND=Agg ./venv/bin/python scripts/forecast_bulk_ceiling.py --output-dir <scratch>/run1
MPLBACKEND=Agg ./venv/bin/python scripts/forecast_bulk_ceiling.py --output-dir <scratch>/run2
# Both runs byte-identical:
#   bulk-ceiling-20pct-2026-08-21.md            0544ec56c4d8ce06112ffdbc6ed758cf383f3d9bc75cd5bcbce3d4cc59ee844d
#   bulk-ceiling-20pct-probability-curve.csv    dcb2125d2dbeb1cbc54d39ca9dd4c8a3ae950fa86b7236a8e090398a7e3eb4f2
#   bulk-ceiling-20pct-forecast.png             c1afb3dafef62640061c3dc864fefd3d4904a6afe78a08827dd22d5d28214a3f
# data/dexa.csv unchanged before and after:
#   ddcb6e5155aa6beffa66fab3eaa8c00aa9a77bccc564440bbfd9728cd1b003df
```

Simulation-count stability, measured on the real record:

```text
n =  5,000   safety ceiling 237.19 lb
n = 20,000   safety ceiling 236.94 lb
n = 80,000   safety ceiling 236.94 lb
```

## Backtesting limits

There is no backtest. Five intervals leave no holdout, and every candidate
holdout scan is also an endpoint of the interval that would have to be dropped.
Leave-one-out refitting is the closest available check and it runs by default:

| Interval dropped | Mean `k` | Safety ceiling |
|---|---:|---:|
| 2022-09-15 to 2023-01-20 | 0.4370 | 237.1 lb |
| 2023-06-14 to 2023-08-25 | 0.4483 | 238.8 lb |
| 2023-08-25 to 2025-03-05 | 0.3719 | 236.3 lb |
| 2025-07-24 to 2026-01-27 | 0.4188 | 236.3 lb |
| 2026-01-27 to 2026-07-10 | 0.3838 | 236.2 lb |

A 2.6 lb spread across five refits is the honest summary of what one scan pair
is worth here. That is smaller than I expected, and it is not evidence that the
model is well calibrated. It only says the mean is stable. The interval width is
driven by the residual term and by measurement error, neither of which
leave-one-out probes.

What would make a real backtest possible: three or four more bulk intervals, at
which point holding out the most recent one and scoring the predicted against the
observed crossing becomes meaningful. At the current scan cadence that is several
years away.

## Edge cases

- Target at or below 0, at or above 100, or non-finite: rejected with a message
  naming the value.
- Target at or below the current reading: rejected, with the current percentage
  and the target both in the message. There is no bulk headroom to forecast.
- Fewer than three usable intervals: rejected, with the minimum and the count
  found. Intervals below the 2.0 lb minimum gain do not count toward it.
- Fewer than two scans, or missing required columns: rejected by
  `extract_bulk_intervals` with the column names.
- Flat intervals (zero weight change) and cuts are skipped, not treated as
  zero-gain bulks.
- Scans arriving out of date order are sorted before pairing.
- `simulations < 1`, negative measurement error, negative noise scale, a
  non-positive grid step, or a cap at or below the current weight: all rejected.
- Non-positive weight or fat-free mass on the latest scan: rejected.
- A path where `k >= 1 - t` never crosses. Those paths are counted as still under
  target at every weight, which is correct, and they show in
  `never_crosses_fraction`. On the real record that fraction is 0.0%.
- A path already over target at the current weight returns the current weight as
  its crossing. On the real record the probability curve starts at 100.0%, but on
  a near-target anchor it starts below 1.0, and a test pins that.
- The upper end of the prediction interval can exceed the extrapolation cap. It
  is reported as censored with the unclipped quantile alongside, never silently
  clipped.
- A fractional target such as 17.5% produces the filename slug `17-5pct`.

## Next steps

- Apply the shared chart style to `src/dexa/forecast_charts.py` in the same pass
  that restyles `src/dexa/charts.py`. The module takes output paths from its
  caller and holds no maths, so restyling is contained.
- Consider a cut counterpart: the lightest weight at which a target reads, using
  the four negative-weight intervals. The closed form is the same equation with
  the sign of the gain flipped, but the four cut intervals partition differently
  from the five bulks, so it needs its own pool rather than a shared one.
- Re-run after the next scan. Each new bulk interval is a 20% increase in the
  resampling pool, and the sparse-data warning clears at nine.
- If a scan is ever repeated within a few days under matched preparation, use the
  pair to replace the assumed 0.8 pp with a measured scanner-specific figure.
  That single change would remove the largest unverified assumption in the model.
- The 2025-03-05 scan sits 18 months after the one before it, and that interval
  produces the highest `k` in the record (0.572). It is worth checking whether
  that scan was taken under comparable conditions before treating it as one
  exchangeable unit alongside the others.
