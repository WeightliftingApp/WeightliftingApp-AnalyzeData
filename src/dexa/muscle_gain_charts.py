"""Shared-style chart for the longitudinal muscle-gain estimate."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from chart_style import (
    FORECAST_FRAME,
    MONO_FONT,
    PALETTE,
    PARETO_AXES,
    AnnotationKind,
    add_footer,
    add_header,
    annotate_point,
    plot_estimate_interval,
    save_chart,
    stacked_canvas,
    style_axes,
)

from .muscle_gain import MuscleGainEstimate


def plot_muscle_gain_estimate(
    estimate: MuscleGainEstimate, output_path: Path
) -> Path:
    """Plot bodyweight-adjusted lean history and the muscle-gain interval."""
    totals = estimate.totals
    dates = totals["date"]
    years = (dates - dates.iloc[0]).dt.days.to_numpy(dtype=float) / 365.2425
    fitted = (
        estimate.adjusted_lean_soft_tissue_lb.mean()
        + estimate.annual_adjusted_lean_slope_lb * (years - years.mean())
    )
    headline = round(estimate.muscle_gain_median_lb * 2.0) / 2.0
    low = round(estimate.muscle_gain_low_95_lb * 2.0) / 2.0
    high = round(estimate.muscle_gain_high_95_lb * 2.0) / 2.0

    with stacked_canvas(
        FORECAST_FRAME,
        (1.55, 0.72),
        0.22,
        sharex=False,
    ) as (figure, (upper, lower)):
        add_header(
            figure,
            FORECAST_FRAME,
            "DEXA ESTIMATE: MODEST, UNCERTAIN GAIN",
            (
                f"Central estimate {headline:+.1f} lb of skeletal muscle; "
                f"95% interval {low:+.1f} to {high:+.1f} lb"
            ),
            (
                f"{len(totals)} SCANS  /  "
                f"{dates.min():%Y.%m.%d} TO {dates.max():%Y.%m.%d}",
                "LEAN VALUES ADJUSTED TO "
                f"{estimate.reference_weight_lb:.1f} LB BODYWEIGHT",
            ),
        )
        upper.plot(
            dates,
            estimate.adjusted_lean_soft_tissue_lb,
            color=PALETTE.neutral_point,
            linewidth=1.2,
            alpha=0.55,
        )
        upper.scatter(
            dates,
            estimate.adjusted_lean_soft_tissue_lb,
            s=72,
            color=PALETTE.neutral_point,
            edgecolor=PALETTE.panel,
            linewidth=1.0,
            zorder=3,
            label="BODYWEIGHT-ADJUSTED DEXA LEAN",
        )
        upper.plot(
            dates,
            fitted,
            color=PALETTE.frontier,
            linewidth=2.5,
            label="ALL-SCAN TIME TREND",
        )
        annotate_point(
            upper,
            dates.iloc[-1],
            estimate.adjusted_lean_soft_tissue_lb[-1],
            f"{dates.iloc[-1]:%Y.%m.%d}",
            kind=AnnotationKind.LATEST,
            xytext=(-8, 15),
            ha="right",
        )
        upper.set_ylabel(
            "LEAN SOFT TISSUE AT COMMON WEIGHT (LB)",
            fontsize=10.5,
            family=MONO_FONT,
        )
        upper.legend(
            frameon=False,
            loc="upper left",
            prop={"family": MONO_FONT, "size": 8.5},
            labelcolor=PALETTE.muted,
        )

        raw_change = estimate.earliest_to_latest.lean_soft_tissue_change_lb
        raw_scan_error = np.sqrt(2.0) * estimate.assumed_scan_error_sd_lb
        raw_change_95 = 1.96 * raw_scan_error
        plot_estimate_interval(
            lower,
            estimate=raw_change,
            low=raw_change - raw_change_95,
            high=raw_change + raw_change_95,
            y=1,
            marker="D",
            markersize=7,
            color=PALETTE.reference,
            capsize=4,
            linewidth=2,
        )
        plot_estimate_interval(
            lower,
            estimate=estimate.muscle_gain_median_lb,
            low=estimate.muscle_gain_low_95_lb,
            high=estimate.muscle_gain_high_95_lb,
            y=0,
            markersize=9,
            color=PALETTE.frontier,
            capsize=5,
            linewidth=2.5,
        )
        lower.axvline(0, color=PALETTE.ink, linewidth=1.0, alpha=0.5)
        lower.set_yticks([0, 1], ["MUSCLE", "DEXA LEAN"])
        lower.set_xlabel(
            "CHANGE FROM EARLIEST TO LATEST SCAN (LB)",
            fontsize=10.5,
            family=MONO_FONT,
        )
        interval_low = min(
            0.0,
            raw_change - raw_change_95,
            estimate.muscle_gain_low_95_lb,
        )
        interval_high = max(
            0.0,
            raw_change + raw_change_95,
            estimate.muscle_gain_high_95_lb,
        )
        padding = max(0.75, 0.06 * (interval_high - interval_low))
        lower.set_xlim(interval_low - padding, interval_high + padding)
        lower.set_ylim(-0.55, 1.55)
        annotate_point(
            lower,
            raw_change,
            1,
            f"{raw_change:+.1f} LB LEAN",
            kind=AnnotationKind.REFERENCE,
            xytext=(7, 9),
            mark=False,
        )
        annotate_point(
            lower,
            estimate.muscle_gain_median_lb,
            0,
            f"{headline:+.1f} LB  /  95% {low:+.1f} TO {high:+.1f}",
            kind=AnnotationKind.ESTIMATE,
            xytext=(7, 9),
            mark=False,
        )
        for axis in (upper, lower):
            style_axes(axis, PARETO_AXES)

        add_footer(
            figure,
            FORECAST_FRAME,
            f"OLS: LEAN ~ BODYWEIGHT + TIME  /  {estimate.assumptions.simulations:,} SEEDED DRAWS",
            "DEXA LEAN IS NOT SKELETAL MUSCLE  /  STRENGTH IS CORROBORATION ONLY",
            right_weight="normal",
        )
        return save_chart(figure, output_path, dpi=FORECAST_FRAME.dpi)
