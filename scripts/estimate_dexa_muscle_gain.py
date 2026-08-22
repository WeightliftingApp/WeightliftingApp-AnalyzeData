#!/usr/bin/env python3
"""Estimate longitudinal skeletal-muscle change from repeated DEXA scans."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dexa.muscle_gain import (  # noqa: E402
    DEFAULT_SCAN_ERROR_SD_LB,
    DEFAULT_SEED,
    DEFAULT_SIMULATIONS,
    MuscleGainAssumptions,
)
from dexa.muscle_gain_pipeline import run_muscle_gain_report  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--totals", type=Path, required=True)
    parser.add_argument("--regions", type=Path, required=True)
    parser.add_argument("--training-log", type=Path, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / ".artifacts" / "dexa-muscle-gain",
    )
    parser.add_argument("--simulations", type=int, default=DEFAULT_SIMULATIONS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--scan-error-sd-lb", type=float, default=DEFAULT_SCAN_ERROR_SD_LB
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    assumptions = MuscleGainAssumptions(
        simulations=args.simulations,
        seed=args.seed,
        scan_error_sd_lb=args.scan_error_sd_lb,
    )
    estimate, _, outputs = run_muscle_gain_report(
        args.totals,
        args.regions,
        args.output_dir,
        assumptions,
        args.training_log,
    )
    print(
        f"Estimated muscle change: {estimate.muscle_gain_median_lb:.1f} lb "
        f"(95% {estimate.muscle_gain_low_95_lb:+.1f} to "
        f"{estimate.muscle_gain_high_95_lb:+.1f} lb)"
    )
    print(f"Wrote {outputs.report}")
    print(f"Wrote {outputs.chart}")


if __name__ == "__main__":
    main()
