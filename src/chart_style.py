"""Shared editorial framing for weightlifting and body-composition charts.

Chart modules own their data marks and annotations. This module owns the visual
frame around them: palette, canvas, headers, axes, footers, and PNG saving.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence, Tuple

import matplotlib.pyplot as plt
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.text import Annotation
from matplotlib.ticker import FuncFormatter


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


class ChartArchetype(str, Enum):
    """Information-density presets for notebook analytical cards."""

    HERO = "hero"
    COMPARISON = "comparison"
    DIAGNOSTIC = "diagnostic"


class AnnotationKind(str, Enum):
    """Shared visual vocabulary for claims placed near chart evidence."""

    LATEST = "LATEST"
    NEW_HIGH = "NEW HIGH"
    CHANGE = "CHANGE"
    ESTIMATE = "ESTIMATE"
    RANGE_95 = "95% RANGE"
    REFERENCE = "REFERENCE"


@dataclass(frozen=True)
class AnnotationStyle:
    color: str
    marker: str


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

# Notebook charts keep their original figure dimensions while sharing the same
# paper, type, spacing, grid, and legend treatment as the published cards.
NOTEBOOK_AXES = AxisStyle(
    tick_size=9.5,
    tick_width=1.0,
    tick_length=4,
    spine_width=1.0,
    grid_width=0.85,
    grid_alpha=0.68,
    axis_below=True,
)

CATEGORICAL_COLORS = (
    "#3b5b92",
    "#b4534b",
    "#3f7d5b",
    "#b7791f",
    "#76558f",
    "#287f8d",
    "#8a6343",
)


ANNOTATION_STYLES: Mapping[AnnotationKind, AnnotationStyle] = {
    AnnotationKind.LATEST: AnnotationStyle(PALETTE.latest, "o"),
    AnnotationKind.NEW_HIGH: AnnotationStyle(PALETTE.advance, "D"),
    AnnotationKind.CHANGE: AnnotationStyle(PALETTE.frontier, "o"),
    AnnotationKind.ESTIMATE: AnnotationStyle(PALETTE.frontier, "o"),
    AnnotationKind.RANGE_95: AnnotationStyle(PALETTE.muted, "|"),
    AnnotationKind.REFERENCE: AnnotationStyle(PALETTE.reference, "s"),
}


_NOTEBOOK_ARCHETYPE_LAYOUTS = {
    ChartArchetype.HERO: {
        "plot_bounds": (0.09, 0.96, 0.77, 0.18),
        "title_y": 0.93,
        "subtitle_y": 0.88,
        "metadata_ys": (0.928, 0.884),
        "footer_y": 0.055,
        "title_size": 21.5,
        "subtitle_size": 10.8,
        "metadata_size": 8.5,
        "footer_sizes": (8.0, 8.0),
    },
    ChartArchetype.COMPARISON: {
        "plot_bounds": (0.09, 0.96, 0.80, 0.17),
        "title_y": 0.93,
        "subtitle_y": 0.885,
        "metadata_ys": (0.928, 0.888),
        "footer_y": 0.055,
        "title_size": 20.0,
        "subtitle_size": 10.5,
        "metadata_size": 8.5,
        "footer_sizes": (8.0, 8.0),
    },
    ChartArchetype.DIAGNOSTIC: {
        "plot_bounds": (0.08, 0.97, 0.84, 0.14),
        "title_y": 0.945,
        "subtitle_y": 0.902,
        "metadata_ys": (0.942, 0.904),
        "footer_y": 0.045,
        "title_size": 16.0,
        "subtitle_size": 9.5,
        "metadata_size": 7.8,
        "footer_sizes": (7.4, 7.4),
    },
}


def notebook_frame(
    figsize: Tuple[float, float],
    *,
    dpi: int = 100,
    archetype: ChartArchetype | str = ChartArchetype.COMPARISON,
) -> ChartFrame:
    """Create an archetype-aware frame without changing a chart's size."""
    try:
        resolved_archetype = ChartArchetype(archetype)
    except ValueError as exc:
        choices = ", ".join(item.value for item in ChartArchetype)
        raise ValueError(f"unknown chart archetype {archetype!r}; choose {choices}") from exc
    layout = _NOTEBOOK_ARCHETYPE_LAYOUTS[resolved_archetype]
    return ChartFrame(
        figsize=figsize,
        dpi=dpi,
        plot_bounds=layout["plot_bounds"],
        header_left=0.075,
        header_right=0.95,
        title_y=layout["title_y"],
        subtitle_y=layout["subtitle_y"],
        metadata_ys=layout["metadata_ys"],
        footer_y=layout["footer_y"],
        title_size=layout["title_size"],
        subtitle_size=layout["subtitle_size"],
        metadata_size=layout["metadata_size"],
        footer_sizes=layout["footer_sizes"],
    )


def format_weight(value: float, *, decimals: int = 0, unit: str = "lb") -> str:
    """Format a weight with repository-standard grouping and units."""
    return f"{value:,.{decimals}f} {unit}"


def format_percent(value: float, *, decimals: int = 0, signed: bool = False) -> str:
    """Format a percentage that is already expressed on a 0-to-100 scale."""
    sign = "+" if signed else ""
    return f"{value:{sign}.{decimals}f}%"


def format_count(value: float) -> str:
    """Format an integer count with thousands separators."""
    return f"{round(value):,}"


def format_delta(value: float, *, decimals: int = 1, unit: str = "lb") -> str:
    """Format a signed change with units."""
    return f"{value:+,.{decimals}f} {unit}"


def weight_axis_formatter(*, decimals: int = 0, unit: str = "lb") -> FuncFormatter:
    """Return a Matplotlib formatter for weight axes."""
    return FuncFormatter(lambda value, _: format_weight(value, decimals=decimals, unit=unit))


def percent_axis_formatter(*, decimals: int = 0) -> FuncFormatter:
    """Return a Matplotlib formatter for percentage axes."""
    return FuncFormatter(lambda value, _: format_percent(value, decimals=decimals))


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
        fig, ax = plt.subplots(
            figsize=frame.figsize,
            dpi=frame.dpi,
            facecolor=PALETTE.paper,
        )
        ax.set_facecolor(PALETTE.panel)
        frame_figure(fig, frame)
        try:
            yield fig, ax
        except Exception:
            plt.close(fig)
            raise


@contextmanager
def stacked_canvas(
    frame: ChartFrame,
    height_ratios: Sequence[float],
    hspace: float,
    *,
    sharex: bool = True,
) -> Iterator[Tuple[Figure, Tuple[Axes, ...]]]:
    """Yield a paper-toned figure and a column of editorial panels.

    Charts that measure two different quantities against the same x quantity
    stack panels instead of crowding one panel with a second y axis. Set
    ``sharex=False`` when the panels use different x quantities.
    """
    if len(height_ratios) < 2:
        raise ValueError("a stacked canvas needs at least two panels")
    with plt.rc_context(EDITORIAL_RC):
        fig, axes = plt.subplots(
            len(height_ratios),
            1,
            figsize=frame.figsize,
            dpi=frame.dpi,
            sharex=sharex,
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


def style_legend(ax: Axes, **kwargs):
    """Create a compact legend that matches the shared notebook frame."""
    legend = ax.legend(
        frameon=True,
        facecolor=PALETTE.panel,
        edgecolor=PALETTE.grid,
        framealpha=0.96,
        prop={"family": MONO_FONT, "size": 8.5},
        **kwargs,
    )
    return legend


def annotation_style(kind: AnnotationKind | str) -> AnnotationStyle:
    """Resolve a shared annotation kind to its color and marker."""
    try:
        resolved_kind = AnnotationKind(kind)
    except ValueError as exc:
        choices = ", ".join(item.value for item in AnnotationKind)
        raise ValueError(f"unknown annotation kind {kind!r}; choose {choices}") from exc
    return ANNOTATION_STYLES[resolved_kind]


def annotate_point(
    ax: Axes,
    x,
    y: float,
    detail: str,
    *,
    kind: AnnotationKind | str,
    xytext: Tuple[float, float] = (8, 10),
    ha: str = "left",
    va: str = "bottom",
    mark: bool = True,
) -> Annotation:
    """Mark evidence with a standard tag and a short chart-specific detail."""
    resolved_kind = AnnotationKind(kind)
    visual = annotation_style(resolved_kind)
    if mark:
        ax.scatter(
            [x],
            [y],
            color=visual.color,
            marker=visual.marker,
            s=54,
            edgecolor=PALETTE.panel,
            linewidth=0.9,
            zorder=6,
        )
    annotation = ax.annotate(
        f"{resolved_kind.value}  {detail}",
        xy=(x, y),
        xytext=xytext,
        textcoords="offset points",
        ha=ha,
        va=va,
        family=MONO_FONT,
        fontsize=8.5,
        fontweight="bold",
        color=visual.color,
        arrowprops={
            "arrowstyle": "-",
            "color": visual.color,
            "linewidth": 0.8,
            "alpha": 0.72,
        },
        annotation_clip=False,
    )
    annotation.set_gid(f"annotation:{resolved_kind.name.lower()}")
    return annotation


def annotate_reference_line(
    ax: Axes,
    x: float,
    detail: str,
    *,
    kind: AnnotationKind | str = AnnotationKind.REFERENCE,
    y: float = 0.96,
    linestyle: str = "--",
) -> Tuple[Line2D, Annotation]:
    """Draw and directly label a vertical threshold or summary statistic."""
    resolved_kind = AnnotationKind(kind)
    visual = annotation_style(resolved_kind)
    line = ax.axvline(
        x,
        color=visual.color,
        linestyle=linestyle,
        linewidth=1.2,
        alpha=0.9,
    )
    line.set_gid(f"reference-line:{resolved_kind.name.lower()}")
    label = ax.annotate(
        f"{resolved_kind.value}\n{detail}",
        xy=(x, y),
        xycoords=ax.get_xaxis_transform(),
        xytext=(4, -2),
        textcoords="offset points",
        ha="left",
        va="top",
        family=MONO_FONT,
        fontsize=7.8,
        fontweight="bold",
        color=visual.color,
        annotation_clip=False,
    )
    label.set_gid(f"annotation:{resolved_kind.name.lower()}")
    return line, label


def _last_finite_point(line: Line2D) -> Tuple[object, float]:
    points = [
        (x, float(y))
        for x, y in zip(line.get_xdata(orig=False), line.get_ydata(orig=False))
        if y is not None and float(y) == float(y)
    ]
    if not points:
        raise ValueError("cannot label a line without a finite y value")
    return points[-1]


def label_line_ends(
    ax: Axes,
    lines: Iterable[Line2D],
    *,
    labels: Sequence[str] | None = None,
    min_gap_points: float = 12,
    x_offset_points: float = 7,
    y_offsets_points: Sequence[float] | None = None,
    max_labels: int = 6,
) -> Tuple[Annotation, ...]:
    """Direct-label line endpoints while separating nearby label baselines."""
    line_list = list(lines)
    if not line_list:
        return ()
    if len(line_list) > max_labels:
        raise ValueError(
            f"direct labels support at most {max_labels} lines; use a legend or highlight fewer"
        )
    resolved_labels = list(labels) if labels is not None else [line.get_label() for line in line_list]
    if len(resolved_labels) != len(line_list):
        raise ValueError("labels must match the number of lines")
    resolved_y_offsets = (
        list(y_offsets_points)
        if y_offsets_points is not None
        else [0.0] * len(line_list)
    )
    if len(resolved_y_offsets) != len(line_list):
        raise ValueError("y offsets must match the number of lines")
    if any(not label or label.startswith("_") for label in resolved_labels):
        raise ValueError("every directly labeled line needs a visible label")

    ax.figure.canvas.draw()
    renderer = ax.figure.canvas.get_renderer()
    axes_box = ax.get_window_extent(renderer)
    gap_pixels = min_gap_points * ax.figure.dpi / 72
    endpoints = []
    for line, label, y_offset_points in zip(
        line_list, resolved_labels, resolved_y_offsets
    ):
        x, y = _last_finite_point(line)
        display_x, display_y = ax.transData.transform((x, y))
        endpoints.append(
            {
                "line": line,
                "label": label,
                "x": x,
                "y": y,
                "display_x": display_x,
                "display_y": display_y,
                "label_y": display_y + y_offset_points * ax.figure.dpi / 72,
            }
        )

    ordered = sorted(endpoints, key=lambda item: item["label_y"])
    for previous, current in zip(ordered, ordered[1:]):
        current["label_y"] = max(
            current["label_y"], previous["label_y"] + gap_pixels
        )
    upper_limit = axes_box.y1 - gap_pixels / 2
    if ordered[-1]["label_y"] > upper_limit:
        shift = ordered[-1]["label_y"] - upper_limit
        for item in ordered:
            item["label_y"] -= shift
    lower_limit = axes_box.y0 + gap_pixels / 2
    if ordered[0]["label_y"] < lower_limit:
        shift = lower_limit - ordered[0]["label_y"]
        for item in ordered:
            item["label_y"] += shift

    annotations = []
    for item in endpoints:
        offset_y_points = (
            item["label_y"] - item["display_y"]
        ) * 72 / ax.figure.dpi
        color = item["line"].get_color()
        annotation = ax.annotate(
            item["label"],
            xy=(item["x"], item["y"]),
            xytext=(x_offset_points, offset_y_points),
            textcoords="offset points",
            ha="left",
            va="center",
            family=MONO_FONT,
            fontsize=8.2,
            fontweight="bold",
            color=color,
            arrowprops={
                "arrowstyle": "-",
                "color": color,
                "linewidth": 0.75,
                "alpha": 0.65,
            },
            annotation_clip=False,
        )
        annotation.set_gid("direct-label")
        annotations.append(annotation)
    return tuple(annotations)


def plot_estimate_interval(
    ax: Axes,
    *,
    estimate: float,
    low: float,
    high: float,
    y: float,
    color: str = PALETTE.frontier,
    label: str | None = None,
    marker: str = "o",
    markersize: float = 7,
    linewidth: float = 2,
    capsize: float = 5,
) -> Artist:
    """Plot one estimate and its complete interval with standard geometry."""
    if low > estimate or estimate > high:
        raise ValueError("estimate interval must satisfy low <= estimate <= high")
    container = ax.errorbar(
        estimate,
        y,
        xerr=[[estimate - low], [high - estimate]],
        fmt=marker,
        markersize=markersize,
        color=color,
        ecolor=color,
        elinewidth=linewidth,
        capsize=capsize,
        capthick=1.2,
        label=label,
        zorder=5,
    )
    container.lines[0].set_gid("estimate-point")
    return container


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
