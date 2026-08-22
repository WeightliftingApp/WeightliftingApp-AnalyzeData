"""Pure body-composition calculations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DexaAnalysis:
    """Calculated values used by charts and the Markdown report."""

    totals: pd.DataFrame
    previous: pd.Series
    latest: pd.Series
    delta: pd.Series
    prior_regions: pd.DataFrame
    latest_regions: pd.DataFrame
    total_loss: float
    fat_loss: float
    lean_loss: float
    fat_share: float


def fit_lean_mass_trend(totals: pd.DataFrame) -> tuple[float, float, pd.Series, float]:
    """Fit lean soft tissue against bodyweight and return vertical residuals."""
    slope, intercept = np.polyfit(
        totals["weight_lb"], totals["lean_soft_tissue_lb"], 1
    )
    predicted = slope * totals["weight_lb"] + intercept
    residuals = totals["lean_soft_tissue_lb"] - predicted
    total_variation = np.square(
        totals["lean_soft_tissue_lb"] - totals["lean_soft_tissue_lb"].mean()
    ).sum()
    unexplained_variation = np.square(residuals).sum()
    r_squared = 1 - unexplained_variation / total_variation
    return slope, intercept, residuals, r_squared


def modeled_body_fat_pct(
    bodyweight_lb: np.ndarray,
    lean_soft_tissue_lb: np.ndarray,
    bone_mineral_content_lb: float,
) -> np.ndarray:
    """Estimate body-fat percentage at chart coordinates for a fixed bone mass."""
    return (
        (bodyweight_lb - lean_soft_tissue_lb - bone_mineral_content_lb)
        / bodyweight_lb
        * 100
    )


def add_interval_efficiency(totals: pd.DataFrame) -> pd.DataFrame:
    """Add bulk or cut efficiency for the interval ending at each scan."""
    result = totals.sort_values("date").copy()
    weight_change = result["weight_lb"].diff()
    lean_change = result["lean_soft_tissue_lb"].diff()
    lean_slope = lean_change / weight_change

    result["phase"] = np.select(
        [weight_change > 0, weight_change < 0],
        ["BULK", "CUT"],
        default="BASELINE",
    )
    result["interval_efficiency"] = np.where(
        weight_change > 0,
        lean_slope,
        np.where(weight_change < 0, 1 - lean_slope, np.nan),
    )
    return result


def analyze_body_composition(
    totals: pd.DataFrame, regions: pd.DataFrame
) -> DexaAnalysis:
    """Calculate latest-scan changes without reading or writing files."""
    ordered_totals = totals.sort_values("date").reset_index(drop=True).copy()
    if len(ordered_totals) < 2:
        raise ValueError("DEXA analysis requires at least two total-body scans")

    latest = ordered_totals.iloc[-1]
    previous = ordered_totals.iloc[-2]
    numeric = [
        "weight_lb",
        "lean_soft_tissue_lb",
        "fat_mass_lb",
        "bone_mineral_content_lb",
        "body_fat_pct",
        "fat_free_mass_lb",
        "ffmi",
        "normalized_ffmi",
        "bmi",
        "height_in",
    ]
    delta = latest[numeric] - previous[numeric]
    total_loss = previous["weight_lb"] - latest["weight_lb"]
    fat_loss = previous["fat_mass_lb"] - latest["fat_mass_lb"]
    lean_loss = (
        previous["lean_soft_tissue_lb"] - latest["lean_soft_tissue_lb"]
    )
    fat_share = fat_loss / total_loss

    prior_regions = regions[regions["date"] == previous["date"]].set_index("region")
    latest_regions = regions[regions["date"] == latest["date"]].set_index("region")
    missing_regions = latest_regions.index.difference(prior_regions.index)
    if not missing_regions.empty:
        missing_list = ", ".join(missing_regions)
        raise ValueError(f"previous scan is missing regions: {missing_list}")

    return DexaAnalysis(
        totals=ordered_totals,
        previous=previous,
        latest=latest,
        delta=delta,
        prior_regions=prior_regions,
        latest_regions=latest_regions,
        total_loss=total_loss,
        fat_loss=fat_loss,
        lean_loss=lean_loss,
        fat_share=fat_share,
    )
