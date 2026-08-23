"""Forecast the bodyweight at which a target DEXA body-fat reading is reached.

Every function here is pure. Nothing reads or writes files, and every random
draw comes from a seeded generator, so a given input plus seed always produces
the same output.

Model
-----
A DEXA scan splits bodyweight into fat mass and fat-free mass (FFM), so

    body_fat_fraction(W) = 1 - FFM(W) / W

During a bulk, some fraction ``k`` of each added pound arrives as fat-free
mass. Holding ``k`` constant over the projected gain,

    FFM(W) = FFM0 + k * (W - W0)

Setting ``body_fat_fraction(W) = t`` and solving for W gives the crossing
weight in closed form:

    W* = (FFM0 - k * W0) / (1 - t - k)

``k = 0`` reduces this to ``W* = FFM0 / (1 - t)``, the constant-FFM reference.
``k >= 1 - t`` means fat-free mass arrives fast enough that the target is never
reached, and the crossing weight is infinite.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import numpy as np
import pandas as pd

# Target the user asked about: the heaviest bulk that still reads under 20%.
DEFAULT_TARGET_BODY_FAT_PCT = 20.0

# Simulation defaults. The seed is fixed so reports are reproducible.
DEFAULT_SIMULATIONS = 20_000
DEFAULT_SEED = 20260821

# One-standard-deviation DEXA body-fat measurement error, in percentage points.
# Velasquez et al. 2026 (PMID 42298959) report between-day body-fat TEM by
# method. The DXA figures are 0.37 to 0.38 pp. The wider 0.37 to 1.24 pp range
# quoted from that paper spans every method it tested, and the 1.24 pp upper end
# is bioimpedance, not DXA, so using it here would import another instrument's
# noise. 0.38 pp is the DXA-specific upper end and is the default.
DEFAULT_MEASUREMENT_ERROR_PP = 0.38

# An explicitly conservative opt-in, roughly the midpoint of the all-method
# range and above BodySpec's own +/-0.5 pp vendor claim. Not DXA-specific.
# Pass it deliberately via --measurement-error-pp to widen every interval.
CONSERVATIVE_MEASUREMENT_ERROR_PP = 0.8

# Multiplier on the resampled interval-to-interval deviation of k. 1.0 uses the
# observed spread as-is. See `simulate_crossing_weights` for why that is
# deliberately conservative.
DEFAULT_PARTITION_NOISE_SCALE = 1.0

# Consecutive bulks can share an endpoint scan, and when they do their two
# ratios share that scan's measurement error. Resampling those as independent
# units would count one scan's noise twice and understate the spread, so blocks
# of scan-linked intervals are the default resampling unit. "interval" treats
# every interval as independent and is kept only for comparison.
RESAMPLE_UNIT_BLOCK = "block"
RESAMPLE_UNIT_INTERVAL = "interval"
RESAMPLE_UNITS = (RESAMPLE_UNIT_BLOCK, RESAMPLE_UNIT_INTERVAL)
DEFAULT_RESAMPLE_UNIT = RESAMPLE_UNIT_BLOCK

# How far above the current scan the forecast is allowed to run. The largest
# single bulk in this record is about 28 lb of gain, so 60 lb is already more
# than twice anything the data covers. Quantiles that land above the cap are
# reported as censored, never clamped to the cap and printed as if exact.
DEFAULT_EXTRAPOLATION_MARGIN_LB = 60.0

# Resolution of the reported probability curve.
DEFAULT_GRID_STEP_LB = 0.5

# Intervals with a tiny weight gain produce a ratio dominated by scan noise, so
# they are excluded from the resampling pool and listed in the report.
MINIMUM_INTERVAL_GAIN_LB = 2.0

# Below three usable intervals the resampled spread is degenerate or rests on a
# single pair of scans, which would make the interval look far more precise
# than the data supports.
MINIMUM_BULK_INTERVALS = 3

# At or below this count the report leads with a sparse-data warning.
SPARSE_INTERVAL_THRESHOLD = 8

# One-sided confidence for the "still under target" safety ceiling.
SAFETY_CONFIDENCE = 0.95

# Two-sided coverages reported for the crossing weight. The outer pair is the
# headline; the inner pair is narrower and easier to reason about day to day.
PREDICTION_COVERAGE = 0.95
PREDICTION_COVERAGE_INNER = 0.80

# A planning bodyweight far from the scan that anchors the model would silently
# mis-anchor the answer, because the forecast never re-derives composition from
# the planning weight. Beyond this gap the input is rejected and a fresh scan is
# the honest fix.
PLANNING_WEIGHT_TOLERANCE_LB = 25.0

# Weekly averages used when smoothing a weight log into one current bodyweight.
DEFAULT_WEIGHT_LOG_WEEKS = 4

CURRENT_SCAN_COLUMNS = ("date", "weight_lb", "fat_free_mass_lb")
WEIGHT_LOG_COLUMNS = ("Week of", "Average")


@dataclass(frozen=True)
class WeightEstimate:
    """A modeled weight together with whether it fell above the cap.

    Quantiles of the crossing weight can land above the extrapolation cap, or be
    infinite when enough simulated paths never reach the target at all. Clamping
    those to the cap and printing them as plain numbers would invent precision
    the model does not have, so the raw value and the cap travel together and
    every caller has to ask whether the figure was identified.
    """

    raw_lb: float
    cap_lb: float

    @property
    def censored(self) -> bool:
        """True when the figure lies above the cap or does not exist."""
        return not np.isfinite(self.raw_lb) or self.raw_lb > self.cap_lb

    @property
    def identified(self) -> bool:
        return not self.censored

    @property
    def unreachable(self) -> bool:
        """True when the target is never reached on enough paths to place this."""
        return not np.isfinite(self.raw_lb)

    @property
    def value_lb(self) -> float | None:
        """The figure when it is identified below the cap, otherwise None."""
        return float(self.raw_lb) if self.identified else None

    def describe(self) -> str:
        """Render for a report or a terminal, never as a bare clamped number."""
        if self.unreachable:
            return f"not identified below {self.cap_lb:.1f} lb"
        if self.censored:
            return (
                f"above {self.cap_lb:.1f} lb "
                f"(unclipped draw quantile {self.raw_lb:.1f} lb)"
            )
        return f"{self.raw_lb:.1f} lb"

    def describe_short(self) -> str:
        """Compact form for terminal output and chart labels."""
        if self.unreachable:
            return f"not identified below {self.cap_lb:.1f} lb"
        if self.censored:
            return f">{self.cap_lb:.1f} lb"
        return f"{self.raw_lb:.1f} lb"


@dataclass(frozen=True)
class BulkInterval:
    """One consecutive pair of scans where bodyweight went up."""

    start_date: date
    end_date: date
    start_weight_lb: float
    end_weight_lb: float
    start_fat_free_mass_lb: float
    end_fat_free_mass_lb: float

    @property
    def weight_gain_lb(self) -> float:
        return self.end_weight_lb - self.start_weight_lb

    @property
    def fat_free_gain_lb(self) -> float:
        return self.end_fat_free_mass_lb - self.start_fat_free_mass_lb

    @property
    def lean_fraction(self) -> float:
        """Share of the weight gain that showed up as fat-free mass."""
        return self.fat_free_gain_lb / self.weight_gain_lb

    @property
    def start_body_fat_pct(self) -> float:
        return 100.0 * (1.0 - self.start_fat_free_mass_lb / self.start_weight_lb)

    @property
    def end_body_fat_pct(self) -> float:
        return 100.0 * (1.0 - self.end_fat_free_mass_lb / self.end_weight_lb)

    @property
    def label(self) -> str:
        return f"{self.start_date} to {self.end_date}"


@dataclass(frozen=True)
class ForecastAssumptions:
    """Every modeling knob the forecast exposes, with its default."""

    target_body_fat_pct: float = DEFAULT_TARGET_BODY_FAT_PCT
    simulations: int = DEFAULT_SIMULATIONS
    seed: int = DEFAULT_SEED
    measurement_error_pp: float = DEFAULT_MEASUREMENT_ERROR_PP
    partition_noise_scale: float = DEFAULT_PARTITION_NOISE_SCALE
    resample_unit: str = DEFAULT_RESAMPLE_UNIT
    max_weight_lb: float | None = None
    grid_step_lb: float = DEFAULT_GRID_STEP_LB


@dataclass(frozen=True)
class PlanningInputs:
    """Where the person is today and how fast they intend to gain.

    Both are optional and neither has a silent default. Without a current
    bodyweight the report falls back to the latest DEXA scan weight and says so.
    Without a weekly rate no duration is reported at all.
    """

    current_bodyweight_lb: float | None = None
    weekly_bulk_rate_lb: float | None = None
    bodyweight_source: str | None = None


@dataclass(frozen=True)
class PlanningOutlook:
    """Headroom and duration from the planning bodyweight to the safety ceiling."""

    current_bodyweight_lb: float
    bodyweight_source: str
    is_scan_fallback: bool
    weekly_bulk_rate_lb: float | None
    headroom_lb: float | None
    weeks_to_ceiling: float | None
    unavailable_reason: str | None


@dataclass(frozen=True)
class SimulationDraws:
    """Per-draw quantities kept so charts and the report agree with each other."""

    lean_fraction: np.ndarray
    anchor_fat_free_mass_lb: np.ndarray
    future_error_pp: np.ndarray
    crossing_weight_lb: np.ndarray


@dataclass(frozen=True)
class AssumptionSensitivity:
    """Safety ceiling with one assumption switched off at a time."""

    zero_partition_noise: WeightEstimate
    zero_measurement_error: WeightEstimate


@dataclass(frozen=True)
class JackknifeSensitivity:
    """Leave-one-interval-out refits of the same forecast.

    This measures how much one interval moves the answer. It is a sensitivity
    check, not a validation: every refit is scored on data it was fitted to, so
    it says nothing about whether the intervals are calibrated. The predictive
    score in `PredictiveScore` is the part that holds data out.
    """

    dropped_label: tuple[str, ...]
    mean_lean_fraction: tuple[float, ...]
    safety_ceiling: tuple[WeightEstimate, ...]

    @property
    def lean_fraction_spread(self) -> float:
        return max(self.mean_lean_fraction) - min(self.mean_lean_fraction)

    @property
    def identified_ceilings_lb(self) -> tuple[float, ...]:
        return tuple(
            estimate.raw_lb for estimate in self.safety_ceiling if estimate.identified
        )

    @property
    def safety_ceiling_spread_lb(self) -> float | None:
        identified = self.identified_ceilings_lb
        if len(identified) < len(self.safety_ceiling) or not identified:
            return None
        return max(identified) - min(identified)


@dataclass(frozen=True)
class PredictiveFold:
    """One held-out bulk, predicted from the bulks that were kept."""

    interval_label: str
    training_intervals: int
    anchor_weight_lb: float
    target_weight_lb: float
    observed_body_fat_pct: float
    predicted_median_pct: float
    predicted_low_80_pct: float
    predicted_high_80_pct: float
    predicted_low_95_pct: float
    predicted_high_95_pct: float
    observed_percentile: float

    @property
    def error_pp(self) -> float:
        """Observed minus predicted median, in percentage points."""
        return self.observed_body_fat_pct - self.predicted_median_pct

    @property
    def inside_80(self) -> bool:
        return (
            self.predicted_low_80_pct
            <= self.observed_body_fat_pct
            <= self.predicted_high_80_pct
        )

    @property
    def inside_95(self) -> bool:
        return (
            self.predicted_low_95_pct
            <= self.observed_body_fat_pct
            <= self.predicted_high_95_pct
        )


@dataclass(frozen=True)
class PredictiveScore:
    """Leave-one-bulk-out scoring of held-out body-fat readings.

    For each bulk in turn: resample only the other bulks, anchor on the held-out
    bulk's own starting scan, predict what a scan would read at that bulk's
    actual ending weight, and compare against what the scan actually read. This
    holds data out, so unlike the jackknife it can be wrong.
    """

    folds: tuple[PredictiveFold, ...]

    @property
    def coverage_80(self) -> float:
        return float(np.mean([fold.inside_80 for fold in self.folds]))

    @property
    def coverage_95(self) -> float:
        return float(np.mean([fold.inside_95 for fold in self.folds]))

    @property
    def median_absolute_error_pp(self) -> float:
        return float(np.median([abs(fold.error_pp) for fold in self.folds]))

    @property
    def mean_error_pp(self) -> float:
        """Positive means the model reads leaner than the scans actually did."""
        return float(np.mean([fold.error_pp for fold in self.folds]))


@dataclass(frozen=True)
class BulkCeilingForecast:
    """Result of one seeded forecast run."""

    assumptions: ForecastAssumptions
    resolved_max_weight_lb: float
    current_date: date
    current_weight_lb: float
    current_fat_free_mass_lb: float
    current_body_fat_pct: float
    intervals: tuple[BulkInterval, ...]
    excluded_intervals: tuple[BulkInterval, ...]
    mean_lean_fraction: float
    pooled_lean_fraction: float
    lean_fraction_sd: float
    measurement_implied_lean_fraction_sd: float
    deconvolved_lean_fraction_sd: float | None
    resampling_blocks: tuple[tuple[int, ...], ...]
    max_weight_is_default: bool
    simulations_is_default: bool
    constant_ffm_ceiling_lb: float
    median_crossing: WeightEstimate
    prediction_low_95: WeightEstimate
    prediction_high_95: WeightEstimate
    prediction_low_80: WeightEstimate
    prediction_high_80: WeightEstimate
    safety_ceiling: WeightEstimate
    never_crosses_fraction: float
    above_cap_fraction: float
    weight_grid_lb: np.ndarray
    probability_under_target: np.ndarray
    body_fat_median_pct: np.ndarray
    body_fat_low_95_pct: np.ndarray
    body_fat_high_95_pct: np.ndarray
    body_fat_low_80_pct: np.ndarray
    body_fat_high_80_pct: np.ndarray
    draws: SimulationDraws
    planning: PlanningOutlook
    jackknife: JackknifeSensitivity | None
    sensitivity: AssumptionSensitivity | None
    predictive_score: PredictiveScore | None

    @property
    def interval_count(self) -> int:
        return len(self.intervals)

    @property
    def is_sparse(self) -> bool:
        return self.interval_count <= SPARSE_INTERVAL_THRESHOLD

    @property
    def probability_at_cap(self) -> float:
        """Modeled probability of still reading under target at the cap."""
        return float(self.probability_under_target[-1])

    @property
    def constant_ffm_above_cap(self) -> bool:
        return self.constant_ffm_ceiling_lb > self.resolved_max_weight_lb

    @property
    def resampling_unit_count(self) -> int:
        """Independent units the bootstrap actually has, which is not the
        interval count whenever intervals share a scan."""
        return len(self.resampling_blocks)

    @property
    def has_shared_endpoints(self) -> bool:
        return self.resampling_unit_count < self.interval_count

    @property
    def noise_variance_share(self) -> float:
        """Share of the observed variance in `k` that scan noise alone explains."""
        if self.lean_fraction_sd <= 0:
            return float("nan")
        return min(
            1.0,
            (self.measurement_implied_lean_fraction_sd / self.lean_fraction_sd) ** 2,
        )


def constant_ffm_ceiling_lb(
    fat_free_mass_lb: float, target_body_fat_pct: float
) -> float:
    """Crossing weight if not one further ounce of fat-free mass is gained.

    This is the deterministic conservative reference: any real fat-free gain
    pushes the true crossing weight higher. It is exact by construction, so it
    is never censored, though it can land above the extrapolation cap.
    """
    _validate_target(target_body_fat_pct)
    if fat_free_mass_lb <= 0:
        raise ValueError("fat-free mass must be positive")
    return fat_free_mass_lb / (1.0 - target_body_fat_pct / 100.0)


def crossing_weight_lb(
    current_weight_lb,
    current_fat_free_mass_lb,
    lean_fraction,
    target_body_fat_pct,
):
    """Weight at which body fat first reaches the target, or infinity.

    Accepts scalars or arrays. Returns a float for all-scalar input.
    """
    weight = np.asarray(current_weight_lb, dtype=float)
    fat_free = np.asarray(current_fat_free_mass_lb, dtype=float)
    partition = np.asarray(lean_fraction, dtype=float)
    target = np.asarray(target_body_fat_pct, dtype=float) / 100.0

    current_fat_fraction = 1.0 - fat_free / weight
    headroom = 1.0 - target - partition
    numerator = fat_free - partition * weight
    with np.errstate(divide="ignore", invalid="ignore"):
        crossing = np.where(headroom > 0, numerator / headroom, np.inf)
    crossing = np.where(current_fat_fraction >= target, weight, crossing)
    crossing = np.asarray(crossing, dtype=float)
    return float(crossing) if crossing.ndim == 0 else crossing


def extract_bulk_intervals(
    totals: pd.DataFrame,
    minimum_gain_lb: float = MINIMUM_INTERVAL_GAIN_LB,
) -> tuple[tuple[BulkInterval, ...], tuple[BulkInterval, ...]]:
    """Split consecutive scans into usable and excluded positive-weight intervals."""
    missing = [column for column in CURRENT_SCAN_COLUMNS if column not in totals]
    if missing:
        raise ValueError(f"totals is missing required columns: {', '.join(missing)}")

    ordered = totals.sort_values("date").reset_index(drop=True)
    if len(ordered) < 2:
        raise ValueError("bulk intervals require at least two scans")

    usable: list[BulkInterval] = []
    excluded: list[BulkInterval] = []
    for position in range(1, len(ordered)):
        start = ordered.iloc[position - 1]
        end = ordered.iloc[position]
        gain = float(end["weight_lb"]) - float(start["weight_lb"])
        if gain <= 0:
            continue
        interval = BulkInterval(
            start_date=_as_date(start["date"]),
            end_date=_as_date(end["date"]),
            start_weight_lb=float(start["weight_lb"]),
            end_weight_lb=float(end["weight_lb"]),
            start_fat_free_mass_lb=float(start["fat_free_mass_lb"]),
            end_fat_free_mass_lb=float(end["fat_free_mass_lb"]),
        )
        if gain < minimum_gain_lb:
            excluded.append(interval)
        else:
            usable.append(interval)
    return tuple(usable), tuple(excluded)


def group_intervals_into_blocks(
    intervals: tuple[BulkInterval, ...],
) -> tuple[tuple[int, ...], ...]:
    """Group intervals that share a scan into one resampling block.

    Two bulks that meet at the same scan share that scan's measurement error, so
    their ratios are not independent observations. Linked intervals are merged
    into a block and the block becomes the unit that gets resampled. Blocks are
    returned as tuples of positions in the input order.
    """
    if not intervals:
        return ()

    parent = list(range(len(intervals)))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for first in range(len(intervals)):
        for second in range(first + 1, len(intervals)):
            shared = {intervals[first].start_date, intervals[first].end_date} & {
                intervals[second].start_date,
                intervals[second].end_date,
            }
            if shared:
                union(first, second)

    grouped: dict[int, list[int]] = {}
    for position in range(len(intervals)):
        grouped.setdefault(find(position), []).append(position)
    return tuple(tuple(members) for _, members in sorted(grouped.items()))


def _resampling_blocks(
    lean_fractions: np.ndarray,
    blocks: tuple[tuple[int, ...], ...] | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Reduce blocks to the sums and counts a vectorized bootstrap needs."""
    if blocks is None:
        return lean_fractions.copy(), np.ones(lean_fractions.size, dtype=float)
    sums = np.array(
        [float(sum(lean_fractions[member] for member in block)) for block in blocks],
        dtype=float,
    )
    counts = np.array([float(len(block)) for block in blocks], dtype=float)
    return sums, counts


def _draw_path_parameters(
    current_weight_lb: float,
    current_fat_free_mass_lb: float,
    lean_fractions: np.ndarray,
    simulations: int,
    seed: int,
    measurement_error_pp: float,
    partition_noise_scale: float,
    blocks: tuple[tuple[int, ...], ...] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Draw the three uncertain quantities every simulated path needs.

    Returns the partitioning ratio, the anchor fat-free mass implied by a noisy
    current reading, and the future scan's own reading error. Both the crossing
    weight and the held-out predictive check are built from these, so the two
    always agree about what a path is.

    `blocks` groups scan-linked intervals so they resample together. Passing
    None treats every interval as its own independent unit.
    """
    if simulations < 1:
        raise ValueError("simulations must be at least 1")
    if measurement_error_pp < 0:
        raise ValueError("measurement error must not be negative")
    if partition_noise_scale < 0:
        raise ValueError("partition noise scale must not be negative")

    observed = np.asarray(lean_fractions, dtype=float)
    count = observed.size
    if count < 1:
        raise ValueError("at least one interval is required")
    generator = np.random.default_rng(seed)

    # 1. Bootstrap the mean partitioning ratio over the resampling units. Whole
    # blocks are drawn together, so intervals that share a scan never contribute
    # their shared noise as two independent observations.
    block_sums, block_counts = _resampling_blocks(observed, blocks)
    unit_count = block_sums.size
    drawn = generator.integers(0, unit_count, size=(simulations, unit_count))
    bootstrap_mean = block_sums[drawn].sum(axis=1) / block_counts[drawn].sum(axis=1)

    # 2. One resampled centred residual for the future bulk's own deviation.
    residuals = observed - observed.mean()
    residual_draw = residuals[generator.integers(0, count, size=simulations)]
    lean_fraction = bootstrap_mean + partition_noise_scale * residual_draw

    # 3a. Current-scan reading error. A flat prior on the true value makes the
    # posterior a normal centred on the reading, which is what is drawn here.
    anchor_error_pp = generator.normal(0.0, measurement_error_pp, simulations)
    anchor_body_fat_pct = (
        100.0 * (1.0 - current_fat_free_mass_lb / current_weight_lb) + anchor_error_pp
    )
    anchor_fat_free_mass_lb = current_weight_lb * (1.0 - anchor_body_fat_pct / 100.0)

    # 3b. Future-scan reading error, carried separately so it can be applied
    # either as a shifted target or as an offset on a predicted reading.
    future_error_pp = generator.normal(0.0, measurement_error_pp, simulations)
    return lean_fraction, anchor_fat_free_mass_lb, future_error_pp


def simulate_crossing_weights(
    current_weight_lb: float,
    current_fat_free_mass_lb: float,
    lean_fractions: np.ndarray,
    target_body_fat_pct: float,
    simulations: int,
    seed: int,
    measurement_error_pp: float,
    partition_noise_scale: float,
    blocks: tuple[tuple[int, ...], ...] | None = None,
) -> SimulationDraws:
    """Resample the observed intervals into a crossing-weight distribution.

    Each draw combines three sources of uncertainty, matching the NIST
    definition of a prediction interval for a future observation:

    1. Parameter uncertainty in the partitioning ratio. Resample the observed
       intervals with replacement and take their mean.
    2. Deviation of one future bulk from that mean. Draw one centred residual
       from the same observed intervals. This is what separates a prediction
       interval from a confidence interval.
    3. Measurement error, applied twice and independently: once to the current
       scan that anchors the projection, once to the future scan that would
       read the result.

    The observed residuals already contain two scans' worth of DEXA noise, so
    step 2 plus step 3 double-counts measurement error. That widens the
    interval rather than narrowing it, which is the safe direction for a
    ceiling. `partition_noise_scale` exists to dial step 2 down if the
    double-count ever needs testing.

    The future-scan error is drawn once per path, not once per weight, so each
    path stays monotone in weight and has a single crossing point. The marginal
    probability at any given weight is unchanged by that choice.
    """
    lean_fraction, anchor_fat_free_mass_lb, future_error_pp = _draw_path_parameters(
        current_weight_lb=current_weight_lb,
        current_fat_free_mass_lb=current_fat_free_mass_lb,
        lean_fractions=lean_fractions,
        simulations=simulations,
        seed=seed,
        measurement_error_pp=measurement_error_pp,
        partition_noise_scale=partition_noise_scale,
        blocks=blocks,
    )
    # A scan reading `e` high crosses the target as soon as the true value
    # reaches `target - e`.
    effective_target_pct = target_body_fat_pct - future_error_pp
    crossing = crossing_weight_lb(
        current_weight_lb,
        anchor_fat_free_mass_lb,
        lean_fraction,
        effective_target_pct,
    )
    return SimulationDraws(
        lean_fraction=lean_fraction,
        anchor_fat_free_mass_lb=anchor_fat_free_mass_lb,
        future_error_pp=future_error_pp,
        crossing_weight_lb=np.asarray(crossing, dtype=float),
    )


def simulate_body_fat_readings(
    anchor_weight_lb: float,
    anchor_fat_free_mass_lb: float,
    lean_fractions: np.ndarray,
    target_weight_lb: float,
    simulations: int,
    seed: int,
    measurement_error_pp: float,
    partition_noise_scale: float,
    blocks: tuple[tuple[int, ...], ...] | None = None,
) -> np.ndarray:
    """Predict what a scan at `target_weight_lb` would read, one value per draw.

    Same three uncertainty terms as `simulate_crossing_weights`, evaluated at a
    fixed weight instead of solved for a crossing. This is what the held-out
    predictive check scores against.
    """
    if target_weight_lb <= 0:
        raise ValueError("target weight must be positive")
    lean_fraction, drawn_fat_free, future_error_pp = _draw_path_parameters(
        current_weight_lb=anchor_weight_lb,
        current_fat_free_mass_lb=anchor_fat_free_mass_lb,
        lean_fractions=lean_fractions,
        simulations=simulations,
        seed=seed,
        measurement_error_pp=measurement_error_pp,
        partition_noise_scale=partition_noise_scale,
        blocks=blocks,
    )
    projected = drawn_fat_free + lean_fraction * (target_weight_lb - anchor_weight_lb)
    return 100.0 * (1.0 - projected / target_weight_lb) + future_error_pp


def modeled_body_fat_pct(
    draws: SimulationDraws, current_weight_lb: float, weight_grid_lb: np.ndarray
) -> np.ndarray:
    """Body-fat percentage a future scan would read, per draw, per grid weight.

    Returns a `(simulations, grid)` array including future-scan reading error,
    so it is consistent with the crossing weights from the same draws.
    """
    grid = np.asarray(weight_grid_lb, dtype=float)[None, :]
    fat_free = (
        draws.anchor_fat_free_mass_lb[:, None]
        + draws.lean_fraction[:, None] * (grid - current_weight_lb)
    )
    true_pct = 100.0 * (1.0 - fat_free / grid)
    return true_pct + draws.future_error_pp[:, None]


def probability_under_target(
    crossing_weight_lb: np.ndarray, weight_grid_lb: np.ndarray
) -> np.ndarray:
    """Modeled probability that a scan at each grid weight still reads under target."""
    crossing = np.asarray(crossing_weight_lb, dtype=float)[:, None]
    grid = np.asarray(weight_grid_lb, dtype=float)[None, :]
    return (crossing > grid).mean(axis=0)


def safety_ceiling_lb(
    crossing_weight_lb: np.ndarray, confidence: float = SAFETY_CONFIDENCE
) -> float:
    """Heaviest weight with at least `confidence` modeled probability of staying under.

    This is the `1 - confidence` quantile of the crossing weight, not the lower
    end of a two-sided interval. A two-sided 95% interval starts at the 2.5%
    quantile, which is a 97.5% one-sided guarantee and therefore stricter.

    The raw quantile is returned uncensored. Wrap it in a `WeightEstimate`
    before showing it to anyone.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return float(
        np.quantile(np.asarray(crossing_weight_lb, dtype=float), 1.0 - confidence)
    )


def smoothed_bodyweight_lb(
    weight_log: pd.DataFrame, weeks: int = DEFAULT_WEIGHT_LOG_WEEKS
) -> float:
    """Average the most recent weekly bodyweight averages into one number.

    The source column is already a weekly average, so this is a mean of weekly
    means rather than a daily smoother. It never infers a rate of gain.
    """
    missing = [column for column in WEIGHT_LOG_COLUMNS if column not in weight_log]
    if missing:
        raise ValueError(
            f"weight log is missing required columns: {', '.join(missing)}"
        )
    if weeks < 1:
        raise ValueError("weeks must be at least 1")

    frame = weight_log.loc[:, list(WEIGHT_LOG_COLUMNS)].copy()
    frame["Week of"] = pd.to_datetime(frame["Week of"], errors="coerce")
    frame["Average"] = pd.to_numeric(frame["Average"], errors="coerce")
    frame = frame[
        frame["Week of"].notna() & frame["Average"].notna() & (frame["Average"] > 0)
    ].sort_values("Week of")
    if frame.empty:
        raise ValueError("weight log contains no usable weekly averages")
    return float(frame["Average"].tail(weeks).mean())


def build_planning_outlook(
    planning: PlanningInputs | None,
    scan_weight_lb: float,
    scan_fat_free_mass_lb: float,
    safety_ceiling: WeightEstimate,
) -> PlanningOutlook:
    """Turn planning inputs into headroom and a duration, or say why not.

    The forecast always anchors composition on the DEXA scan. A supplied current
    bodyweight changes only where the headroom is measured from, never the
    modeled ceiling itself.
    """
    inputs = planning or PlanningInputs()
    supplied = inputs.current_bodyweight_lb
    is_fallback = supplied is None

    if is_fallback:
        current = scan_weight_lb
        source = "latest DEXA scan weight (no current bodyweight supplied)"
    else:
        current = float(supplied)
        if not np.isfinite(current) or current <= 0:
            raise ValueError("current bodyweight must be a positive number")
        if current <= scan_fat_free_mass_lb:
            raise ValueError(
                f"current bodyweight of {current:.1f} lb is at or below the "
                f"{scan_fat_free_mass_lb:.1f} lb of fat-free mass measured on the "
                "latest scan, which is not physically possible"
            )
        gap = abs(current - scan_weight_lb)
        if gap > PLANNING_WEIGHT_TOLERANCE_LB:
            raise ValueError(
                f"current bodyweight of {current:.1f} lb is {gap:.1f} lb from the "
                f"{scan_weight_lb:.1f} lb scan that anchors this forecast, beyond "
                f"the {PLANNING_WEIGHT_TOLERANCE_LB:g} lb tolerance; the modeled "
                "composition would be stale, so take a fresh scan instead"
            )
        source = inputs.bodyweight_source or "supplied on the command line"

    rate = inputs.weekly_bulk_rate_lb
    if rate is not None:
        rate = float(rate)
        if not np.isfinite(rate) or rate <= 0:
            raise ValueError("weekly bulk rate must be a positive number of pounds")

    if safety_ceiling.censored:
        return PlanningOutlook(
            current_bodyweight_lb=current,
            bodyweight_source=source,
            is_scan_fallback=is_fallback,
            weekly_bulk_rate_lb=rate,
            headroom_lb=None,
            weeks_to_ceiling=None,
            unavailable_reason=(
                "the safety ceiling was not identified below the extrapolation cap"
            ),
        )

    headroom = safety_ceiling.raw_lb - current
    if rate is None:
        return PlanningOutlook(
            current_bodyweight_lb=current,
            bodyweight_source=source,
            is_scan_fallback=is_fallback,
            weekly_bulk_rate_lb=None,
            headroom_lb=headroom,
            weeks_to_ceiling=None,
            unavailable_reason="no weekly bulk rate was supplied",
        )
    if headroom <= 0:
        return PlanningOutlook(
            current_bodyweight_lb=current,
            bodyweight_source=source,
            is_scan_fallback=is_fallback,
            weekly_bulk_rate_lb=rate,
            headroom_lb=headroom,
            weeks_to_ceiling=0.0,
            unavailable_reason=None,
        )
    return PlanningOutlook(
        current_bodyweight_lb=current,
        bodyweight_source=source,
        is_scan_fallback=is_fallback,
        weekly_bulk_rate_lb=rate,
        headroom_lb=headroom,
        weeks_to_ceiling=headroom / rate,
        unavailable_reason=None,
    )


def blocks_for(
    intervals: tuple[BulkInterval, ...], resample_unit: str
) -> tuple[tuple[int, ...], ...] | None:
    """Resolve the configured resampling unit into concrete blocks."""
    if resample_unit == RESAMPLE_UNIT_INTERVAL:
        return None
    if resample_unit != RESAMPLE_UNIT_BLOCK:
        raise ValueError(
            f"resample unit must be one of {', '.join(RESAMPLE_UNITS)}; "
            f"got {resample_unit!r}"
        )
    return group_intervals_into_blocks(intervals)


def deconvolved_lean_fraction_sd(
    observed_sd: float, measurement_implied_sd: float
) -> float | None:
    """Strip the measurement-noise share out of the observed spread in `k`.

    Returns None when the implied noise exceeds the observed spread, which would
    give a negative variance and means the data cannot separate the two.
    """
    residual_variance = observed_sd**2 - measurement_implied_sd**2
    if residual_variance <= 0:
        return None
    return float(np.sqrt(residual_variance))


def leave_one_bulk_out_score(
    intervals: tuple[BulkInterval, ...], settings: ForecastAssumptions
) -> PredictiveScore:
    """Score held-out bulks, the only honest validation this record allows.

    For each bulk in turn, resample only the other bulks, anchor on the held-out
    bulk's own starting scan, and predict what a scan would read at that bulk's
    actual ending weight. The observed reading is then placed inside that
    predictive distribution.

    Each fold gets its own seed derived from the run seed, so the whole score is
    reproducible and no two folds share draws.
    """
    if len(intervals) < MINIMUM_BULK_INTERVALS:
        raise ValueError(
            f"a held-out score needs at least {MINIMUM_BULK_INTERVALS} intervals"
        )

    folds: list[PredictiveFold] = []
    outer_tail = (1.0 - PREDICTION_COVERAGE) / 2.0
    inner_tail = (1.0 - PREDICTION_COVERAGE_INNER) / 2.0
    for position, held_out in enumerate(intervals):
        training = tuple(
            interval
            for index, interval in enumerate(intervals)
            if index != position
        )
        fractions = np.array(
            [interval.lean_fraction for interval in training], dtype=float
        )
        readings = simulate_body_fat_readings(
            blocks=blocks_for(training, settings.resample_unit),
            anchor_weight_lb=held_out.start_weight_lb,
            anchor_fat_free_mass_lb=held_out.start_fat_free_mass_lb,
            lean_fractions=fractions,
            target_weight_lb=held_out.end_weight_lb,
            simulations=settings.simulations,
            seed=settings.seed + 101 * (position + 1),
            measurement_error_pp=settings.measurement_error_pp,
            partition_noise_scale=settings.partition_noise_scale,
        )
        observed = held_out.end_body_fat_pct
        folds.append(
            PredictiveFold(
                interval_label=held_out.label,
                training_intervals=len(training),
                anchor_weight_lb=held_out.start_weight_lb,
                target_weight_lb=held_out.end_weight_lb,
                observed_body_fat_pct=observed,
                predicted_median_pct=float(np.quantile(readings, 0.5)),
                predicted_low_80_pct=float(np.quantile(readings, inner_tail)),
                predicted_high_80_pct=float(np.quantile(readings, 1.0 - inner_tail)),
                predicted_low_95_pct=float(np.quantile(readings, outer_tail)),
                predicted_high_95_pct=float(np.quantile(readings, 1.0 - outer_tail)),
                observed_percentile=float(np.mean(readings < observed)),
            )
        )
    return PredictiveScore(folds=tuple(folds))


def forecast_bulk_ceiling(
    totals: pd.DataFrame,
    assumptions: ForecastAssumptions | None = None,
    planning: PlanningInputs | None = None,
    with_sensitivity: bool = True,
    with_predictive_score: bool = True,
) -> BulkCeilingForecast:
    """Run one seeded forecast from a table of total-body scans."""
    settings = assumptions or ForecastAssumptions()
    _validate_target(settings.target_body_fat_pct)
    if settings.grid_step_lb <= 0:
        raise ValueError("grid step must be positive")

    ordered = totals.sort_values("date").reset_index(drop=True)
    intervals, excluded = extract_bulk_intervals(ordered)
    if len(intervals) < MINIMUM_BULK_INTERVALS:
        raise ValueError(
            f"forecast requires at least {MINIMUM_BULK_INTERVALS} positive-weight "
            f"intervals of {MINIMUM_INTERVAL_GAIN_LB:g} lb or more; found "
            f"{len(intervals)}"
        )

    latest = ordered.iloc[-1]
    current_weight = float(latest["weight_lb"])
    current_fat_free = float(latest["fat_free_mass_lb"])
    if current_weight <= 0 or current_fat_free <= 0:
        raise ValueError("the latest scan must have positive weight and fat-free mass")
    current_body_fat_pct = 100.0 * (1.0 - current_fat_free / current_weight)
    if current_body_fat_pct >= settings.target_body_fat_pct:
        raise ValueError(
            f"the latest scan already reads {current_body_fat_pct:.2f}% body fat, at "
            f"or above the {settings.target_body_fat_pct:g}% target; there is no bulk "
            "headroom to forecast"
        )

    max_weight = settings.max_weight_lb
    max_weight_is_default = max_weight is None
    if max_weight is None:
        max_weight = current_weight + DEFAULT_EXTRAPOLATION_MARGIN_LB
    if max_weight <= current_weight:
        raise ValueError("maximum weight must be above the current scan weight")
    cap = float(max_weight)

    lean_fractions = np.array(
        [interval.lean_fraction for interval in intervals], dtype=float
    )
    blocks = blocks_for(intervals, settings.resample_unit)
    resolved_blocks = blocks or tuple(
        (position,) for position in range(len(intervals))
    )
    draws = simulate_crossing_weights(
        current_weight_lb=current_weight,
        current_fat_free_mass_lb=current_fat_free,
        lean_fractions=lean_fractions,
        target_body_fat_pct=settings.target_body_fat_pct,
        simulations=settings.simulations,
        seed=settings.seed,
        measurement_error_pp=settings.measurement_error_pp,
        partition_noise_scale=settings.partition_noise_scale,
        blocks=blocks,
    )
    crossing = draws.crossing_weight_lb

    grid = np.arange(
        current_weight, cap + settings.grid_step_lb / 2.0, settings.grid_step_lb
    )
    probability = probability_under_target(crossing, grid)
    body_fat = modeled_body_fat_pct(draws, current_weight, grid)

    outer_tail = (1.0 - PREDICTION_COVERAGE) / 2.0
    inner_tail = (1.0 - PREDICTION_COVERAGE_INNER) / 2.0
    pooled = float(
        sum(interval.fat_free_gain_lb for interval in intervals)
        / sum(interval.weight_gain_lb for interval in intervals)
    )
    implied_sd = measurement_implied_lean_fraction_sd(
        current_weight, intervals, settings.measurement_error_pp
    )
    ceiling = WeightEstimate(safety_ceiling_lb(crossing), cap)
    jackknife = (
        _jackknife(current_weight, current_fat_free, intervals, settings, cap)
        if with_sensitivity
        else None
    )
    sensitivity = (
        _assumption_sensitivity(
            current_weight, current_fat_free, lean_fractions, settings, cap, blocks
        )
        if with_sensitivity
        else None
    )
    predictive_score = (
        leave_one_bulk_out_score(intervals, settings) if with_predictive_score else None
    )

    return BulkCeilingForecast(
        assumptions=replace(settings, max_weight_lb=cap),
        resolved_max_weight_lb=cap,
        current_date=_as_date(latest["date"]),
        current_weight_lb=current_weight,
        current_fat_free_mass_lb=current_fat_free,
        current_body_fat_pct=current_body_fat_pct,
        intervals=intervals,
        excluded_intervals=excluded,
        mean_lean_fraction=float(lean_fractions.mean()),
        pooled_lean_fraction=pooled,
        lean_fraction_sd=float(lean_fractions.std(ddof=1)),
        measurement_implied_lean_fraction_sd=implied_sd,
        deconvolved_lean_fraction_sd=deconvolved_lean_fraction_sd(
            float(lean_fractions.std(ddof=1)), implied_sd
        ),
        resampling_blocks=resolved_blocks,
        max_weight_is_default=max_weight_is_default,
        simulations_is_default=settings.simulations == DEFAULT_SIMULATIONS,
        constant_ffm_ceiling_lb=constant_ffm_ceiling_lb(
            current_fat_free, settings.target_body_fat_pct
        ),
        median_crossing=WeightEstimate(float(np.quantile(crossing, 0.5)), cap),
        prediction_low_95=WeightEstimate(float(np.quantile(crossing, outer_tail)), cap),
        prediction_high_95=WeightEstimate(
            float(np.quantile(crossing, 1.0 - outer_tail)), cap
        ),
        prediction_low_80=WeightEstimate(float(np.quantile(crossing, inner_tail)), cap),
        prediction_high_80=WeightEstimate(
            float(np.quantile(crossing, 1.0 - inner_tail)), cap
        ),
        safety_ceiling=ceiling,
        never_crosses_fraction=float(np.mean(~np.isfinite(crossing))),
        above_cap_fraction=float(np.mean(crossing > cap)),
        weight_grid_lb=grid,
        probability_under_target=probability,
        body_fat_median_pct=np.quantile(body_fat, 0.5, axis=0),
        body_fat_low_95_pct=np.quantile(body_fat, outer_tail, axis=0),
        body_fat_high_95_pct=np.quantile(body_fat, 1.0 - outer_tail, axis=0),
        body_fat_low_80_pct=np.quantile(body_fat, inner_tail, axis=0),
        body_fat_high_80_pct=np.quantile(body_fat, 1.0 - inner_tail, axis=0),
        draws=draws,
        planning=build_planning_outlook(
            planning, current_weight, current_fat_free, ceiling
        ),
        jackknife=jackknife,
        sensitivity=sensitivity,
        predictive_score=predictive_score,
    )


PROBABILITY_CURVE_COLUMNS = (
    "weight_lb",
    "probability_under_target",
    "body_fat_pct_median",
    "body_fat_pct_p10",
    "body_fat_pct_p90",
    "body_fat_pct_p2_5",
    "body_fat_pct_p97_5",
)


def probability_curve_frame(forecast: BulkCeilingForecast) -> pd.DataFrame:
    """Tabulate the probability curve in a fixed column order."""
    return pd.DataFrame(
        {
            "weight_lb": forecast.weight_grid_lb,
            "probability_under_target": forecast.probability_under_target,
            "body_fat_pct_median": forecast.body_fat_median_pct,
            "body_fat_pct_p10": forecast.body_fat_low_80_pct,
            "body_fat_pct_p90": forecast.body_fat_high_80_pct,
            "body_fat_pct_p2_5": forecast.body_fat_low_95_pct,
            "body_fat_pct_p97_5": forecast.body_fat_high_95_pct,
        },
        columns=list(PROBABILITY_CURVE_COLUMNS),
    )


def measurement_implied_lean_fraction_sd(
    current_weight_lb: float,
    intervals: tuple[BulkInterval, ...],
    measurement_error_pp: float,
) -> float:
    """How much of the observed spread in `k` scan noise alone could explain.

    Each `k` is a difference of two fat-free readings divided by a weight gain,
    so its measurement-induced standard deviation is
    `sqrt(2) * W * error / gain`. The typical interval gain is used for `gain`.
    If this comes out at or above the observed spread, the interval-to-interval
    variation in `k` carries no evidence of real biological variation.
    """
    if not intervals:
        raise ValueError("at least one interval is required")
    fat_free_error_lb = current_weight_lb * measurement_error_pp / 100.0
    typical_gain_lb = float(
        np.median([interval.weight_gain_lb for interval in intervals])
    )
    return float(np.sqrt(2.0) * fat_free_error_lb / typical_gain_lb)


def _assumption_sensitivity(
    current_weight_lb: float,
    current_fat_free_mass_lb: float,
    lean_fractions: np.ndarray,
    settings: ForecastAssumptions,
    max_weight_lb: float,
    blocks: tuple[tuple[int, ...], ...] | None,
) -> AssumptionSensitivity:
    """Rerun the safety ceiling with each noise term zeroed, seed unchanged."""

    def ceiling(
        measurement_error_pp: float, partition_noise_scale: float
    ) -> WeightEstimate:
        draws = simulate_crossing_weights(
            current_weight_lb=current_weight_lb,
            current_fat_free_mass_lb=current_fat_free_mass_lb,
            lean_fractions=lean_fractions,
            target_body_fat_pct=settings.target_body_fat_pct,
            simulations=settings.simulations,
            seed=settings.seed,
            measurement_error_pp=measurement_error_pp,
            partition_noise_scale=partition_noise_scale,
            blocks=blocks,
        )
        return WeightEstimate(
            safety_ceiling_lb(draws.crossing_weight_lb), max_weight_lb
        )

    return AssumptionSensitivity(
        zero_partition_noise=ceiling(settings.measurement_error_pp, 0.0),
        zero_measurement_error=ceiling(0.0, settings.partition_noise_scale),
    )


def _jackknife(
    current_weight_lb: float,
    current_fat_free_mass_lb: float,
    intervals: tuple[BulkInterval, ...],
    settings: ForecastAssumptions,
    max_weight_lb: float,
) -> JackknifeSensitivity:
    """Refit once per dropped interval, holding the seed and every other knob fixed."""
    labels: list[str] = []
    means: list[float] = []
    ceilings: list[WeightEstimate] = []
    for dropped in range(len(intervals)):
        kept = tuple(
            interval
            for position, interval in enumerate(intervals)
            if position != dropped
        )
        fractions = np.array(
            [interval.lean_fraction for interval in kept], dtype=float
        )
        draws = simulate_crossing_weights(
            current_weight_lb=current_weight_lb,
            current_fat_free_mass_lb=current_fat_free_mass_lb,
            lean_fractions=fractions,
            target_body_fat_pct=settings.target_body_fat_pct,
            simulations=settings.simulations,
            seed=settings.seed,
            measurement_error_pp=settings.measurement_error_pp,
            partition_noise_scale=settings.partition_noise_scale,
            blocks=blocks_for(kept, settings.resample_unit),
        )
        labels.append(intervals[dropped].label)
        means.append(float(fractions.mean()))
        ceilings.append(
            WeightEstimate(safety_ceiling_lb(draws.crossing_weight_lb), max_weight_lb)
        )
    return JackknifeSensitivity(
        dropped_label=tuple(labels),
        mean_lean_fraction=tuple(means),
        safety_ceiling=tuple(ceilings),
    )


def _validate_target(target_body_fat_pct: float) -> None:
    value = float(target_body_fat_pct)
    if not np.isfinite(value):
        raise ValueError("target body fat must be a finite percentage")
    if not 0.0 < value < 100.0:
        raise ValueError(
            f"target body fat must be between 0 and 100 percent; got {value:g}"
        )


def _as_date(value) -> date:
    return pd.Timestamp(value).date()
