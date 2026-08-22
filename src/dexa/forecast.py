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
# Ober et al. 2026 (PMID 42298959) report between-day body-fat TEM of 0.37 to
# 1.24 pp; 0.8 pp is the midpoint of that published range. BodySpec's own
# repeatability claim of about +/-0.5 pp under matched preparation sits inside
# it. This is an assumption, not a measurement of this scanner.
DEFAULT_MEASUREMENT_ERROR_PP = 0.8

# Multiplier on the resampled interval-to-interval deviation of k. 1.0 uses the
# observed spread as-is. See `simulate_crossing_weights` for why that is
# deliberately conservative.
DEFAULT_PARTITION_NOISE_SCALE = 1.0

# How far above the current scan the forecast is allowed to run. The largest
# single bulk in this record is about 28 lb of gain, so 60 lb is already more
# than twice anything the data covers. Draws that cross above the cap are
# reported as censored rather than silently dropped.
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

# Two-sided coverage for the crossing-weight prediction interval.
PREDICTION_COVERAGE = 0.95

CURRENT_SCAN_COLUMNS = ("date", "weight_lb", "fat_free_mass_lb")


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


@dataclass(frozen=True)
class ForecastAssumptions:
    """Every knob the forecast exposes, with its default."""

    target_body_fat_pct: float = DEFAULT_TARGET_BODY_FAT_PCT
    simulations: int = DEFAULT_SIMULATIONS
    seed: int = DEFAULT_SEED
    measurement_error_pp: float = DEFAULT_MEASUREMENT_ERROR_PP
    partition_noise_scale: float = DEFAULT_PARTITION_NOISE_SCALE
    max_weight_lb: float | None = None
    grid_step_lb: float = DEFAULT_GRID_STEP_LB


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

    zero_partition_noise_lb: float
    zero_measurement_error_lb: float


@dataclass(frozen=True)
class JackknifeSensitivity:
    """Leave-one-interval-out refits, the only holdout a 5-interval record allows."""

    dropped_label: tuple[str, ...]
    mean_lean_fraction: tuple[float, ...]
    safety_ceiling_lb: tuple[float, ...]

    @property
    def lean_fraction_spread(self) -> float:
        return max(self.mean_lean_fraction) - min(self.mean_lean_fraction)

    @property
    def safety_ceiling_spread_lb(self) -> float:
        return max(self.safety_ceiling_lb) - min(self.safety_ceiling_lb)


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
    constant_ffm_ceiling_lb: float
    median_crossing_lb: float
    prediction_low_lb: float
    prediction_high_lb: float
    prediction_high_raw_lb: float
    prediction_high_censored: bool
    safety_ceiling_lb: float
    never_crosses_fraction: float
    above_cap_fraction: float
    weight_grid_lb: np.ndarray
    probability_under_target: np.ndarray
    body_fat_median_pct: np.ndarray
    body_fat_low_pct: np.ndarray
    body_fat_high_pct: np.ndarray
    draws: SimulationDraws
    jackknife: JackknifeSensitivity | None
    sensitivity: AssumptionSensitivity | None

    @property
    def interval_count(self) -> int:
        return len(self.intervals)

    @property
    def is_sparse(self) -> bool:
        return self.interval_count <= SPARSE_INTERVAL_THRESHOLD

    @property
    def headroom_lb(self) -> float:
        """Pounds from the current scan to the one-sided safety ceiling."""
        return self.safety_ceiling_lb - self.current_weight_lb


def constant_ffm_ceiling_lb(
    fat_free_mass_lb: float, target_body_fat_pct: float
) -> float:
    """Crossing weight if not one further ounce of fat-free mass is gained.

    This is the deterministic conservative reference: any real fat-free gain
    pushes the true crossing weight higher.
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


def simulate_crossing_weights(
    current_weight_lb: float,
    current_fat_free_mass_lb: float,
    lean_fractions: np.ndarray,
    target_body_fat_pct: float,
    simulations: int,
    seed: int,
    measurement_error_pp: float,
    partition_noise_scale: float,
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
    if simulations < 1:
        raise ValueError("simulations must be at least 1")
    if measurement_error_pp < 0:
        raise ValueError("measurement error must not be negative")
    if partition_noise_scale < 0:
        raise ValueError("partition noise scale must not be negative")

    observed = np.asarray(lean_fractions, dtype=float)
    count = observed.size
    generator = np.random.default_rng(seed)

    # 1. Bootstrap the mean partitioning ratio over the observed intervals.
    resampled = observed[generator.integers(0, count, size=(simulations, count))]
    bootstrap_mean = resampled.mean(axis=1)

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

    # 3b. Future-scan reading error. A scan that reads `e` high crosses the
    # target as soon as the true value reaches `target - e`.
    future_error_pp = generator.normal(0.0, measurement_error_pp, simulations)
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
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return float(np.quantile(np.asarray(crossing_weight_lb, dtype=float), 1.0 - confidence))


def forecast_bulk_ceiling(
    totals: pd.DataFrame,
    assumptions: ForecastAssumptions | None = None,
    with_sensitivity: bool = True,
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
    if max_weight is None:
        max_weight = current_weight + DEFAULT_EXTRAPOLATION_MARGIN_LB
    if max_weight <= current_weight:
        raise ValueError("maximum weight must be above the current scan weight")

    lean_fractions = np.array(
        [interval.lean_fraction for interval in intervals], dtype=float
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
    )
    crossing = draws.crossing_weight_lb

    grid = np.arange(
        current_weight, max_weight + settings.grid_step_lb / 2.0, settings.grid_step_lb
    )
    probability = probability_under_target(crossing, grid)
    body_fat = modeled_body_fat_pct(draws, current_weight, grid)

    tail = (1.0 - PREDICTION_COVERAGE) / 2.0
    low = float(np.quantile(crossing, tail))
    high = float(np.quantile(crossing, 1.0 - tail))
    pooled = float(
        sum(interval.fat_free_gain_lb for interval in intervals)
        / sum(interval.weight_gain_lb for interval in intervals)
    )
    implied_sd = measurement_implied_lean_fraction_sd(
        current_weight, intervals, settings.measurement_error_pp
    )
    jackknife = (
        _jackknife(
            current_weight, current_fat_free, intervals, settings, float(max_weight)
        )
        if with_sensitivity
        else None
    )
    sensitivity = (
        _assumption_sensitivity(
            current_weight,
            current_fat_free,
            lean_fractions,
            settings,
            float(max_weight),
        )
        if with_sensitivity
        else None
    )

    return BulkCeilingForecast(
        assumptions=replace(settings, max_weight_lb=max_weight),
        resolved_max_weight_lb=float(max_weight),
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
        constant_ffm_ceiling_lb=constant_ffm_ceiling_lb(
            current_fat_free, settings.target_body_fat_pct
        ),
        median_crossing_lb=min(float(np.quantile(crossing, 0.5)), float(max_weight)),
        prediction_low_lb=min(low, float(max_weight)),
        prediction_high_lb=min(high, float(max_weight)),
        prediction_high_raw_lb=high,
        prediction_high_censored=bool(high > max_weight),
        safety_ceiling_lb=min(safety_ceiling_lb(crossing), float(max_weight)),
        never_crosses_fraction=float(np.mean(~np.isfinite(crossing))),
        above_cap_fraction=float(np.mean(crossing > max_weight)),
        weight_grid_lb=grid,
        probability_under_target=probability,
        body_fat_median_pct=np.quantile(body_fat, 0.5, axis=0),
        body_fat_low_pct=np.quantile(body_fat, tail, axis=0),
        body_fat_high_pct=np.quantile(body_fat, 1.0 - tail, axis=0),
        draws=draws,
        jackknife=jackknife,
        sensitivity=sensitivity,
    )


PROBABILITY_CURVE_COLUMNS = (
    "weight_lb",
    "probability_under_target",
    "body_fat_pct_median",
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
            "body_fat_pct_p2_5": forecast.body_fat_low_pct,
            "body_fat_pct_p97_5": forecast.body_fat_high_pct,
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
) -> AssumptionSensitivity:
    """Rerun the safety ceiling with each noise term zeroed, seed unchanged."""

    def ceiling(measurement_error_pp: float, partition_noise_scale: float) -> float:
        draws = simulate_crossing_weights(
            current_weight_lb=current_weight_lb,
            current_fat_free_mass_lb=current_fat_free_mass_lb,
            lean_fractions=lean_fractions,
            target_body_fat_pct=settings.target_body_fat_pct,
            simulations=settings.simulations,
            seed=settings.seed,
            measurement_error_pp=measurement_error_pp,
            partition_noise_scale=partition_noise_scale,
        )
        return min(safety_ceiling_lb(draws.crossing_weight_lb), max_weight_lb)

    return AssumptionSensitivity(
        zero_partition_noise_lb=ceiling(settings.measurement_error_pp, 0.0),
        zero_measurement_error_lb=ceiling(0.0, settings.partition_noise_scale),
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
    ceilings: list[float] = []
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
        )
        labels.append(
            f"{intervals[dropped].start_date} to {intervals[dropped].end_date}"
        )
        means.append(float(fractions.mean()))
        ceilings.append(
            min(safety_ceiling_lb(draws.crossing_weight_lb), max_weight_lb)
        )
    return JackknifeSensitivity(
        dropped_label=tuple(labels),
        mean_lean_fraction=tuple(means),
        safety_ceiling_lb=tuple(ceilings),
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
