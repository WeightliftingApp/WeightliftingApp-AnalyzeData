#!/usr/bin/env python3
"""Render deterministic, synthetic reference cards for each chart archetype."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from chart_lint import assert_chart_lint_clean
from chart_style import (
    CATEGORICAL_COLORS,
    NOTEBOOK_AXES,
    PALETTE,
    AnnotationKind,
    ChartArchetype,
    add_footer,
    add_header,
    annotate_point,
    chart_canvas,
    label_line_ends,
    notebook_frame,
    save_chart,
    style_axes,
)


def render_hero(output_dir: Path) -> Path:
    frame = notebook_frame((10, 6), dpi=140, archetype=ChartArchetype.HERO)
    x = np.arange(8)
    values = np.array([315, 323, 328, 334, 337, 344, 350, 356])
    with chart_canvas(frame) as (fig, ax):
        ax.plot(x, values, color=PALETTE.frontier, linewidth=2.2)
        annotate_point(
            ax,
            x[-1],
            values[-1],
            "+41 LB",
            kind=AnnotationKind.CHANGE,
            xytext=(-8, 12),
            ha="right",
        )
        ax.set_xlabel("TRAINING BLOCK")
        ax.set_ylabel("ESTIMATED 1RM (LB)")
        ax.set_xticks(x, [str(value) for value in range(1, 9)])
        style_axes(ax, NOTEBOOK_AXES)
        add_header(
            fig,
            frame,
            "Estimated 1RM Progression",
            "Eight synthetic training blocks with the total change annotated",
            ("8 BLOCKS", "REFERENCE DATA"),
        )
        add_footer(
            fig,
            frame,
            "SYNTHETIC EXAMPLE  /  NOT A PERSONAL RESULT",
            "BLUE = ESTABLISHED TREND",
            right_weight="normal",
        )
        assert_chart_lint_clean(fig, expected_units={(0, "y"): "LB"})
        return save_chart(fig, output_dir / "hero.png", dpi=frame.dpi)


def render_comparison(output_dir: Path) -> Path:
    frame = notebook_frame((10, 6), dpi=140, archetype=ChartArchetype.COMPARISON)
    x = np.arange(7)
    series = {
        "BENCH": np.array([72, 74, 77, 79, 82, 84, 88]),
        "SQUAT": np.array([68, 72, 75, 80, 83, 87, 91]),
        "DEADLIFT": np.array([75, 76, 80, 81, 85, 89, 94]),
    }
    with chart_canvas(frame) as (fig, ax):
        lines = []
        for (label, values), color in zip(series.items(), CATEGORICAL_COLORS):
            line, = ax.plot(
                x,
                values,
                color=color,
                linewidth=2,
                marker="o",
                markersize=3.5,
                label=label,
            )
            lines.append(line)
        ax.margins(x=0.1)
        label_line_ends(ax, lines, min_gap_points=14)
        ax.set_xlabel("TRAINING BLOCK")
        ax.set_ylabel("INDEXED ESTIMATED 1RM")
        ax.set_xticks(x, [str(value) for value in range(1, 8)])
        style_axes(ax, NOTEBOOK_AXES)
        add_header(
            fig,
            frame,
            "Big Three Relative Progression",
            "Direct labels replace a legend when every series has a meaningful endpoint",
            (),
        )
        add_footer(
            fig,
            frame,
            "SYNTHETIC INDEX  /  FIRST BLOCK NORMALIZED NEAR 70",
            "END LABELS FOLLOW EACH SERIES",
            right_weight="normal",
        )
        assert_chart_lint_clean(fig)
        return save_chart(fig, output_dir / "comparison.png", dpi=frame.dpi)


def render_diagnostic(output_dir: Path) -> Path:
    frame = notebook_frame((10, 6), dpi=140, archetype=ChartArchetype.DIAGNOSTIC)
    fitted = np.linspace(250, 450, 36)
    residuals = 8 * np.sin(np.linspace(0, 4 * np.pi, len(fitted)))
    colors = np.where(residuals >= 0, PALETTE.positive, PALETTE.negative)
    with chart_canvas(frame) as (fig, ax):
        ax.axhline(0, color=PALETTE.ink, linewidth=1, alpha=0.6)
        ax.scatter(fitted, residuals, c=colors, s=24, alpha=0.82)
        ax.set_xlabel("FITTED ESTIMATED 1RM (LB)")
        ax.set_ylabel("RESIDUAL (LB)")
        style_axes(ax, NOTEBOOK_AXES)
        add_header(
            fig,
            frame,
            "Residuals Across the Fitted Range",
            "Dense diagnostic evidence receives more canvas and a quieter header",
            ("36 POINTS",),
        )
        add_footer(
            fig,
            frame,
            "SYNTHETIC MODEL CHECK",
            "GREEN = ABOVE FIT  /  RED = BELOW FIT",
            right_weight="normal",
        )
        assert_chart_lint_clean(
            fig,
            expected_units={(0, "x"): "LB", (0, "y"): "LB"},
        )
        return save_chart(fig, output_dir / "diagnostic.png", dpi=frame.dpi)


def render_gallery(output_dir: Path) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return (
        render_hero(output_dir),
        render_comparison(output_dir),
        render_diagnostic(output_dir),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".artifacts/chart-language-gallery"),
    )
    args = parser.parse_args()
    for path in render_gallery(args.output_dir):
        print(path)


if __name__ == "__main__":
    main()
