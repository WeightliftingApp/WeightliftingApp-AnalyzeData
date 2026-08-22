# Bulk ceiling forecaster review

An engineering review of `src/dexa/forecast*.py` and
`scripts/forecast_bulk_ceiling.py`. The forecaster estimates the bodyweight at
which a target DEXA body-fat reading arrives and separates the one-sided weight
that keeps a stated probability of staying under target from the two-sided
prediction interval for the crossing weight.

No personal measurements, dates, or results appear here. Run notes for a
specific scan history belong in the ignored `.artifacts/` directory alongside the
generated report, which carries every figure with its own assumptions attached.

## Shortcuts

- The forecast reads only the totals CSV. Regional scans carry no information
  about how a bulk partitions bodyweight, so `date`, `weight_lb`, and
  `fat_free_mass_lb` are the whole input contract.
- The chart module has its own palette rather than reusing either existing chart
  style. Chart styling is being integrated separately.
  `src/dexa/forecast_charts.py` takes output paths from its caller, so restyling
  it touches no maths.
- `scripts/forecast_bulk_ceiling.py` adds `src` to `sys.path`, matching
  `scripts/analyze_dexa.py`. The repo has no editable install.
- The model is entirely in weight space. Time enters only through the optional
  planning rate, which converts headroom into weeks after the fact. Nothing in
  the forecast itself knows how long a bulk takes.

## Issues found

- **A cap could produce a false exact headline.** The first implementation
  clamped every quantile to the extrapolation cap with `min(raw, cap)`, so a low
  cap printed the cap itself as though the model had identified it. Quantiles now
  travel as `WeightEstimate`, which keeps the raw draw beside the cap and forces
  every caller to ask whether the figure was identified. Rendering distinguishes
  three cases: an exact value, "above `cap`" with the unclipped quantile shown,
  and "not identified below `cap`" when enough paths never cross at all. Tests
  drive a cap below the true answer and assert no bare cap value reaches the
  report as a headline.
- **Measurement error was sourced from the wrong row of the paper.** The default
  was 0.8 pp, taken as the midpoint of a 0.37 to 1.24 pp range, and the paper was
  attributed to the wrong first author. That range spans every method the study
  tested and its upper end is bioimpedance. The DXA-specific between-day
  body-fat figure is 0.37 to 0.38 pp. The default is now 0.38 pp, the citation
  names Velasquez et al., and `CONSERVATIVE_MEASUREMENT_ERROR_PP` keeps 0.8 pp
  reachable as a deliberate opt-in rather than a silent baseline.
- **A conclusion did not survive the corrected input.** At 0.8 pp the
  measurement-implied spread in the partitioning ratio exceeded the observed
  spread, and the report concluded that the observed variation was
  indistinguishable from scan noise. At the DXA-specific default the implied
  spread is well below the observed one, so real variation is present. The report
  now computes the noise share and the deconvolved spread and states both, and a
  test asserts the old claim is absent.
- **Interval ratios are not independent.** Consecutive bulks that meet at the
  same scan inherit that scan's measurement error in both ratios. Resampling them
  as separate units counts one scan's noise twice. `group_intervals_into_blocks`
  merges scan-linked intervals and the block is now the default resampling unit,
  which reduces the effective sample size and widens the interval. The limits
  section names the dependence directly rather than implying independence, and
  `--resample-unit interval` keeps the old behaviour reachable for comparison.
- **Refit sensitivity was described as backtesting.** Leave-one-out refits are
  scored on data they were fitted to and cannot fail. They are now labelled as
  sensitivity, and a genuine held-out score sits beside them.
- **Report prose asserted facts about the default run.** Three sentences were
  unconditional: that quantiles were stable at four times the simulation count,
  that the cap was the current weight plus the default margin, and that the
  interval count was sparse. Each now branches on whether the corresponding knob
  was actually left at its default, and the fold-count and shared-scan sentences
  interpolate the real numbers instead of describing one particular record.
- **The report hardcoded an ordering that is not always true.** An early draft
  asserted the constant fat-free mass reference sits below both modeled figures.
  When the current reading sits close to the target, measurement error on that
  reading can pull the modeled ceiling below the zero-gain calculation.
  `_reference_position` describes the ordering it found and says to take the
  lower of the two. Tests pin both branches.

## Ambiguities

- **"95% confidence" is ambiguous, and the ambiguity is expensive.** The
  one-sided safety ceiling is the 5% quantile of the crossing weight. The bottom
  of a two-sided 95% prediction interval is the 2.5% quantile and is therefore a
  97.5% one-sided guarantee. The report carries the one-sided ceiling, both
  two-sided intervals, and a paragraph on why they differ, so the reader picks
  rather than guesses.
- **"Under target" could mean true body fat or what a scan would read.** NIST's
  prediction interval is for a future observation, and a reading is the only
  thing that can ever be checked, so the headline models the reading and includes
  future-scan error. `--measurement-error-pp 0` produces the latent-value
  version.
- **"Positive-weight interval" could include a fractional gain.** A ratio across
  a tiny gain is almost pure scan noise, so `MINIMUM_INTERVAL_GAIN_LB` separates
  those out and the report lists what was excluded rather than dropping it
  silently.
- **Lean soft tissue or fat-free mass.** Body fat is defined against fat mass, so
  fat-free mass is the quantity that closes `weight = fat + fat_free`. The
  existing `add_interval_efficiency` uses lean soft tissue for a different
  purpose and is untouched.
- **Whether a supplied planning weight should re-anchor the model.** It does not.
  Re-anchoring would require assuming a partitioning ratio for the gain since the
  scan, which is the very thing being estimated. A planning weight moves only
  where headroom is measured from, and a gap beyond
  `PLANNING_WEIGHT_TOLERANCE_LB` is rejected because the composition behind the
  ceiling would be stale.

## Judgment calls

- The partitioning ratio `k` is the single modeled quantity. It has a closed-form
  crossing weight, it reduces to the constant fat-free mass case at `k = 0`, and
  it is readable off any pair of scans.
- A bootstrap of the mean gives parameter uncertainty. A second, separate
  residual draw gives the deviation of one future bulk from that mean, which is
  what makes the result a prediction interval rather than a confidence interval.
- Measurement error is parameterized in body-fat percentage points, because the
  target is stated in percentage points and the cited sources report error that
  way. The conversion to pounds of fat-free mass is exact.
- Future-scan error becomes a shifted target. A scan reading `e` high crosses as
  soon as the true value reaches `t - e`, which keeps the closed form intact.
- One future-scan error draw per path, not one per weight. Each path stays
  monotone and has exactly one crossing. The marginal probability at any weight
  is unchanged, and a test verifies that counting uncrossed paths and reading
  body fat off the paths agree to within 1e-12.
- A flat prior on the true current reading, which makes the posterior a normal
  centred on the reading. This is a prior, so the assumptions table names it.
- Held-out folds are seeded from the run seed plus a per-fold offset, so the
  score is reproducible and no two folds share draws.
- Sensitivity refits and the held-out score both run by default. Together they
  cost a fraction of a second and they turn several prose claims into computed
  numbers.

## Rejected alternatives

- **A normal-theory interval with a t multiplier.** The crossing weight is
  strongly right-skewed because `(1 - t - k)` sits in its denominator. Resampling
  reproduces that skew; a symmetric interval would be wrong at both ends.
- **Deconvolving measurement noise out of the residual term.** The estimate is
  unstable at this sample size and goes negative at conservative error settings.
  The model keeps the double-count, which widens the interval, reports the size
  of it, and exposes `--partition-noise-scale` so the assumption can be tested.
- **A population prior on partitioning ratios.** There is no defensible
  population value for a specific trained individual, and inventing one would
  hide the sparseness rather than report it.
- **Weighting intervals by gain or elapsed time.** The pooled ratio and the
  unweighted mean sit close together, and the unweighted mean is what the
  bootstrap can treat as exchangeable units. Both are printed.
- **Modeling a declining `k` as body fat rises.** Physiologically real and it
  would lower the crossing weight, but a handful of intervals cannot identify a
  slope, and assuming one would be a hidden prior. The limits section names the
  omission and its direction.
- **Inferring a bulk rate from a weight log.** The log is a record of the past,
  not a statement of intent, and fitting a trend to it would put a silent
  assumption behind a duration estimate. Without an explicit rate no duration is
  reported at all.
- **Making `--output-dir` required.** It defaults to `outputs/`, matching
  `scripts/analyze_dexa.py`. Generated filenames are gitignored so the default
  cannot leak derived personal data into a commit.

## Formulas

Fat-free mass is bodyweight minus fat mass, so body fat is `1 - FFM / W`.
Holding the partitioning ratio `k` constant over the projected gain:

```text
FFM(W)          = FFM0 + k * (W - W0)
body_fat(W)     = 1 - FFM(W) / W
crossing weight = (FFM0 - k * W0) / (1 - t - k)
```

- `k = 0` gives `W* = FFM0 / (1 - t)`, the constant fat-free mass reference.
- `k >= 1 - t` makes the denominator non-positive and the crossing weight
  infinite. Fat-free mass arrives fast enough that the target never does.
- `k >= FFM0 / W0` makes body fat fall as weight rises. Also infinite.
- `body_fat(W0) >= t` returns `W0`.
- Body fat is monotone in `W` on every path, so the probability of still reading
  under target at weight `W` equals the share of paths whose crossing weight
  exceeds `W`. The one-sided safety ceiling is the `1 - confidence` quantile of
  the crossing weight, and both two-sided intervals are quantiles of the same
  array. One simulation, every answer, no chance of them disagreeing.

Measurement-implied spread in `k`, used to size the double-count:

```text
sd_measurement(k) = sqrt(2) * (W0 * error_pp / 100) / median_interval_gain
```

The share of observed variance attributable to scan noise is the square of the
ratio of that figure to the observed spread. What remains after removing it is
`sqrt(observed^2 - implied^2)`, or undefined when the implied figure is larger.

## Commands

```text
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt

MPLBACKEND=Agg PYTHONPATH=src ./venv/bin/python -m unittest \
  tests.test_forecast_bulk_ceiling

MPLBACKEND=Agg PYTHONPATH=src ./venv/bin/python -m unittest \
  tests.test_analyze_dexa tests.test_analysis_utils tests.test_convert_dexa_xlsx

MPLBACKEND=Agg ./venv/bin/python scripts/forecast_bulk_ceiling.py \
  --output-dir <directory>
```

Determinism is checked by running the CLI twice into separate directories and
comparing SHA-256 of all three outputs, and by hashing the input CSV before and
after to confirm it is never written.

## Validation and its limits

Two distinct checks ship, and conflating them would be the easy mistake:

- **Held-out predictive score.** Each bulk is held out in turn. The model
  resamples the remaining bulks only, anchors on the held-out bulk's own starting
  scan, and predicts what a scan would read at that bulk's actual ending weight.
  The observed reading is placed inside that predictive distribution, and
  coverage is reported at both the inner and outer levels alongside the median
  absolute error in percentage points. This can fail.
- **Leave-one-out refit sensitivity.** Each interval is dropped and the forecast
  refitted. Every refit is scored on data it was fitted to, so this measures how
  much one interval moves the answer and nothing else. It cannot fail, and the
  report says so.

Neither validates the crossing weight itself, because no scan in the record sits
near the projected ceiling. The held-out score validates body-fat prediction at
observed end weights, which is the same model evaluated inside the data range.

Coverage at a handful of folds cannot distinguish a well calibrated interval from
an overwide one, and the folds inherit the same shared-scan dependence as the
training data, so the numbers are optimistic. The median absolute error is the
part worth reading.

A real backtest needs enough bulk intervals to hold out the most recent one and
score a predicted crossing against an observed one. At typical scan cadence that
is years away.

## Edge cases

- Target at or below 0, at or above 100, or non-finite: rejected with the value.
- Target at or below the current reading: rejected, with both figures named.
- Fewer usable intervals than `MINIMUM_BULK_INTERVALS`: rejected with the count
  found. Intervals below the minimum gain do not count toward it.
- Fewer than two scans, or missing required columns: rejected with column names.
- Flat intervals and cuts are skipped, not treated as zero-gain bulks.
- Scans arriving out of date order are sorted before pairing.
- Invalid simulation count, negative error, negative noise scale, non-positive
  grid step, unknown resample unit, or a cap at or below the current weight: all
  rejected.
- A path where `k >= 1 - t` never crosses. Counted as still under target at every
  weight, and surfaced as `never_crosses_fraction`.
- A path already over target at the current weight crosses at the current weight,
  so the probability curve can start below 1.0 when scan error is large relative
  to the headroom left. A test pins both directions.
- Quantiles above the cap are censored with the unclipped value shown. Quantiles
  that are infinite report as not identified. The probability at the cap is still
  reported either way.
- Planning weight non-positive, below the measured fat-free mass, or beyond the
  tolerance from the anchoring scan: rejected with the reason.
- Planning rate zero or negative: rejected. Absent: no duration reported.
- Planning weight already past the ceiling: headroom goes negative and duration
  reports zero rather than a negative number of weeks.
- Weight log with zero or missing weekly averages: those rows are dropped, and an
  empty result is rejected rather than silently averaged.
- A fractional target produces a filesystem-safe filename slug.

## Next steps

- Fold `src/dexa/forecast_charts.py` into the shared chart style alongside
  `src/dexa/charts.py`. The module holds no maths.
- Consider a cut counterpart, the lightest weight at which a target reads. The
  closed form is the same equation with the sign of the gain flipped, but cut
  intervals partition differently from bulks and need their own pool.
- If a scan is ever repeated within a few days under matched preparation, use the
  pair to replace the assumed error with a measured scanner-specific figure. That
  would remove the largest unverified assumption in the model.
- Revisit the block grouping if scan cadence changes. It currently links
  intervals that share an endpoint scan; a record with many closely spaced scans
  may warrant linking on proximity in time as well.
