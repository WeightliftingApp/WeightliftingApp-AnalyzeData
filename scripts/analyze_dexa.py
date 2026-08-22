#!/usr/bin/env python3
"""Generate the longitudinal DEXA report from existing CSV data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dexa.calculations import (  # noqa: E402,F401
    add_interval_efficiency,
    fit_lean_mass_trend,
    modeled_body_fat_pct,
)
from dexa.pipeline import run_report  # noqa: E402

TOTALS = ROOT / "data" / "dexa.csv"
REGIONS = ROOT / "data" / "dexa_regions.csv"
OUTPUT_DIR = ROOT / "outputs"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--totals", type=Path, default=TOTALS)
    parser.add_argument("--regions", type=Path, default=REGIONS)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    outputs = run_report(args.totals, args.regions, args.output_dir)
    print(f"Wrote {outputs.markdown}")
    print(f"Wrote {outputs.composition_chart}")
    print(f"Wrote {outputs.lean_mass_chart}")


if __name__ == "__main__":
    main()
