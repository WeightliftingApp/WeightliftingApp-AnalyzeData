"""Shared editorial framing for weightlifting and body-composition charts.

Chart modules own their data marks and annotations. This module owns the visual
frame around them: palette, canvas, headers, axes, footers, and PNG saving.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence, Tuple

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure


@dataclass(frozen=True)
class ChartPalette:
    paper: str = "#f5f2ea"
    panel: str = "#faf8f2"
    ink: str = "#18181b"
    muted: str = "#71717a"
    grid: str = "#d6d3ca"
    trend: str = "#334155"
    neutral_point: str = "#475569"
    positive: str = "#15803d"
    negative: str = "#c2413b"
    latest: str = "#f97316"
    cut: str = "#38bdf8"
    bulk: str = "#ef4444"
    checkpoint: str = "#93c5fd"
    frontier: str = "#2563eb"
    advance: str = "#dc2626"
    advance_ink: str = "#991b1b"
    contour: str = "#a6a198"
    # A secondary reference construct plotted alongside a primary modeled
    # series, such as the constant fat-free-mass ceiling in the bulk forecast.
    reference: str = "#ea580c"


@dataclass(frozen=True)
class ChartFrame:
    figsize: Tuple[float, float]
    dpi: int
    plot_bounds: Tuple[float, float, float, float]
    header_left: float
    header_right: float
    title_y: float
    subtitle_y: float
    metadata_ys: Tuple[float, float]
    footer_y: float
    title_size: float
    subtitle_size: float
    metadata_size: float
    footer_sizes: Tuple[float, float]


@dataclass(frozen=True)
class AxisStyle:
    tick_size: float
    tick_width: float
    tick_length: float | None
    spine_width: float
    grid_width: float
    grid_alpha: float
    axis_below: bool


PALETTE = ChartPalette()
SANS_FONT = "DejaVu Sans"
MONO_FONT = "DejaVu Sans Mono"

TOPOGRAPHY_FRAME = ChartFrame(
    figsize=(10, 8),
    dpi=200,
    plot_bounds=(0.115, 0.95, 0.805, 0.165),
    header_left=0.075,
    header_right=0.95,
    title_y=0.90,
    subtitle_y=0.86,
    metadata_ys=(0.898, 0.858),
    footer_y=0.065,
    title_size=27,
    subtitle_size=13.5,
    metadata_size=9.8,
    footer_sizes=(9.2, 8.6),
)

PARETO_FRAME = ChartFrame(
    figsize=(12, 6.75),
    dpi=200,
    plot_bounds=(0.08, 0.96, 0.82, 0.17),
    header_left=0.09,
    header_right=0.91,
    title_y=0.95,
    subtitle_y=0.912,
    metadata_ys=(0.948, 0.916),
    footer_y=0.04,
    title_size=24,
    subtitle_size=11.5,
    metadata_size=8.5,
    footer_sizes=(8.2, 8.2),
)

FORECAST_FRAME = ChartFrame(
    figsize=(11, 9),
    dpi=200,
    plot_bounds=(0.085, 0.965, 0.885, 0.105),
    header_left=0.065,
    header_right=0.965,
    title_y=0.951,
    subtitle_y=0.920,
    metadata_ys=(0.949, 0.921),
    footer_y=0.038,
    title_size=21,
    subtitle_size=11.5,
    metadata_size=8.2,
    # This card carries a longer model note than the other two, because the
    # simulation has more assumptions to disclose. Both footer strings have to
    # fit on one row without meeting in the middle.
    footer_sizes=(7.8, 7.8),
)

TOPOGRAPHY_AXES = AxisStyle(
    tick_size=10.5,
    tick_width=1.2,
    tick_length=5,
    spine_width=1.2,
    grid_width=1.05,
    grid_alpha=0.72,
    axis_below=False,
)

PARETO_AXES = AxisStyle(
    tick_size=9.5,
    tick_width=1.1,
    tick_length=None,
    spine_width=1.0,
    grid_width=0.9,
    grid_alpha=0.8,
    axis_below=True,
)


def frame_figure(fig: Figure, frame: ChartFrame) -> None:
    """Apply a frame's plot bounds to a figure."""
    left, right, top, bottom = frame.plot_bounds
    fig.subplots_adjust(left=left, right=right, top=top, bottom=bottom)


EDITORIAL_RC = {
    "font.family": SANS_FONT,
    "axes.edgecolor": PALETTE.ink,
    "axes.labelcolor": PALETTE.ink,
    "xtick.color": PALETTE.muted,
    "ytick.color": PALETTE.muted,
}


@contextmanager
def chart_canvas(frame: ChartFrame) -> Iterator[Tuple[Figure, Axes]]:
    """Yield a paper-toned figure and one editorial plot panel."""
    with plt.rc_context(EDITORIAL_RC):
        fig, ax = plt.subplots(figsize=frame.figsize, facecolor=PALETTE.paper)
        ax.set_facecolor(PALETTE.panel)
        frame_figure(fig, frame)
        try:
            yield fig, ax
        except Exception:
            plt.close(fig)
            raise


@contextmanager
def stacked_canvas(
    frame: ChartFrame, height_ratios: Sequence[float], hspace: float,
) -> Iterator[Tuple[Figure, Tuple[Axes, ...]]]:
    """Yield a paper-toned figure and a column of panels sharing one x axis.

    Charts that measure two different quantities against the same x quantity
    stack panels instead of crowding one panel with a second y axis.
    """
    if len(height_ratios) < 2:
        raise ValueError("a stacked canvas needs at least two panels")
    with plt.rc_context(EDITORIAL_RC):
        fig, axes = plt.subplots(
            len(height_ratios),
            1,
            figsize=frame.figsize,
            sharex=True,
            gridspec_kw={"height_ratios": list(height_ratios), "hspace": hspace},
            facecolor=PALETTE.paper,
        )
        for ax in axes:
            ax.set_facecolor(PALETTE.panel)
        frame_figure(fig, frame)
        fig.subplots_adjust(hspace=hspace)
        try:
            yield fig, tuple(axes)
        except Exception:
            plt.close(fig)
            raise


def add_header(
    fig: Figure, frame: ChartFrame, title: str, subtitle: str, metadata: Sequence[str],
) -> None:
    """Add the editorial title block and up to two right-aligned metadata rows."""
    if len(metadata) > len(frame.metadata_ys):
        raise ValueError("chart headers support at most two metadata rows")
    fig.text(
        frame.header_left,
        frame.title_y,
        title,
        fontsize=frame.title_size,
        fontweight="bold",
        color=PALETTE.ink,
        ha="left",
    )
    fig.text(
        frame.header_left,
        frame.subtitle_y,
        subtitle,
        fontsize=frame.subtitle_size,
        color=PALETTE.muted,
        ha="left",
    )
    for text, y in zip(metadata, frame.metadata_ys):
        fig.text(
            frame.header_right,
            y,
            text,
            fontsize=frame.metadata_size,
            family=MONO_FONT,
            color=PALETTE.muted,
            ha="right",
        )


def style_axes(ax: Axes, style: AxisStyle) -> None:
    """Apply the shared grid, tick, and spine treatment to an axes."""
    tick_options = {"labelsize": style.tick_size, "width": style.tick_width}
    if style.tick_length is not None:
        tick_options["length"] = style.tick_length
    ax.tick_params(axis="both", **tick_options)
    ax.grid(
        True, color=PALETTE.grid, linewidth=style.grid_width, alpha=style.grid_alpha,
    )
    ax.set_axisbelow(style.axis_below)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(style.spine_width)
    ax.spines["bottom"].set_linewidth(style.spine_width)


def add_footer(
    fig: Figure,
    frame: ChartFrame,
    left: str,
    right: str,
    *,
    right_color: str | None = None,
    right_weight: str = "bold",
) -> None:
    """Add paired monospace model and reading notes below the plot."""
    fig.text(
        frame.header_left,
        frame.footer_y,
        left,
        fontsize=frame.footer_sizes[0],
        family=MONO_FONT,
        color=PALETTE.muted,
        ha="left",
    )
    fig.text(
        frame.header_right,
        frame.footer_y,
        right,
        fontsize=frame.footer_sizes[1],
        family=MONO_FONT,
        color=right_color or PALETTE.muted,
        fontweight=right_weight,
        ha="right",
    )


def save_chart(
    fig: Figure, output_path: Path, *, dpi: int, bbox_inches: str | None = None,
) -> Path:
    """Save a chart with its figure background, creating parents as needed."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.savefig(
            output_path,
            dpi=dpi,
            bbox_inches=bbox_inches,
            facecolor=fig.get_facecolor(),
        )
    finally:
        plt.close(fig)
    return output_path
