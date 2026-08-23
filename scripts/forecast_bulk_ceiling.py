#!/usr/bin/env python3
"""Forecast the bodyweight at which a target DEXA body-fat reading is reached.

Reads the DEXA totals CSV. Never writes to it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dexa.forecast import (  # noqa: E402
    DEFAULT_MEASUREMENT_ERROR_PP,
    DEFAULT_PARTITION_NOISE_SCALE,
    DEFAULT_RESAMPLE_UNIT,
    DEFAULT_SEED,
    DEFAULT_SIMULATIONS,
    DEFAULT_TARGET_BODY_FAT_PCT,
    DEFAULT_WEIGHT_LOG_WEEKS,
    PREDICTION_COVERAGE,
    PREDICTION_COVERAGE_INNER,
    RESAMPLE_UNITS,
    SAFETY_CONFIDENCE,
    ForecastAssumptions,
    PlanningInputs,
)
from dexa.forecast_pipeline import (  # noqa: E402
    planning_from_weight_log,
    run_forecast_report,
)

TOTALS = ROOT / "data" / "dexa.csv"
OUTPUT_DIR = ROOT / "outputs"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--totals", type=Path, default=TOTALS, help="DEXA totals CSV to read"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="directory to write the report, CSV, and chart into",
    )
    parser.add_argument(
        "--target-body-fat-pct",
        type=float,
        default=DEFAULT_TARGET_BODY_FAT_PCT,
        help="body-fat percentage to stay under (default: %(default)s)",
    )
    parser.add_argument(
        "--simulations",
        type=int,
        default=DEFAULT_SIMULATIONS,
        help="resampling draws (default: %(default)s)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="random seed; fixed so runs reproduce (default: %(default)s)",
    )
    parser.add_argument(
        "--measurement-error-pp",
        type=float,
        default=DEFAULT_MEASUREMENT_ERROR_PP,
        help=(
            "one-standard-deviation DXA body-fat error in percentage points, "
            "applied to the current scan and to the future scan. The default is "
            "the DXA-specific between-day figure; 0.8 is a deliberately "
            "conservative all-method value (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--partition-noise-scale",
        type=float,
        default=DEFAULT_PARTITION_NOISE_SCALE,
        help=(
            "multiplier on the resampled interval-to-interval spread of the "
            "fat-free gain fraction; 0 removes the future-bulk deviation term "
            "(default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--resample-unit",
        choices=RESAMPLE_UNITS,
        default=DEFAULT_RESAMPLE_UNIT,
        help=(
            "'block' groups intervals that share a scan so their common "
            "measurement error is not counted twice; 'interval' treats every "
            "interval as independent (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--max-weight-lb",
        type=float,
        default=None,
        help=(
            "extrapolation cap; defaults to the current scan weight plus 60 lb. "
            "Quantiles above the cap are reported as censored, never clamped"
        ),
    )
    planning = parser.add_argument_group(
        "planning inputs",
        "Optional. Neither has a silent default: without a current bodyweight "
        "headroom is measured from the DEXA scan weight and labelled as such, "
        "and without a rate no duration is reported.",
    )
    planning.add_argument(
        "--current-bodyweight-lb",
        type=float,
        default=None,
        help="smoothed bodyweight today, for headroom and duration",
    )
    planning.add_argument(
        "--weekly-bulk-rate-lb",
        type=float,
        default=None,
        help="intended gain in pounds per week; must be positive",
    )
    planning.add_argument(
        "--weight-log",
        type=Path,
        default=None,
        help=(
            "optional weekly bodyweight CSV with 'Week of' and 'Average' columns, "
            "averaged into a current bodyweight. No default path. A rate is never "
            "inferred from it"
        ),
    )
    planning.add_argument(
        "--weight-log-weeks",
        type=int,
        default=DEFAULT_WEIGHT_LOG_WEEKS,
        help="weekly averages to smooth over (default: %(default)s)",
    )
    return parser.parse_args(argv)


def build_planning(args: argparse.Namespace) -> PlanningInputs:
    if args.weight_log is not None and args.current_bodyweight_lb is not None:
        raise ValueError(
            "pass either --current-bodyweight-lb or --weight-log, not both"
        )
    if args.weight_log is not None:
        return planning_from_weight_log(
            args.weight_log,
            weeks=args.weight_log_weeks,
            weekly_bulk_rate_lb=args.weekly_bulk_rate_lb,
        )
    return PlanningInputs(
        current_bodyweight_lb=args.current_bodyweight_lb,
        weekly_bulk_rate_lb=args.weekly_bulk_rate_lb,
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    assumptions = ForecastAssumptions(
        target_body_fat_pct=args.target_body_fat_pct,
        simulations=args.simulations,
        seed=args.seed,
        measurement_error_pp=args.measurement_error_pp,
        partition_noise_scale=args.partition_noise_scale,
        resample_unit=args.resample_unit,
        max_weight_lb=args.max_weight_lb,
    )
    forecast, outputs = run_forecast_report(
        args.totals, args.output_dir, assumptions, build_planning(args)
    )

    target = forecast.assumptions.target_body_fat_pct
    if forecast.is_sparse:
        print(
            f"WARNING: {forecast.interval_count} positive-weight DEXA intervals "
            f"carrying {forecast.resampling_unit_count} independent resampling "
            "units. These are modeled estimates, not calibrated probabilities."
        )
    print(f"Target body fat: {target:g}%")
    print(
        f"Current scan:    {forecast.current_weight_lb:.1f} lb at "
        f"{forecast.current_body_fat_pct:.2f}% ({forecast.current_date})"
    )
    print(
        f"Constant-FFM reference (deterministic): "
        f"{forecast.constant_ffm_ceiling_lb:.1f} lb"
    )
    print(
        f"One-sided {SAFETY_CONFIDENCE:.0%} safety ceiling:        "
        f"{forecast.safety_ceiling.describe_short()}"
    )
    print(
        f"Median crossing weight:                "
        f"{forecast.median_crossing.describe_short()}"
    )
    print(
        f"Two-sided {PREDICTION_COVERAGE_INNER:.0%} prediction interval: "
        f"{forecast.prediction_low_80.describe_short()} to "
        f"{forecast.prediction_high_80.describe_short()}"
    )
    print(
        f"Two-sided {PREDICTION_COVERAGE:.0%} prediction interval: "
        f"{forecast.prediction_low_95.describe_short()} to "
        f"{forecast.prediction_high_95.describe_short()}"
    )

    plan = forecast.planning
    print()
    print(f"Planning from {plan.current_bodyweight_lb:.1f} lb ({plan.bodyweight_source})")
    if plan.headroom_lb is None:
        print(f"  Headroom: unavailable, {plan.unavailable_reason}")
    else:
        print(f"  Headroom to the safety ceiling: {plan.headroom_lb:+.1f} lb")
    if plan.weeks_to_ceiling is None:
        print(f"  Duration: unavailable, {plan.unavailable_reason}")
    elif plan.weeks_to_ceiling == 0.0:
        print("  Duration: already at or past the safety ceiling")
    else:
        print(
            f"  Weeks to the safety ceiling at "
            f"{plan.weekly_bulk_rate_lb:.2f} lb/week: {plan.weeks_to_ceiling:.1f}"
        )

    score = forecast.predictive_score
    if score is not None:
        print()
        print(
            f"Held-out check: {score.coverage_80:.0%} inside "
            f"{PREDICTION_COVERAGE_INNER:.0%}, {score.coverage_95:.0%} inside "
            f"{PREDICTION_COVERAGE:.0%}, median absolute error "
            f"{score.median_absolute_error_pp:.2f} pp over {len(score.folds)} folds"
        )

    print()
    print(f"Wrote {outputs.markdown}")
    print(f"Wrote {outputs.probability_curve}")
    print(f"Wrote {outputs.chart}")


if __name__ == "__main__":
    main()
