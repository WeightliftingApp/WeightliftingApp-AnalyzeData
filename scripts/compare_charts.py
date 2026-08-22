#!/usr/bin/env python3
"""Generate and compare the shared-style charts against preserved baselines.

The changed-pixel fraction only measures a chart's fidelity when both images
came out of the same Matplotlib. Matplotlib 3.11 moved from FreeType 2.6.1 to
2.14, which changes glyph advances by a fraction of a pixel. Those fractions
accumulate along a string, so an editorial card covered in monospace metadata
re-flows by a few pixels per label with nothing about the chart changed.

Measured on this repository's two baselines, with the generators untouched:

    same Matplotlib 3.10.0   dexa 0.000000   bench 0.000000
    Matplotlib 3.11.1        dexa 0.035192   bench (no 3.10 source to rerun)

The shared-style migration itself, measured under one Matplotlib, moved
0.000548 of the DEXA card and none of the bench card. So a 3.5% reading across
a renderer change is typography, not a lost claim, and a threshold that treats
it as a regression is telling the reviewer something false.

This script therefore reads the renderer out of each PNG and says which
question it can answer. Matching renderers get the strict fidelity gate.
Mismatched renderers get a gross-change ceiling and an explicit refusal to
certify, which `--accept-renderer-drift` records the reviewer overriding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
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

# Fidelity gate, applied only when both images came out of one renderer. The
# faithful shared-style migration measured 0.000548 against this baseline set,
# so this leaves better than an order of magnitude of headroom.
MAX_CHANGED_PIXEL_FRACTION = 0.01

# Gross-change ceiling for a cross-renderer run. Text re-flow between
# Matplotlib 3.10 and 3.11 reached 0.0352 on the text-heaviest of these cards,
# so this sits roughly four times above the observed typographic floor. It
# catches a blank canvas, the wrong chart, or an inverted palette. It says
# nothing about whether a label or a point survived.
MAX_CROSS_RENDERER_CHANGED_FRACTION = 0.15

MATPLOTLIB_SOFTWARE = re.compile(r"Matplotlib version\s*([0-9][0-9A-Za-z.+-]*)")


def report_path(path: Path) -> str:
    """Prefer repository-relative paths so reports survive worktree moves."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def read_renderer(image: Image.Image) -> str | None:
    """Name the Matplotlib that rasterized a PNG, or None if it does not say.

    Matplotlib stamps its version into the PNG `Software` chunk. That is the
    only record of which FreeType drew the glyphs, and it is what decides
    whether a changed-pixel fraction means anything.
    """
    software = image.info.get("Software")
    if not isinstance(software, str):
        return None
    match = MATPLOTLIB_SOFTWARE.search(software)
    return f"matplotlib {match.group(1)}" if match else software.strip() or None


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
            "renderer": read_renderer(image),
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


def evaluate_comparison(
    dimensions_match: bool,
    changed_pixel_fraction: float,
    threshold: float = MAX_CHANGED_PIXEL_FRACTION,
    *,
    before_renderer: str | None = None,
    after_renderer: str | None = None,
    accept_renderer_drift: bool = False,
    cross_renderer_threshold: float = MAX_CROSS_RENDERER_CHANGED_FRACTION,
) -> Dict[str, object]:
    """Apply the broad regression gate that the two renderers actually support.

    Dimensions are gated either way. The changed-pixel fraction is a fidelity
    signal only when one renderer drew both images; across renderers it is
    dominated by glyph re-flow, so it drops to a gross-change ceiling and the
    run refuses to certify until a reviewer acknowledges the mismatch.
    """
    # Two PNGs that do not name a renderer are not a match. They are two
    # unknowns, and an unknown renderer is exactly the case this gate cannot
    # certify. Only a named renderer on both sides earns the strict threshold.
    renderer_match = before_renderer is not None and before_renderer == after_renderer
    if renderer_match:
        applied = threshold
        mode = "strict"
    else:
        applied = cross_renderer_threshold
        mode = "cross-renderer"

    failures = []
    notes = []
    if not dimensions_match:
        failures.append("dimensions differ")
    if changed_pixel_fraction > applied:
        failures.append(
            f"changed-pixel fraction {changed_pixel_fraction:.6f} exceeds "
            f"{applied:.6f}"
        )
    if not renderer_match:
        pair = f"{before_renderer or 'unknown'} -> {after_renderer or 'unknown'}"
        reason = (
            "came from different renderers"
            if before_renderer and after_renderer
            else "do not both record which renderer drew them"
        )
        notes.append(
            f"baseline and result {reason} ({pair}); the changed-pixel "
            "fraction measures glyph re-flow as well as the chart, so only "
            f"the {cross_renderer_threshold:.2f} gross-change ceiling applies"
        )
        if accept_renderer_drift:
            notes.append("reviewer accepted the renderer mismatch")
        else:
            failures.append(
                "renderer mismatch is not certifiable by pixel count; rerun "
                f"under {before_renderer or 'the baseline renderer'}, or pass "
                "--accept-renderer-drift after reviewing the contact sheets"
            )
    return {
        "passed": not failures,
        "mode": mode,
        "renderer_match": renderer_match,
        "max_changed_pixel_fraction": applied,
        "failures": failures,
        "notes": notes,
    }


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
    before_path: Path,
    after_path: Path,
    output_dir: Path,
    *,
    accept_renderer_drift: bool = False,
) -> Dict[str, object]:
    """Write one contact sheet and diff image, then return comparison metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(before_path) as before_source, Image.open(
        after_path
    ) as after_source:
        before = before_source.copy()
        after = after_source.copy()
    metrics, difference = coarse_metrics(before, after)
    before_meta = image_metadata(before_path)
    after_meta = image_metadata(after_path)
    stem = before_path.stem
    contact_path = output_dir / f"{stem}-side-by-side.png"
    diff_path = output_dir / f"{stem}-diff.png"
    contact_sheet(before, after, before_path.name).save(contact_path)
    difference.save(diff_path)
    dimensions_match = before.size == after.size
    return {
        "chart": before_path.name,
        "before": before_meta,
        "after": after_meta,
        "dimensions_match": dimensions_match,
        "metrics": metrics,
        "broad_check": evaluate_comparison(
            dimensions_match,
            metrics["changed_pixel_fraction_over_8"],
            before_renderer=before_meta["renderer"],
            after_renderer=after_meta["renderer"],
            accept_renderer_drift=accept_renderer_drift,
        ),
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
    baseline_dir: Path,
    after_dir: Path,
    output_dir: Path,
    chart_names: Iterable[str],
    *,
    accept_renderer_drift: bool = False,
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
        comparisons.append(
            compare_pair(
                before_path,
                after_path,
                output_dir,
                accept_renderer_drift=accept_renderer_drift,
            )
        )
    report = {
        "broad_check_passed": all(
            comparison["broad_check"]["passed"] for comparison in comparisons
        ),
        "renderer_match": all(
            comparison["broad_check"]["renderer_match"] for comparison in comparisons
        ),
        "accepted_renderer_drift": accept_renderer_drift,
        "comparisons": comparisons,
    }
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
    parser.add_argument(
        "--accept-renderer-drift",
        action="store_true",
        help=(
            "Record that a reviewer read the contact sheets and accepts a "
            "baseline drawn by a different Matplotlib. Without it a "
            "cross-renderer run refuses to certify, because the changed-pixel "
            "fraction then measures glyph re-flow as well as the chart."
        ),
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    args = parse_args(argv)
    if args.generate:
        generate_charts(args.after_dir)
    report = compare_all(
        args.baseline_dir,
        args.after_dir,
        args.output_dir,
        args.charts,
        accept_renderer_drift=args.accept_renderer_drift,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["broad_check_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
