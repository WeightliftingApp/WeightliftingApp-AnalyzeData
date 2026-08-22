"""Objective structural checks for editorial Matplotlib charts.

The linter catches mechanical failures. It does not judge whether a finding is
important, whether prose is insightful, or whether a domain calculation is
correct.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from matplotlib import colors as mcolors
from matplotlib import dates as mdates
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from chart_style import ANNOTATION_STYLES, AnnotationKind


DEFAULT_MATPLOTLIB_COLORS = frozenset(
    mcolors.to_hex(color)
    for color in (
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
    )
)


@dataclass(frozen=True)
class ChartLintIssue:
    code: str
    message: str
    axes_index: int | None = None


def _axes_has_data(ax: Axes) -> bool:
    return bool(ax.lines or ax.collections or ax.patches or ax.images)


def _is_date_axis(ax: Axes) -> bool:
    formatter = ax.xaxis.get_major_formatter()
    return isinstance(
        formatter,
        (mdates.DateFormatter, mdates.ConciseDateFormatter, mdates.AutoDateFormatter),
    )


def _normalized_color(color) -> str | None:
    try:
        return mcolors.to_hex(color)
    except (TypeError, ValueError):
        return None


def _overlaps(left, right) -> bool:
    return not (
        left.x1 <= right.x0
        or right.x1 <= left.x0
        or left.y1 <= right.y0
        or right.y1 <= left.y0
    )


def lint_figure(
    fig: Figure,
    *,
    require_axis_labels: bool = True,
    max_date_ticks: int = 12,
    expected_units: Mapping[tuple[int, str], str] | None = None,
) -> tuple[ChartLintIssue, ...]:
    """Return deterministic structural issues for a rendered figure.

    ``expected_units`` maps ``(axes_index, "x" | "y")`` to text that must be
    present in that axis label. Domain code supplies the expectation because a
    generic style module cannot infer whether an unlabeled value is pounds,
    percent, minutes, a score, or a count.
    """
    if max_date_ticks < 2:
        raise ValueError("max_date_ticks must be at least 2")
    expected_units = expected_units or {}
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    issues: list[ChartLintIssue] = []

    for index, ax in enumerate(fig.axes):
        if not ax.get_visible() or not _axes_has_data(ax):
            continue
        if require_axis_labels:
            if not ax.get_xlabel().strip():
                issues.append(
                    ChartLintIssue("missing-x-label", "data axes has no x label", index)
                )
            if not ax.get_ylabel().strip():
                issues.append(
                    ChartLintIssue("missing-y-label", "data axes has no y label", index)
                )
        for axis_name, getter in (("x", ax.get_xlabel), ("y", ax.get_ylabel)):
            expected = expected_units.get((index, axis_name))
            if expected and expected.casefold() not in getter().casefold():
                issues.append(
                    ChartLintIssue(
                        f"missing-{axis_name}-unit",
                        f"{axis_name} label does not contain expected unit {expected!r}",
                        index,
                    )
                )
        if _is_date_axis(ax) and len(ax.get_xticks()) > max_date_ticks:
            issues.append(
                ChartLintIssue(
                    "dense-date-ticks",
                    f"date axis has {len(ax.get_xticks())} ticks; limit is {max_date_ticks}",
                    index,
                )
            )
        legend = ax.get_legend()
        if legend is not None and getattr(legend, "_loc", None) == 0:
            issues.append(
                ChartLintIssue(
                    "automatic-legend-location",
                    "legend uses automatic placement; choose a stable location",
                    index,
                )
            )
        for line in ax.lines:
            color = _normalized_color(line.get_color())
            if color in DEFAULT_MATPLOTLIB_COLORS:
                issues.append(
                    ChartLintIssue(
                        "default-series-color",
                        f"line {line.get_label()!r} uses Matplotlib default {color}",
                        index,
                    )
                )
        for text in ax.texts:
            gid = text.get_gid() or ""
            if not gid.startswith("annotation:"):
                continue
            kind_name = gid.removeprefix("annotation:").upper()
            try:
                kind = AnnotationKind[kind_name]
            except KeyError:
                issues.append(
                    ChartLintIssue(
                        "unknown-annotation-kind",
                        f"annotation gid {gid!r} is not in the shared vocabulary",
                        index,
                    )
                )
                continue
            expected_color = _normalized_color(ANNOTATION_STYLES[kind].color)
            actual_color = _normalized_color(text.get_color())
            if actual_color != expected_color:
                issues.append(
                    ChartLintIssue(
                        "annotation-color-mismatch",
                        f"{kind.value} uses {actual_color}; expected {expected_color}",
                        index,
                    )
                )

    figure_box = fig.bbox
    visible_figure_text = [text for text in fig.texts if text.get_visible() and text.get_text()]
    text_boxes = [(text, text.get_window_extent(renderer)) for text in visible_figure_text]
    for text, box in text_boxes:
        if (
            box.x0 < figure_box.x0 - 1
            or box.y0 < figure_box.y0 - 1
            or box.x1 > figure_box.x1 + 1
            or box.y1 > figure_box.y1 + 1
        ):
            issues.append(
                ChartLintIssue(
                    "clipped-figure-text",
                    f"figure text {text.get_text()!r} extends beyond the canvas",
                )
            )
    for offset, (left_text, left_box) in enumerate(text_boxes):
        for right_text, right_box in text_boxes[offset + 1 :]:
            if _overlaps(left_box, right_box):
                issues.append(
                    ChartLintIssue(
                        "overlapping-figure-text",
                        f"figure texts {left_text.get_text()!r} and {right_text.get_text()!r} overlap",
                    )
                )

    return tuple(issues)


def assert_chart_lint_clean(
    fig: Figure,
    *,
    allowed_codes: Sequence[str] = (),
    **kwargs,
) -> None:
    """Raise an actionable assertion when objective chart checks fail."""
    allowed = set(allowed_codes)
    issues = [issue for issue in lint_figure(fig, **kwargs) if issue.code not in allowed]
    if not issues:
        return
    details = "\n".join(
        f"- {issue.code}"
        f"{f' [axes {issue.axes_index}]' if issue.axes_index is not None else ''}: "
        f"{issue.message}"
        for issue in issues
    )
    raise AssertionError(f"chart lint failed:\n{details}")
