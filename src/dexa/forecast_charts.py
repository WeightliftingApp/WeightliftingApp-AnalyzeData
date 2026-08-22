"""Chart for the bulk-ceiling forecast.

Deliberately separate from `dexa.charts`. The existing report charts carry
their own bespoke styling, and a later integration pass can bring all three
under one style without touching the forecast maths.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .forecast import (
    PREDICTION_COVERAGE,
    PREDICTION_COVERAGE_INNER,
    SAFETY_CONFIDENCE,
    BulkCeilingForecast,
)

# Light-mode chart chrome and the first two categorical slots. Both slots clear
# every all-pairs gate against the #fcfcfb surface.
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
MUTED_INK = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
MODEL_BLUE = "#2a78d6"
REFERENCE_ORANGE = "#eb6834"
CRITICAL_RED = "#d03b3b"


def plot_bulk_ceiling(forecast: BulkCeilingForecast, output_path: Path) -> None:
    """Write the two-panel forecast chart.

    Top panel: modeled body fat against bodyweight, with the prediction band.
    Bottom panel: modeled probability of still reading under target.

    Two panels rather than two y-axes on one plot. They share the bodyweight
    axis, which is the only quantity both panels measure.
    """
    target = forecast.assumptions.target_body_fat_pct
    grid = forecast.weight_grid_lb
    coverage_label = f"{PREDICTION_COVERAGE:.0%}"
    inner_label = f"{PREDICTION_COVERAGE_INNER:.0%}"
    safety_label = f"{SAFETY_CONFIDENCE:.0%}"

    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "axes.edgecolor": AXIS,
            "axes.labelcolor": SECONDARY_INK,
            "xtick.color": MUTED_INK,
            "ytick.color": MUTED_INK,
            "text.color": INK,
        }
    ):
        figure, axes = plt.subplots(
            2,
            1,
            figsize=(11, 9),
            sharex=True,
            gridspec_kw={"height_ratios": [1.45, 1.0], "hspace": 0.16},
            facecolor=PAGE,
        )
        upper, lower = axes
        for axis in axes:
            axis.set_facecolor(SURFACE)
            axis.grid(True, color=GRID, linewidth=1.0, alpha=1.0)
            axis.set_axisbelow(True)
            axis.spines["top"].set_visible(False)
            axis.spines["right"].set_visible(False)
            axis.tick_params(labelsize=10.5, width=1.0, length=4)

        figure.text(
            0.065,
            0.955,
            f"HOW HEAVY BEFORE {target:g}% BODY FAT",
            fontsize=21,
            fontweight="bold",
            color=INK,
            ha="left",
        )
        figure.text(
            0.065,
            0.925,
            f"Modeled from {forecast.interval_count} positive-weight DEXA intervals "
            f"({forecast.resampling_unit_count} independent resampling units). "
            f"Anchored on the {forecast.current_date} scan.",
            fontsize=11.5,
            color=SECONDARY_INK,
            ha="left",
        )

        _plot_body_fat(upper, forecast, grid, target, coverage_label, inner_label)
        _plot_probability(lower, forecast, grid, target, safety_label)

        lower.set_xlabel("BODYWEIGHT (LB)", fontsize=11, labelpad=10)
        span = grid[-1] - grid[0]
        lower.set_xlim(grid[0] - 0.02 * span, grid[-1] + 0.01 * span)

        figure.text(
            0.065,
            0.038,
            "Modeled estimates, not measurements. "
            + (
                f"{forecast.resampling_unit_count} resampling units is sparse. "
                if forecast.is_sparse
                else ""
            )
            + f"Seed {forecast.assumptions.seed}, "
            f"{forecast.assumptions.simulations:,} simulations, "
            f"{forecast.assumptions.measurement_error_pp:g} pp assumed scan error.",
            fontsize=9,
            color=MUTED_INK,
            ha="left",
        )
        figure.subplots_adjust(left=0.085, right=0.965, top=0.885, bottom=0.105)
        figure.savefig(output_path, dpi=200, facecolor=PAGE)
        plt.close(figure)


def _plot_body_fat(axis, forecast, grid, target, coverage_label, inner_label) -> None:
    axis.fill_between(
        grid,
        forecast.body_fat_low_95_pct,
        forecast.body_fat_high_95_pct,
        color=MODEL_BLUE,
        alpha=0.13,
        linewidth=0,
        label=f"{coverage_label} prediction band",
    )
    axis.fill_between(
        grid,
        forecast.body_fat_low_80_pct,
        forecast.body_fat_high_80_pct,
        color=MODEL_BLUE,
        alpha=0.20,
        linewidth=0,
        label=f"{inner_label} prediction band",
    )
    axis.plot(
        grid,
        forecast.body_fat_median_pct,
        color=MODEL_BLUE,
        linewidth=2.0,
        label="Median modeled reading",
    )
    axis.axhline(
        target,
        color=CRITICAL_RED,
        linewidth=2.0,
        linestyle=(0, (5, 3)),
        label=f"{target:g}% target",
    )
    axis.scatter(
        [forecast.current_weight_lb],
        [forecast.current_body_fat_pct],
        s=90,
        color=INK,
        zorder=5,
        label=f"{forecast.current_date} scan",
    )
    axis.annotate(
        f"{forecast.current_weight_lb:.1f} lb\n{forecast.current_body_fat_pct:.1f}%",
        (forecast.current_weight_lb, forecast.current_body_fat_pct),
        xytext=(8, -26),
        textcoords="offset points",
        fontsize=10,
        color=SECONDARY_INK,
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
                REFERENCE_ORANGE,
                "Constant FFM",
                "right",
                0.16,
            )
        )
    if forecast.safety_ceiling.identified:
        references.append(
            (
                forecast.safety_ceiling.raw_lb,
                MODEL_BLUE,
                f"{SAFETY_CONFIDENCE:.0%} safety ceiling",
                "left",
                0.03,
            )
        )
    for weight, color, label, side, height in references:
        axis.axvline(weight, color=color, linewidth=1.6, linestyle=(0, (2, 2.5)))
        offset = -6 if side == "right" else 6
        axis.annotate(
            f"{label}\n{weight:.1f} lb",
            (weight, bottom + height * (top - bottom)),
            xytext=(offset, 0),
            textcoords="offset points",
            fontsize=9.5,
            color=color,
            fontweight="bold",
            ha=side,
            va="bottom",
        )
    if not forecast.safety_ceiling.identified:
        axis.annotate(
            f"{SAFETY_CONFIDENCE:.0%} safety ceiling "
            f"{forecast.safety_ceiling.describe_short()}",
            (grid[-1], bottom + 0.03 * (top - bottom)),
            xytext=(-6, 0),
            textcoords="offset points",
            fontsize=9.5,
            color=MODEL_BLUE,
            fontweight="bold",
            ha="right",
            va="bottom",
        )
    axis.set_ylabel("MODELED BODY FAT (%)", fontsize=11, labelpad=8)
    axis.legend(
        frameon=False,
        fontsize=10,
        loc="upper left",
        labelcolor=SECONDARY_INK,
        ncol=2,
    )


def _plot_probability(axis, forecast, grid, target, safety_label) -> None:
    probability = forecast.probability_under_target * 100.0
    axis.plot(
        grid,
        probability,
        color=MODEL_BLUE,
        linewidth=2.0,
    )
    axis.axhline(
        100.0 * SAFETY_CONFIDENCE,
        color=CRITICAL_RED,
        linewidth=2.0,
        linestyle=(0, (5, 3)),
    )
    axis.annotate(
        f"{safety_label} confidence",
        (grid[-1], 100.0 * SAFETY_CONFIDENCE),
        xytext=(-4, 7),
        textcoords="offset points",
        fontsize=10,
        color=CRITICAL_RED,
        fontweight="bold",
        ha="right",
        va="bottom",
    )
    if forecast.safety_ceiling.identified:
        axis.scatter(
            [forecast.safety_ceiling.raw_lb],
            [100.0 * SAFETY_CONFIDENCE],
            s=90,
            color=MODEL_BLUE,
            zorder=5,
        )
        axis.annotate(
            forecast.safety_ceiling.describe_short(),
            (forecast.safety_ceiling.raw_lb, 100.0 * SAFETY_CONFIDENCE),
            xytext=(9, -20),
            textcoords="offset points",
            fontsize=11,
            color=MODEL_BLUE,
            fontweight="bold",
            ha="left",
        )
    if not forecast.constant_ffm_above_cap:
        axis.axvline(
            forecast.constant_ffm_ceiling_lb,
            color=REFERENCE_ORANGE,
            linewidth=1.6,
            linestyle=(0, (2, 2.5)),
        )
    axis.set_ylabel(
        f"PROBABILITY UNDER {target:g}% (%)", fontsize=11, labelpad=8
    )
    axis.set_ylim(0, 104)
    axis.set_yticks(np.arange(0, 101, 25))
