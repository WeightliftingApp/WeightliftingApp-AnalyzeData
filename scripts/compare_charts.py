#!/usr/bin/env python3
"""Generate and compare the shared-style charts against preserved baselines."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageStat

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

BASELINE_DIR = (
    REPO_ROOT / ".artifacts" / "chart-baselines" / "2026-08-21-pre-shared-style"
)
COMPARISON_DIR = REPO_ROOT / ".artifacts" / "chart-comparisons"
CHARTS = (
    "dexa-lean-mass-vs-bodyweight.png",
    "bench-strength-eval-update-2026-08-21.png",
)
LABEL_HEIGHT = 28
GAP = 8


def report_path(path: Path) -> str:
    """Prefer repository-relative paths so reports survive worktree moves."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def image_metadata(path: Path) -> Dict[str, object]:
    """Return stable file and pixel metadata without modifying the image."""
    with Image.open(path) as image:
        return {
            "path": report_path(path),
            "dimensions": list(image.size),
            "mode": image.mode,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mean_luma": round(ImageStat.Stat(image.convert("L")).mean[0], 4),
        }


def normalized_pair(
    before: Image.Image, after: Image.Image
) -> Tuple[Image.Image, Image.Image]:
    """Place both images on equal transparent canvases for coarse comparison."""
    width = max(before.width, after.width)
    height = max(before.height, after.height)
    canvases = []
    for image in (before, after):
        canvas = Image.new("RGBA", (width, height), "white")
        canvas.paste(image.convert("RGBA"), (0, 0))
        canvases.append(canvas)
    return canvases[0], canvases[1]


def coarse_metrics(
    before: Image.Image, after: Image.Image
) -> Tuple[Dict[str, float], Image.Image]:
    """Measure broad pixel drift and return a visible grayscale heat map."""
    before, after = normalized_pair(before, after)
    difference = ImageChops.difference(before, after).convert("RGB")
    pixels = difference.width * difference.height
    histogram = difference.histogram()
    channel_samples = pixels * 3
    absolute_sum = sum(
        value * count
        for channel in range(3)
        for value, count in enumerate(histogram[channel * 256 : (channel + 1) * 256])
    )
    squared_sum = sum(
        value * value * count
        for channel in range(3)
        for value, count in enumerate(histogram[channel * 256 : (channel + 1) * 256])
    )
    gray = difference.convert("L")
    changed = sum(gray.histogram()[9:])
    visible = ImageOps.colorize(
        ImageOps.autocontrast(gray), black="#f5f2ea", white="#dc2626"
    )
    return (
        {
            "mean_abs_channel_difference": round(absolute_sum / channel_samples, 4),
            "rms_channel_difference": round(
                math.sqrt(squared_sum / channel_samples), 4
            ),
            "changed_pixel_fraction_over_8": round(changed / pixels, 6),
        },
        visible,
    )


def contact_sheet(
    before: Image.Image, after: Image.Image, filename: str
) -> Image.Image:
    """Place before and after images side by side with small deterministic labels."""
    before = before.convert("RGB")
    after = after.convert("RGB")
    height = max(before.height, after.height)
    sheet = Image.new(
        "RGB", (before.width + after.width + GAP, height + LABEL_HEIGHT), "#ece7dd",
    )
    sheet.paste(before, (0, LABEL_HEIGHT))
    sheet.paste(after, (before.width + GAP, LABEL_HEIGHT))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    draw.text((8, 8), f"BEFORE  {filename}", fill="#18181b", font=font)
    draw.text(
        (before.width + GAP + 8, 8), f"AFTER  {filename}", fill="#18181b", font=font,
    )
    return sheet


def compare_pair(
    before_path: Path, after_path: Path, output_dir: Path
) -> Dict[str, object]:
    """Write one contact sheet and diff image, then return comparison metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(before_path) as before_source, Image.open(
        after_path
    ) as after_source:
        before = before_source.copy()
        after = after_source.copy()
    metrics, difference = coarse_metrics(before, after)
    stem = before_path.stem
    contact_path = output_dir / f"{stem}-side-by-side.png"
    diff_path = output_dir / f"{stem}-diff.png"
    contact_sheet(before, after, before_path.name).save(contact_path)
    difference.save(diff_path)
    return {
        "chart": before_path.name,
        "before": image_metadata(before_path),
        "after": image_metadata(after_path),
        "dimensions_match": before.size == after.size,
        "metrics": metrics,
        "contact_sheet": report_path(contact_path),
        "diff_image": report_path(diff_path),
    }


def generate_charts(after_dir: Path) -> None:
    """Run both migrated generators into the ignored comparison directory."""
    from dexa.pipeline import run_report
    from generate_bench_frontier_update import build_chart

    after_dir.mkdir(parents=True, exist_ok=True)
    run_report(
        REPO_ROOT / "data" / "dexa.csv",
        REPO_ROOT / "data" / "dexa_regions.csv",
        after_dir,
    )
    build_chart(output_path=after_dir / "bench-strength-eval-update-2026-08-21.png")


def compare_all(
    baseline_dir: Path, after_dir: Path, output_dir: Path, chart_names: Iterable[str],
) -> Dict[str, object]:
    """Compare all requested filenames and write a stable JSON report."""
    comparisons: List[Dict[str, object]] = []
    for name in chart_names:
        before_path = baseline_dir / name
        after_path = after_dir / name
        if not before_path.is_file():
            raise FileNotFoundError(f"Missing baseline image: {before_path}")
        if not after_path.is_file():
            raise FileNotFoundError(f"Missing post-migration image: {after_path}")
        comparisons.append(compare_pair(before_path, after_path, output_dir))
    report = {"comparisons": comparisons}
    report_path = output_dir / "comparison-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=BASELINE_DIR)
    parser.add_argument("--after-dir", type=Path, default=COMPARISON_DIR / "after")
    parser.add_argument("--output-dir", type=Path, default=COMPARISON_DIR)
    parser.add_argument("--charts", nargs="+", default=list(CHARTS))
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Run both chart generators into --after-dir before comparing.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    args = parse_args(argv)
    if args.generate:
        generate_charts(args.after_dir)
    report = compare_all(
        args.baseline_dir, args.after_dir, args.output_dir, args.charts,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
