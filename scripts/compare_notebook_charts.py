#!/usr/bin/env python3
"""Build a complete before-and-after gallery for embedded notebook images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from PIL import Image

try:
    from scripts.compare_charts import (
        coarse_metrics,
        contact_sheet,
        image_metadata,
        report_path,
    )
except ModuleNotFoundError:  # Direct execution puts scripts/ on sys.path.
    from compare_charts import (
        coarse_metrics,
        contact_sheet,
        image_metadata,
        report_path,
    )

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = (
    REPO_ROOT
    / ".artifacts"
    / "chart-baselines"
    / "2026-08-22-notebooks-pre-shared-style"
)
AFTER_DIR = REPO_ROOT / ".artifacts" / "chart-comparisons" / "notebooks" / "after"
OUTPUT_DIR = REPO_ROOT / ".artifacts" / "chart-comparisons" / "notebooks"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
OVERVIEW_COLUMNS = 3
OVERVIEW_CELL = (520, 340)


def image_paths(root: Path) -> set[Path]:
    """Return image paths relative to an extracted notebook directory."""
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    }


def build_overview(sheet_paths: list[Path], output_path: Path) -> None:
    """Arrange readable contact-sheet thumbnails on one review canvas."""
    if not sheet_paths:
        return
    rows = (len(sheet_paths) + OVERVIEW_COLUMNS - 1) // OVERVIEW_COLUMNS
    overview = Image.new(
        "RGB",
        (OVERVIEW_CELL[0] * OVERVIEW_COLUMNS, OVERVIEW_CELL[1] * rows),
        "#ece7dd",
    )
    for index, sheet_path in enumerate(sheet_paths):
        with Image.open(sheet_path) as source:
            thumbnail = source.convert("RGB")
            thumbnail.thumbnail((OVERVIEW_CELL[0] - 12, OVERVIEW_CELL[1] - 12))
        column = index % OVERVIEW_COLUMNS
        row = index // OVERVIEW_COLUMNS
        x = column * OVERVIEW_CELL[0] + (OVERVIEW_CELL[0] - thumbnail.width) // 2
        y = row * OVERVIEW_CELL[1] + (OVERVIEW_CELL[1] - thumbnail.height) // 2
        overview.paste(thumbnail, (x, y))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overview.save(output_path)


def compare_notebook_images(
    baseline_dir: Path, after_dir: Path, output_dir: Path
) -> dict[str, object]:
    """Pair extracted outputs by notebook, cell, and output filename."""
    before_paths = image_paths(baseline_dir)
    after_paths = image_paths(after_dir)
    missing_after = sorted(str(path) for path in before_paths - after_paths)
    added_after = sorted(str(path) for path in after_paths - before_paths)
    comparisons = []
    sheet_paths = []

    for relative_path in sorted(before_paths & after_paths):
        before_path = baseline_dir / relative_path
        after_path = after_dir / relative_path
        with Image.open(before_path) as before_source, Image.open(
            after_path
        ) as after_source:
            before = before_source.copy()
            after = after_source.copy()
        metrics, _ = coarse_metrics(before, after)
        sheet_path = output_dir / "side-by-side" / relative_path
        sheet_path.parent.mkdir(parents=True, exist_ok=True)
        contact_sheet(before, after, str(relative_path)).save(sheet_path)
        sheet_paths.append(sheet_path)
        comparisons.append(
            {
                "image": str(relative_path),
                "before": image_metadata(before_path),
                "after": image_metadata(after_path),
                "dimensions_match": before.size == after.size,
                "metrics": metrics,
                "contact_sheet": report_path(sheet_path),
            }
        )

    report = {
        "baseline_count": len(before_paths),
        "after_count": len(after_paths),
        "paired_count": len(comparisons),
        "missing_after": missing_after,
        "added_after": added_after,
        "all_images_paired": not missing_after and not added_after,
        "comparisons": comparisons,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_file = output_dir / "comparison-report.json"
    report_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    gallery_lines = [
        "# Notebook chart before and after gallery",
        "",
        f"Paired images: {len(comparisons)}",
        "",
    ]
    for comparison in comparisons:
        gallery_lines.extend(
            [
                f"## `{comparison['image']}`",
                "",
                f"![Before and after](side-by-side/{comparison['image']})",
                "",
            ]
        )
    (output_dir / "gallery.md").write_text("\n".join(gallery_lines))
    build_overview(sheet_paths, output_dir / "overview.png")
    return report


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=BASELINE_DIR)
    parser.add_argument("--after-dir", type=Path, default=AFTER_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    report = compare_notebook_images(
        args.baseline_dir, args.after_dir, args.output_dir
    )
    summary_keys = (
        "baseline_count",
        "after_count",
        "paired_count",
        "all_images_paired",
        "missing_after",
        "added_after",
    )
    print(json.dumps({key: report[key] for key in summary_keys}, indent=2))
    return 0 if report["all_images_paired"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
