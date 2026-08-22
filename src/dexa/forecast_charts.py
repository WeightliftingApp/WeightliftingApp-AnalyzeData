"""Chart for the bulk-ceiling forecast.

Framed by `chart_style` like the DEXA topography and the bench Pareto card.
The forecast maths, the marks, and every claim on the canvas stay here.

Palette choices worth stating, because this chart carries more model states
than the other two cards:

- `PALETTE.frontier` is the modeled series: median, both prediction bands, and
  the safety ceiling derived from them.
- `PALETTE.negative` is a limit the reader is asked not to cross: the body-fat
  target and the safety confidence level.
- `PALETTE.reference` is the constant fat-free-mass ceiling, an alternative
  reference plotted next to the model rather than produced by it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from chart_style import (
    FORECAST_FRAME,
    MONO_FONT,
    PALETTE,
    PARETO_AXES,
    add_footer,
    add_header,
    save_chart,
    stacked_canvas,
    style_axes,
)

from .forecast import (
    PREDICTION_COVERAGE,
    PREDICTION_COVERAGE_INNER,
    SAFETY_CONFIDENCE,
    BulkCeilingForecast,
)

PANEL_HEIGHT_RATIOS = (1.45, 1.0)
PANEL_SPACING = 0.16


def model_footer(forecast: BulkCeilingForecast) -> str:
    """Describe the simulation the reader is looking at.

    The two footer strings share one row, so this one stays to the seed, the
    draw count, the assumed scan error, and the sparse-evidence warning. The
    "these are estimates" caveat belongs with the reading key on the right.

    "DRAWS" is the word `--simulations` already uses for these in its own help
    text, and it buys enough of the row that a ten-digit seed beside a
    seven-figure draw count still clears the reading key.
    """
    assumptions = forecast.assumptions
    parts = [
        f"SEED {assumptions.seed}",
        f"{assumptions.simulations:,} DRAWS",
        f"{assumptions.measurement_error_pp:g} PP ASSUMED SCAN ERROR",
    ]
    if forecast.is_sparse:
        # The header metadata already names these as resampling units.
        parts.append(f"SPARSE: {forecast.resampling_unit_count} UNITS")
    return "  /  ".join(parts)


def reading_footer() -> str:
    """Describe what the reader is looking at and how the bands nest."""
    return (
        "MODELED, NOT MEASURED  /  "
        f"BANDS = {PREDICTION_COVERAGE_INNER:.0%} INSIDE {PREDICTION_COVERAGE:.0%}"
    )


def plot_bulk_ceiling(forecast: BulkCeilingForecast, output_path: Path) -> None:
    """Write the two-panel forecast chart.

    Top panel: modeled body fat against bodyweight, with the prediction bands.
    Bottom panel: modeled probability of still reading under target.

    Two panels rather than two y-axes on one plot. They share the bodyweight
    axis, which is the only quantity both panels measure.
    """
    target = forecast.assumptions.target_body_fat_pct
    grid = forecast.weight_grid_lb
    coverage_label = f"{PREDICTION_COVERAGE:.0%}"
    inner_label = f"{PREDICTION_COVERAGE_INNER:.0%}"
    safety_label = f"{SAFETY_CONFIDENCE:.0%}"

    with stacked_canvas(FORECAST_FRAME, PANEL_HEIGHT_RATIOS, PANEL_SPACING) as (
        figure,
        (upper, lower),
    ):
        add_header(
            figure,
            FORECAST_FRAME,
            f"HOW HEAVY BEFORE {target:g}% BODY FAT",
            "Modeled body fat and the odds of staying under target as bodyweight rises",
            (
                f"{forecast.interval_count} POSITIVE-WEIGHT DEXA INTERVALS",
                f"{forecast.resampling_unit_count} RESAMPLING UNITS"
                f"  /  ANCHOR {forecast.current_date}",
            ),
        )

        _plot_body_fat(upper, forecast, grid, target, coverage_label, inner_label)
        _plot_probability(lower, forecast, grid, target, safety_label)
        for axis in (upper, lower):
            style_axes(axis, PARETO_AXES)

        lower.set_xlabel(
            "BODYWEIGHT (LB)", fontsize=11, family=MONO_FONT, labelpad=10,
        )
        span = grid[-1] - grid[0]
        lower.set_xlim(grid[0] - 0.02 * span, grid[-1] + 0.01 * span)

        add_footer(
            figure,
            FORECAST_FRAME,
            model_footer(forecast),
            reading_footer(),
            right_weight="normal",
        )
        save_chart(figure, output_path, dpi=FORECAST_FRAME.dpi)


def _plot_body_fat(axis, forecast, grid, target, coverage_label, inner_label) -> None:
    axis.fill_between(
        grid,
        forecast.body_fat_low_95_pct,
        forecast.body_fat_high_95_pct,
        color=PALETTE.frontier,
        alpha=0.13,
        linewidth=0,
        label=f"{coverage_label} PREDICTION BAND",
    )
    axis.fill_between(
        grid,
        forecast.body_fat_low_80_pct,
        forecast.body_fat_high_80_pct,
        color=PALETTE.frontier,
        alpha=0.20,
        linewidth=0,
        label=f"{inner_label} PREDICTION BAND",
    )
    axis.plot(
        grid,
        forecast.body_fat_median_pct,
        color=PALETTE.frontier,
        linewidth=2.0,
        label="MEDIAN MODELED READING",
    )
    axis.axhline(
        target,
        color=PALETTE.negative,
        linewidth=2.0,
        linestyle=(0, (5, 3)),
        label=f"{target:g}% TARGET",
    )
    axis.scatter(
        [forecast.current_weight_lb],
        [forecast.current_body_fat_pct],
        s=90,
        color=PALETTE.ink,
        zorder=5,
        label=f"{forecast.current_date} SCAN",
    )
    axis.annotate(
        f"{forecast.current_weight_lb:.1f} LB\n{forecast.current_body_fat_pct:.1f}%",
        (forecast.current_weight_lb, forecast.current_body_fat_pct),
        xytext=(8, -26),
        textcoords="offset points",
        fontsize=9.5,
        family=MONO_FONT,
        color=PALETTE.muted,
        ha="left",
    )
    bottom, top = axis.get_ylim()
    axis.set_ylim(bottom - 0.06 * (top - bottom), top)
    bottom, top = axis.get_ylim()
    # The two reference weights sit only a few pounds apart, so the labels take
    # opposite sides of their own lines and different heights.
    references = []
    if not forecast.constant_ffm_above_cap:
        references.append(
            (
                forecast.constant_ffm_ceiling_lb,
                PALETTE.reference,
                "CONSTANT FFM",
                "right",
                0.16,
            )
        )
    if forecast.safety_ceiling.identified:
        references.append(
            (
                forecast.safety_ceiling.raw_lb,
                PALETTE.frontier,
                f"{SAFETY_CONFIDENCE:.0%} SAFETY CEILING",
                "left",
                0.03,
            )
        )
    for weight, color, label, side, height in references:
        axis.axvline(weight, color=color, linewidth=1.6, linestyle=(0, (2, 2.5)))
        offset = -6 if side == "right" else 6
        axis.annotate(
            f"{label}\n{weight:.1f} LB",
            (weight, bottom + height * (top - bottom)),
            xytext=(offset, 0),
            textcoords="offset points",
            fontsize=9,
            family=MONO_FONT,
            color=color,
            fontweight="bold",
            ha=side,
            va="bottom",
        )
    if not forecast.safety_ceiling.identified:
        axis.annotate(
            f"{SAFETY_CONFIDENCE:.0%} SAFETY CEILING "
            f"{forecast.safety_ceiling.describe_short()}",
            (grid[-1], bottom + 0.03 * (top - bottom)),
            xytext=(-6, 0),
            textcoords="offset points",
            fontsize=9,
            family=MONO_FONT,
            color=PALETTE.frontier,
            fontweight="bold",
            ha="right",
            va="bottom",
        )
    axis.set_ylabel(
        "MODELED BODY FAT (%)", fontsize=11, family=MONO_FONT, labelpad=8,
    )
    axis.legend(
        frameon=False,
        loc="upper left",
        labelcolor=PALETTE.muted,
        prop={"family": MONO_FONT, "size": 8.8},
        ncol=2,
    )


def _plot_probability(axis, forecast, grid, target, safety_label) -> None:
    probability = forecast.probability_under_target * 100.0
    axis.plot(
        grid,
        probability,
        color=PALETTE.frontier,
        linewidth=2.0,
    )
    axis.axhline(
        100.0 * SAFETY_CONFIDENCE,
        color=PALETTE.negative,
        linewidth=2.0,
        linestyle=(0, (5, 3)),
    )
    axis.annotate(
        f"{safety_label} CONFIDENCE",
        (grid[-1], 100.0 * SAFETY_CONFIDENCE),
        xytext=(-4, 7),
        textcoords="offset points",
        fontsize=9.5,
        family=MONO_FONT,
        color=PALETTE.negative,
        fontweight="bold",
        ha="right",
        va="bottom",
    )
    if forecast.safety_ceiling.identified:
        axis.scatter(
            [forecast.safety_ceiling.raw_lb],
            [100.0 * SAFETY_CONFIDENCE],
            s=90,
            color=PALETTE.frontier,
            zorder=5,
        )
        axis.annotate(
            forecast.safety_ceiling.describe_short(),
            (forecast.safety_ceiling.raw_lb, 100.0 * SAFETY_CONFIDENCE),
            xytext=(9, -20),
            textcoords="offset points",
            fontsize=10.5,
            family=MONO_FONT,
            color=PALETTE.frontier,
            fontweight="bold",
            ha="left",
        )
    if not forecast.constant_ffm_above_cap:
        axis.axvline(
            forecast.constant_ffm_ceiling_lb,
            color=PALETTE.reference,
            linewidth=1.6,
            linestyle=(0, (2, 2.5)),
        )
    axis.set_ylabel(
        f"PROBABILITY UNDER {target:g}% (%)",
        fontsize=11,
        family=MONO_FONT,
        labelpad=8,
    )
    axis.set_ylim(0, 104)
    axis.set_yticks(np.arange(0, 101, 25))
