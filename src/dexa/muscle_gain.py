"""Estimate longitudinal skeletal-muscle change from repeated DEXA scans.

DEXA measures lean soft tissue, not skeletal muscle. This module first models
lean soft tissue at a common bodyweight, then applies an explicit and deliberately
broad lean-to-muscle interpretation range. Strength data never enter the mass
calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

DEFAULT_SIMULATIONS = 50_000
DEFAULT_SEED = 20260822
KG_TO_LB = 2.2046226218
# Powers et al. 2015 report 0.76 kg total-lean RMS-SD over repeat scans.
DEFAULT_SCAN_ERROR_SD_LB = 0.76 * KG_TO_LB
DEFAULT_MUSCLE_SHARE_LOW = 0.50
DEFAULT_MUSCLE_SHARE_HIGH = 1.00
RECENT_WINDOW_YEARS = 3
ESTIMATOR_COLUMNS = (
    "date",
    "weight_lb",
    "lean_soft_tissue_lb",
    "bone_mineral_content_lb",
    "fat_free_mass_lb",
    "fat_mass_lb",
)


@dataclass(frozen=True)
class MuscleGainAssumptions:
    """Inputs that control the uncertainty calculation."""

    simulations: int = DEFAULT_SIMULATIONS
    seed: int = DEFAULT_SEED
    scan_error_sd_lb: float = DEFAULT_SCAN_ERROR_SD_LB
    muscle_share_low: float = DEFAULT_MUSCLE_SHARE_LOW
    muscle_share_high: float = DEFAULT_MUSCLE_SHARE_HIGH


@dataclass(frozen=True)
class ChangeWindow:
    """Observed composition change between two scans."""

    label: str
    start_date: date
    end_date: date
    years: float
    weight_change_lb: float
    lean_soft_tissue_change_lb: float
    bone_mineral_content_change_lb: float
    fat_free_mass_change_lb: float
    fat_mass_change_lb: float


@dataclass(frozen=True)
class RegionalSensitivity:
    """Sparse appendicular lean-mass check, kept separate from the estimate."""

    scan_count: int
    start_date: date
    end_date: date
    observed_appendicular_change_lb: float
    adjusted_appendicular_change_lb: float
    adjusted_arm_change_lb: float
    adjusted_leg_change_lb: float


@dataclass(frozen=True)
class StrengthComparison:
    """One lift's recorded estimated-1RM comparison."""

    exercise: str
    baseline_workouts: int
    latest_workouts: int
    baseline_p95_one_rm_lb: float
    latest_p95_one_rm_lb: float

    @property
    def change_pct(self) -> float:
        return 100.0 * (
            self.latest_p95_one_rm_lb / self.baseline_p95_one_rm_lb - 1.0
        )


@dataclass(frozen=True)
class TrainingEvidence:
    """Training evidence that can corroborate, but never size, muscle gain."""

    first_workout_date: date
    workouts_before_baseline: int
    workouts_during_scan_window: int
    comparisons: tuple[StrengthComparison, ...]


@dataclass(frozen=True)
class MuscleGainEstimate:
    """Observed changes, modeled lean trend, and interpreted muscle change."""

    assumptions: MuscleGainAssumptions
    totals: pd.DataFrame
    windows: tuple[ChangeWindow, ChangeWindow]
    reference_weight_lb: float
    bodyweight_slope: float
    annual_adjusted_lean_slope_lb: float
    full_span_adjusted_lean_gain_lb: float
    residual_sd_lb: float
    assumed_scan_error_sd_lb: float
    residual_state_sd_lb: float
    muscle_gain_median_lb: float
    muscle_gain_low_95_lb: float
    muscle_gain_high_95_lb: float
    adjusted_lean_gain_draws_lb: np.ndarray
    muscle_gain_draws_lb: np.ndarray
    adjusted_lean_soft_tissue_lb: np.ndarray
    regional: RegionalSensitivity | None

    @property
    def earliest_to_latest(self) -> ChangeWindow:
        return self.windows[0]

    @property
    def recent(self) -> ChangeWindow:
        return self.windows[1]


def estimate_muscle_gain(
    totals: pd.DataFrame,
    regions: pd.DataFrame | None = None,
    assumptions: MuscleGainAssumptions | None = None,
) -> MuscleGainEstimate:
    """Estimate net skeletal-muscle change over the full scan history.

    The model is ``lean soft tissue ~ bodyweight + elapsed time``. The time
    coefficient is the estimated lean change at a common bodyweight. Its
    uncertainty is split into a declared scan-error component and the remaining
    scan-to-scan state variation. A bounded interpretation factor then allows
    50% to 100% of that adjusted lean trend to represent skeletal muscle.
    """
    settings = assumptions or MuscleGainAssumptions()
    _validate_assumptions(settings)
    ordered = _validate_totals(totals)

    elapsed_years = (
        (ordered["date"] - ordered["date"].iloc[0]).dt.days.to_numpy(dtype=float)
        / 365.2425
    )
    reference_weight = float(ordered["weight_lb"].mean())
    centered_weight = ordered["weight_lb"].to_numpy(dtype=float) - reference_weight
    design = np.column_stack(
        [np.ones(len(ordered), dtype=float), centered_weight, elapsed_years]
    )
    observed_lean = ordered["lean_soft_tissue_lb"].to_numpy(dtype=float)
    coefficients, _, _, _ = np.linalg.lstsq(design, observed_lean, rcond=None)
    fitted = design @ coefficients
    degrees_of_freedom = len(ordered) - design.shape[1]
    residual_sd = float(
        np.sqrt(np.square(observed_lean - fitted).sum() / degrees_of_freedom)
    )
    scan_error_sd = float(settings.scan_error_sd_lb)
    state_sd = float(np.sqrt(max(0.0, residual_sd**2 - scan_error_sd**2)))

    full_span_years = float(elapsed_years[-1])
    coefficient_scale = float(np.sqrt(np.linalg.inv(design.T @ design)[2, 2]))
    adjusted_lean_gain = float(coefficients[2] * full_span_years)

    generator = np.random.default_rng(settings.seed)
    state_error = (
        generator.standard_t(degrees_of_freedom, settings.simulations)
        * state_sd
        * coefficient_scale
        * full_span_years
    )
    scan_error = (
        generator.normal(0.0, scan_error_sd, settings.simulations)
        * coefficient_scale
        * full_span_years
    )
    adjusted_draws = adjusted_lean_gain + state_error + scan_error
    # No validated individual-level conversion exists. A uniform draw avoids
    # treating any point in the declared range as literature-derived.
    muscle_share = generator.uniform(
        settings.muscle_share_low,
        settings.muscle_share_high,
        settings.simulations,
    )
    muscle_draws = adjusted_draws * muscle_share
    low, median, high = np.quantile(muscle_draws, [0.025, 0.5, 0.975])

    adjusted_lean = observed_lean - coefficients[1] * centered_weight
    windows = (
        _change_window("Earliest to latest", ordered.iloc[0], ordered.iloc[-1]),
        _recent_window(ordered),
    )
    regional = _regional_sensitivity(regions, ordered) if regions is not None else None
    return MuscleGainEstimate(
        assumptions=settings,
        totals=ordered,
        windows=windows,
        reference_weight_lb=reference_weight,
        bodyweight_slope=float(coefficients[1]),
        annual_adjusted_lean_slope_lb=float(coefficients[2]),
        full_span_adjusted_lean_gain_lb=adjusted_lean_gain,
        residual_sd_lb=residual_sd,
        assumed_scan_error_sd_lb=scan_error_sd,
        residual_state_sd_lb=state_sd,
        muscle_gain_median_lb=float(median),
        muscle_gain_low_95_lb=float(low),
        muscle_gain_high_95_lb=float(high),
        adjusted_lean_gain_draws_lb=adjusted_draws,
        muscle_gain_draws_lb=muscle_draws,
        adjusted_lean_soft_tissue_lb=adjusted_lean,
        regional=regional,
    )


def summarize_training_evidence(
    workouts: pd.DataFrame,
    sets: pd.DataFrame,
    baseline_date: date,
    latest_date: date,
    exercises: tuple[str, ...] = (
        "Flat Barbell Bench Press",
        "Back Squats",
        "Barbell Overhead Press",
    ),
) -> TrainingEvidence:
    """Summarize training history without converting strength into muscle mass."""
    workout_dates = pd.to_datetime(workouts["date"])
    set_frame = sets.copy()
    set_frame["date"] = pd.to_datetime(set_frame["date"])
    baseline = pd.Timestamp(baseline_date)
    latest = pd.Timestamp(latest_date)
    one_year = pd.Timedelta(days=365)
    comparisons: list[StrengthComparison] = []
    for exercise in exercises:
        candidates = set_frame[
            (set_frame["display_name"] == exercise)
            & set_frame["one_rm"].notna()
            & (set_frame["one_rm"] > 0)
            & set_frame["reps"].between(1, 12)
        ]
        before = candidates[
            (candidates["date"] >= baseline - one_year)
            & (candidates["date"] <= baseline)
        ]
        after = candidates[
            (candidates["date"] >= latest - one_year)
            & (candidates["date"] <= latest)
        ]
        if before.empty or after.empty:
            continue
        comparisons.append(
            StrengthComparison(
                exercise=exercise,
                baseline_workouts=int(before["workout_id"].nunique()),
                latest_workouts=int(after["workout_id"].nunique()),
                baseline_p95_one_rm_lb=float(before["one_rm"].quantile(0.95)),
                latest_p95_one_rm_lb=float(after["one_rm"].quantile(0.95)),
            )
        )
    return TrainingEvidence(
        first_workout_date=workout_dates.min().date(),
        workouts_before_baseline=int((workout_dates < baseline).sum()),
        workouts_during_scan_window=int(
            ((workout_dates >= baseline) & (workout_dates <= latest)).sum()
        ),
        comparisons=tuple(comparisons),
    )


def leave_one_scan_out_adjusted_gains(totals: pd.DataFrame) -> tuple[float, ...]:
    """Return full-span adjusted lean gains after dropping each scan in turn."""
    ordered = _validate_totals(totals)
    full_span_years = (
        ordered["date"].iloc[-1] - ordered["date"].iloc[0]
    ).days / 365.2425
    results = []
    for position in range(len(ordered)):
        kept = ordered.drop(index=position).reset_index(drop=True)
        years = (
            (kept["date"] - ordered["date"].iloc[0]).dt.days.to_numpy(dtype=float)
            / 365.2425
        )
        weights = kept["weight_lb"].to_numpy(dtype=float)
        design = np.column_stack([np.ones(len(kept)), weights - weights.mean(), years])
        coefficients, _, _, _ = np.linalg.lstsq(
            design, kept["lean_soft_tissue_lb"].to_numpy(dtype=float), rcond=None
        )
        results.append(float(coefficients[2] * full_span_years))
    return tuple(results)


def _validate_totals(totals: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in ESTIMATOR_COLUMNS if column not in totals]
    if missing:
        raise ValueError(f"totals is missing required columns: {', '.join(missing)}")
    ordered = totals.copy()
    ordered["date"] = pd.to_datetime(ordered["date"])
    ordered = ordered.sort_values("date").reset_index(drop=True)
    if len(ordered) < 5:
        raise ValueError("muscle-gain estimation requires at least five scans")
    if ordered["date"].duplicated().any():
        raise ValueError("scan dates must be unique")
    if not np.isfinite(ordered[list(ESTIMATOR_COLUMNS[1:])].to_numpy()).all():
        raise ValueError("DEXA measurements must be finite")
    return ordered


def _validate_assumptions(settings: MuscleGainAssumptions) -> None:
    if settings.simulations < 1:
        raise ValueError("simulations must be at least 1")
    if settings.scan_error_sd_lb < 0:
        raise ValueError("scan error SD must not be negative")
    shares = (
        settings.muscle_share_low,
        settings.muscle_share_high,
    )
    if not (0 <= shares[0] <= shares[1] <= 1):
        raise ValueError("muscle-share bounds must satisfy 0 <= low <= high <= 1")
    if shares[0] == shares[1]:
        raise ValueError("muscle-share range must have positive width")


def _change_window(label: str, start: pd.Series, end: pd.Series) -> ChangeWindow:
    years = (end["date"] - start["date"]).days / 365.2425
    return ChangeWindow(
        label=label,
        start_date=start["date"].date(),
        end_date=end["date"].date(),
        years=float(years),
        weight_change_lb=float(end["weight_lb"] - start["weight_lb"]),
        lean_soft_tissue_change_lb=float(
            end["lean_soft_tissue_lb"] - start["lean_soft_tissue_lb"]
        ),
        bone_mineral_content_change_lb=float(
            end["bone_mineral_content_lb"] - start["bone_mineral_content_lb"]
        ),
        fat_free_mass_change_lb=float(
            end["fat_free_mass_lb"] - start["fat_free_mass_lb"]
        ),
        fat_mass_change_lb=float(end["fat_mass_lb"] - start["fat_mass_lb"]),
    )


def _recent_window(ordered: pd.DataFrame) -> ChangeWindow:
    latest_date = ordered["date"].iloc[-1]
    target = latest_date - pd.DateOffset(years=RECENT_WINDOW_YEARS)
    candidates = ordered.iloc[:-1]
    position = (candidates["date"] - target).abs().idxmin()
    return _change_window(
        f"Nearest {RECENT_WINDOW_YEARS}-year window",
        ordered.loc[position],
        ordered.iloc[-1],
    )


def _regional_sensitivity(
    regions: pd.DataFrame, totals: pd.DataFrame
) -> RegionalSensitivity | None:
    required = {"date", "region", "lean_soft_tissue_lb"}
    if not required.issubset(regions.columns):
        return None
    frame = regions.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    pivot = frame.pivot_table(
        index="date", columns="region", values="lean_soft_tissue_lb", aggfunc="first"
    ).sort_index()
    if len(pivot) < 4 or not {"Arms", "Legs"}.issubset(pivot.columns):
        return None
    pivot = pivot.join(totals.set_index("date")[["weight_lb"]], how="inner")
    if len(pivot) < 4:
        return None
    pivot["appendicular"] = pivot["Arms"] + pivot["Legs"]
    years = (pivot.index - pivot.index[0]).days.to_numpy(dtype=float) / 365.2425
    weights = pivot["weight_lb"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(pivot)), weights - weights.mean(), years])
    span = float(years[-1])

    def adjusted_change(column: str) -> float:
        coefficients, _, _, _ = np.linalg.lstsq(
            design, pivot[column].to_numpy(dtype=float), rcond=None
        )
        return float(coefficients[2] * span)

    return RegionalSensitivity(
        scan_count=len(pivot),
        start_date=pivot.index[0].date(),
        end_date=pivot.index[-1].date(),
        observed_appendicular_change_lb=float(
            pivot["appendicular"].iloc[-1] - pivot["appendicular"].iloc[0]
        ),
        adjusted_appendicular_change_lb=adjusted_change("appendicular"),
        adjusted_arm_change_lb=adjusted_change("Arms"),
        adjusted_leg_change_lb=adjusted_change("Legs"),
    )
