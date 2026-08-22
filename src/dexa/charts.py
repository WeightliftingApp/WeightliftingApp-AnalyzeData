"""Chart generation for DEXA reports."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyArrowPatch

from .calculations import (
    add_interval_efficiency,
    fit_lean_mass_trend,
    modeled_body_fat_pct,
)


def scan_sequence_footer(scan_count: int) -> str:
    """Describe the numbered scan sequence in the lean-mass chart footer."""
    return (
        f"1 TO {scan_count} = TIME  /  BLUE = CUT  /  "
        "RED = BULK  /  BAR = VS TREND"
    )


def plot_composition_history(totals: pd.DataFrame, output_path: Path) -> None:
    """Plot total mass, fat-free mass, fat mass, and body-fat history."""
    with plt.style.context("dark_background"):
        fig, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=True)
        fig.patch.set_facecolor("#0b1020")
        for ax in axes:
            ax.set_facecolor("#0b1020")
            ax.grid(alpha=0.18, linewidth=0.8)
        axes[0].plot(
            totals.date,
            totals.weight_lb,
            "o-",
            color="#70d6ff",
            linewidth=2.7,
            markersize=7,
            label="Total mass",
        )
        axes[0].plot(
            totals.date,
            totals.fat_free_mass_lb,
            "o-",
            color="#ff9f1c",
            linewidth=2.7,
            markersize=7,
            label="Fat-free mass",
        )
        axes[0].plot(
            totals.date,
            totals.fat_mass_lb,
            "o-",
            color="#ff4d6d",
            linewidth=2.7,
            markersize=7,
            label="Fat mass",
        )
        axes[0].set_ylabel("Mass (lb)", fontsize=13, weight="bold")
        axes[0].legend(frameon=False, ncol=3)
        axes[0].set_title(
            "DEXA body-composition history", fontsize=19, weight="bold", loc="left"
        )
        axes[1].plot(
            totals.date,
            totals.body_fat_pct,
            "o-",
            color="#c77dff",
            linewidth=3,
            markersize=8,
        )
        axes[1].axhspan(
            10,
            16,
            color="#2ec4b6",
            alpha=0.10,
            label="Athletic/lean reference band",
        )
        axes[1].set_ylabel("Body fat (%)", fontsize=13, weight="bold")
        axes[1].set_xlabel("Scan date", fontsize=13, weight="bold")
        axes[1].legend(frameon=False)
        fig.tight_layout()
        fig.savefig(
            output_path,
            dpi=180,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
        )
        plt.close(fig)


def plot_lean_mass_vs_bodyweight(totals: pd.DataFrame, output_path: Path) -> None:
    """Plot DEXA lean mass against bodyweight with time, trend, and fat contours."""
    points = add_interval_efficiency(totals)
    slope, intercept, points["trend_residual_lb"], r_squared = fit_lean_mass_trend(
        points
    )
    recent_points = points.tail(2)
    recent_slope, recent_intercept = np.polyfit(
        recent_points["weight_lb"], recent_points["lean_soft_tissue_lb"], 1
    )

    paper_bg = "#f5f2ea"
    panel_bg = "#faf8f2"
    ink = "#18181b"
    muted_ink = "#71717a"
    grid_color = "#d6d3ca"
    trend_color = "#334155"
    positive_color = "#15803d"
    negative_color = "#c2413b"
    point_color = "#475569"
    latest_point_color = "#f97316"
    cut_path_color = "#38bdf8"
    bulk_path_color = "#ef4444"
    mono = "DejaVu Sans Mono"

    x_min = np.floor(points["weight_lb"].min() - 3)
    x_max = np.ceil(points["weight_lb"].max() + 3)
    y_min = np.floor(points["lean_soft_tissue_lb"].min() - 3)
    y_max = np.ceil(points["lean_soft_tissue_lb"].max() + 4)
    reference_bone_mass = points.iloc[-1]["bone_mineral_content_lb"]

    grid_x, grid_y = np.meshgrid(
        np.linspace(x_min, x_max, 320),
        np.linspace(y_min, y_max, 240),
    )
    body_fat_grid = modeled_body_fat_pct(grid_x, grid_y, reference_bone_mass)
    contour_levels = np.arange(5, 21, 1)
    body_fat_cmap = LinearSegmentedColormap.from_list(
        "body_fat_topography",
        ["#f7f6f1", "#e8e5de", "#d2cec4"],
    )
    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "axes.edgecolor": ink,
            "axes.labelcolor": ink,
            "xtick.color": muted_ink,
            "ytick.color": muted_ink,
        }
    ):
        fig, ax = plt.subplots(figsize=(10, 8), facecolor=paper_bg)
        ax.set_facecolor(panel_bg)

        fig.text(
            0.075,
            0.90,
            "LEAN MASS VS BODYWEIGHT",
            fontsize=27,
            fontweight="bold",
            color=ink,
            ha="left",
        )
        fig.text(
            0.075,
            0.86,
            "DEXA trajectory and distance from the full-history trend",
            fontsize=13.5,
            color=muted_ink,
            ha="left",
        )
        fig.text(
            0.95,
            0.898,
            f"SCAN WINDOW  {points['date'].min():%Y.%m} TO {points['date'].max():%Y.%m}",
            fontsize=9.8,
            family=mono,
            color=muted_ink,
            ha="right",
        )
        fig.text(
            0.95,
            0.858,
            f"{len(points)} DEXA SCANS  /  TREND R2 {r_squared:.2f}",
            fontsize=9.8,
            family=mono,
            color=muted_ink,
            ha="right",
        )

        ax.contourf(
            grid_x,
            grid_y,
            body_fat_grid,
            levels=contour_levels,
            cmap=body_fat_cmap,
            alpha=0.68,
            extend="both",
            zorder=0,
        )
        contours = ax.contour(
            grid_x,
            grid_y,
            body_fat_grid,
            levels=contour_levels,
            colors="#a6a198",
            linewidths=0.72,
            alpha=0.56,
            zorder=0.5,
        )
        ax.clabel(
            contours,
            levels=[5, 10, 15, 20],
            fmt=lambda level: f"{level:.0f}%",
            inline=True,
            inline_spacing=3,
            fontsize=8.8,
            colors=muted_ink,
        )

        for (_, start), (_, end) in zip(
            points.iloc[:-1].iterrows(), points.iloc[1:].iterrows()
        ):
            path_color = (
                cut_path_color
                if end["weight_lb"] < start["weight_lb"]
                else bulk_path_color
            )
            ax.add_patch(
                FancyArrowPatch(
                    (start["weight_lb"], start["lean_soft_tissue_lb"]),
                    (end["weight_lb"], end["lean_soft_tissue_lb"]),
                    arrowstyle="-|>",
                    mutation_scale=12,
                    color=path_color,
                    linewidth=1.8,
                    alpha=0.50,
                    shrinkA=12,
                    shrinkB=14,
                    zorder=1.5,
                )
            )

        trend_x = np.array([x_min, x_max])
        ax.plot(
            trend_x,
            slope * trend_x + intercept,
            color=trend_color,
            linewidth=2.6,
            linestyle=(0, (5, 4)),
            alpha=0.92,
            zorder=2,
        )
        ax.plot(
            trend_x,
            recent_slope * trend_x + recent_intercept,
            color=trend_color,
            linewidth=2.1,
            linestyle=(0, (1.5, 3)),
            alpha=0.42,
            zorder=1.9,
        )
        point_colors = np.where(
            points["trend_residual_lb"] >= 0, positive_color, negative_color
        )
        ax.vlines(
            points["weight_lb"],
            points["lean_soft_tissue_lb"] - points["trend_residual_lb"],
            points["lean_soft_tissue_lb"],
            color=point_colors,
            linewidth=2.3,
            alpha=0.78,
            zorder=2.5,
        )
        scan_colors = np.full(len(points), point_color, dtype=object)
        scan_colors[-1] = latest_point_color
        ax.scatter(
            points["weight_lb"],
            points["lean_soft_tissue_lb"],
            s=172,
            color=scan_colors,
            edgecolor="none",
            linewidth=0,
            zorder=4,
        )

        latest = points.iloc[-1]
        cut_efficiencies = points.loc[
            points["phase"] == "CUT", "interval_efficiency"
        ].rank(method="min", ascending=False)
        latest_cut_rank = cut_efficiencies.get(latest.name)
        cut_count = (points["phase"] == "CUT").sum()

        for sequence, (_, point) in enumerate(points.iterrows(), start=1):
            is_latest = point["date"] == latest["date"]
            is_positive_outlier = point["trend_residual_lb"] > 0.75
            ax.text(
                point["weight_lb"],
                point["lean_soft_tissue_lb"] - 0.07,
                str(sequence),
                ha="center",
                va="center",
                fontsize=10.4,
                family=mono,
                color="#ffffff",
                fontweight="bold",
                zorder=4.5,
            )
            label_backing = {
                "boxstyle": "square,pad=0.12",
                "facecolor": paper_bg,
                "edgecolor": "none",
                "alpha": 0.64,
            }
            if is_latest:
                ax.annotate(
                    f"LATEST  {point['date']:%Y.%m}  /  "
                    f"{point['lean_soft_tissue_lb']:.1f} LB LEAN",
                    (point["weight_lb"], point["lean_soft_tissue_lb"]),
                    xytext=(-10, 28),
                    textcoords="offset points",
                    ha="right",
                    va="bottom",
                    fontsize=11.2,
                    family=mono,
                    color=latest_point_color,
                    fontweight="bold",
                    bbox=label_backing,
                    zorder=5,
                )
                ax.annotate(
                    f"{point['trend_residual_lb']:+.1f} VS TREND",
                    (point["weight_lb"], point["lean_soft_tissue_lb"]),
                    xytext=(-10, 10),
                    textcoords="offset points",
                    ha="right",
                    va="bottom",
                    fontsize=11.2,
                    family=mono,
                    color=positive_color,
                    fontweight="bold",
                    bbox=label_backing,
                    zorder=5,
                )
                if point["phase"] == "CUT":
                    efficiency_label = (
                        f"CUT EFF {point['interval_efficiency']:.0%}"
                        + (
                            f"  /  BEST OF {cut_count} CUTS"
                            if latest_cut_rank == 1
                            else ""
                        )
                    )
                else:
                    efficiency_label = (
                        f"{point['phase']} EFF {point['interval_efficiency']:.0%}"
                        if point["phase"] != "BASELINE"
                        else "BASELINE"
                    )
                ax.annotate(
                    efficiency_label,
                    (point["weight_lb"], point["lean_soft_tissue_lb"]),
                    xytext=(-10, -8),
                    textcoords="offset points",
                    ha="right",
                    va="top",
                    fontsize=8.8,
                    family=mono,
                    color=cut_path_color,
                    fontweight="bold",
                    bbox=label_backing,
                    zorder=5,
                )
                continue

            if point["phase"] == "BASELINE":
                efficiency_label = "BASELINE"
            else:
                efficiency_label = (
                    f"{point['phase']} EFF {point['interval_efficiency']:.0%}"
                )
            label = (
                f"{point['date']:%Y.%m}  {point['trend_residual_lb']:+.1f}\n"
                f"{efficiency_label}"
            )
            xytext = (0, 9) if is_positive_outlier else (0, -10)
            va = "bottom" if is_positive_outlier else "top"
            ax.annotate(
                label,
                (point["weight_lb"], point["lean_soft_tissue_lb"]),
                xytext=xytext,
                textcoords="offset points",
                ha="center",
                va=va,
                fontsize=10.0,
                family=mono,
                color=muted_ink,
                fontweight="normal",
                linespacing=1.35,
                bbox=label_backing,
                zorder=5,
            )

        ax.text(
            0.015,
            0.975,
            "MORE LEAN MASS FOR BODYWEIGHT  UP",
            transform=ax.transAxes,
            fontsize=9.5,
            family=mono,
            color=muted_ink,
            ha="left",
            va="top",
        )
        ax.set_xlabel("BODYWEIGHT (LB)", fontsize=11.5, family=mono, labelpad=13)
        ax.set_ylabel(
            "LEAN SOFT TISSUE (LB)", fontsize=11.5, family=mono, labelpad=7
        )
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)
        ax.set_aspect("equal", adjustable="box")
        ax.set_anchor("N")
        ax.tick_params(axis="both", labelsize=10.5, width=1.2, length=5)
        ax.grid(True, color=grid_color, linewidth=1.05, alpha=0.72)
        ax.set_axisbelow(False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_linewidth(1.2)
        ax.spines["bottom"].set_linewidth(1.2)

        fig.text(
            0.075,
            0.065,
            f"BODY FAT CONTOURS: 1 PP  /  LATEST BONE MASS: {reference_bone_mass:.1f} LB",
            fontsize=9.2,
            family=mono,
            color=muted_ink,
            ha="left",
        )
        fig.text(
            0.95,
            0.065,
            scan_sequence_footer(len(points)),
            fontsize=8.6,
            family=mono,
            color=muted_ink,
            fontweight="bold",
            ha="right",
        )
        fig.subplots_adjust(left=0.115, right=0.95, top=0.805, bottom=0.165)
        fig.savefig(output_path, dpi=200, facecolor=paper_bg)
        plt.close(fig)


def generate_charts(
    totals: pd.DataFrame, composition_path: Path, lean_mass_path: Path
) -> None:
    """Write both report charts."""
    with plt.style.context("dark_background"):
        plot_composition_history(totals, composition_path)
        plot_lean_mass_vs_bodyweight(totals, lean_mass_path)
