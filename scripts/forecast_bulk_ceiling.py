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
    DEFAULT_SEED,
    DEFAULT_SIMULATIONS,
    DEFAULT_TARGET_BODY_FAT_PCT,
    PREDICTION_COVERAGE,
    SAFETY_CONFIDENCE,
    ForecastAssumptions,
)
from dexa.forecast_pipeline import run_forecast_report  # noqa: E402

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
            "one-standard-deviation DEXA body-fat error in percentage points, "
            "applied to the current scan and to the future scan "
            "(default: %(default)s)"
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
        "--max-weight-lb",
        type=float,
        default=None,
        help=(
            "extrapolation cap; defaults to the current scan weight plus 60 lb, "
            "more than twice the largest bulk on record"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    assumptions = ForecastAssumptions(
        target_body_fat_pct=args.target_body_fat_pct,
        simulations=args.simulations,
        seed=args.seed,
        measurement_error_pp=args.measurement_error_pp,
        partition_noise_scale=args.partition_noise_scale,
        max_weight_lb=args.max_weight_lb,
    )
    forecast, outputs = run_forecast_report(
        args.totals, args.output_dir, assumptions
    )

    target = forecast.assumptions.target_body_fat_pct
    if forecast.is_sparse:
        print(
            f"WARNING: only {forecast.interval_count} positive-weight DEXA "
            "intervals. These are modeled estimates, not calibrated probabilities."
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
        f"{forecast.safety_ceiling_lb:.1f} lb "
        f"({forecast.headroom_lb:+.1f} lb from today)"
    )
    print(f"Median crossing weight:                {forecast.median_crossing_lb:.1f} lb")
    upper = (
        f">{forecast.resolved_max_weight_lb:.1f}"
        if forecast.prediction_high_censored
        else f"{forecast.prediction_high_lb:.1f}"
    )
    print(
        f"Two-sided {PREDICTION_COVERAGE:.0%} prediction interval: "
        f"{forecast.prediction_low_lb:.1f} to {upper} lb"
    )
    print()
    print(f"Wrote {outputs.markdown}")
    print(f"Wrote {outputs.probability_curve}")
    print(f"Wrote {outputs.chart}")


if __name__ == "__main__":
    main()
