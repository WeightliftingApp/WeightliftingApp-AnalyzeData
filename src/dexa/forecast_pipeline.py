"""Read DEXA totals, run the bulk-ceiling forecast, and write its outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .forecast import (
    DEFAULT_WEIGHT_LOG_WEEKS,
    WEIGHT_LOG_COLUMNS,
    BulkCeilingForecast,
    ForecastAssumptions,
    PlanningInputs,
    forecast_bulk_ceiling,
    probability_curve_frame,
    smoothed_bodyweight_lb,
)
from .forecast_charts import plot_bulk_ceiling
from .forecast_report import render_markdown
from .ingestion import load_totals


@dataclass(frozen=True)
class ForecastOutputs:
    markdown: Path
    probability_curve: Path
    chart: Path


def load_weight_log(path: Path) -> pd.DataFrame:
    """Read a weekly bodyweight log without changing it.

    Expects the documented `Week of` and `Average` columns. There is no default
    path: the caller has to name the file.
    """
    frame = pd.read_csv(path)
    missing = [column for column in WEIGHT_LOG_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
    return frame


def planning_from_weight_log(
    path: Path,
    weeks: int = DEFAULT_WEIGHT_LOG_WEEKS,
    weekly_bulk_rate_lb: float | None = None,
) -> PlanningInputs:
    """Smooth a weight log into a current bodyweight. Never infers a rate."""
    smoothed = smoothed_bodyweight_lb(load_weight_log(path), weeks)
    return PlanningInputs(
        current_bodyweight_lb=smoothed,
        weekly_bulk_rate_lb=weekly_bulk_rate_lb,
        bodyweight_source=f"{weeks}-week mean of weekly averages from {path.name}",
    )


def run_forecast_report(
    totals_path: Path,
    output_dir: Path,
    assumptions: ForecastAssumptions | None = None,
    planning: PlanningInputs | None = None,
) -> tuple[BulkCeilingForecast, ForecastOutputs]:
    """Read the totals CSV once, then write a report, a CSV, and a chart.

    The input path is only ever read. Every write lands under `output_dir`.
    """
    totals = load_totals(totals_path)
    forecast = forecast_bulk_ceiling(totals, assumptions, planning)
    target_slug = f"{forecast.assumptions.target_body_fat_pct:g}".replace(".", "-")

    outputs = ForecastOutputs(
        markdown=output_dir
        / f"bulk-ceiling-{target_slug}pct-{forecast.current_date}.md",
        probability_curve=output_dir
        / f"bulk-ceiling-{target_slug}pct-probability-curve.csv",
        chart=output_dir / f"bulk-ceiling-{target_slug}pct-forecast.png",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    probability_curve_frame(forecast).to_csv(
        outputs.probability_curve, index=False, float_format="%.6f"
    )
    plot_bulk_ceiling(forecast, outputs.chart)
    outputs.markdown.write_text(
        render_markdown(
            forecast,
            chart_filename=outputs.chart.name,
            curve_filename=outputs.probability_curve.name,
        ),
        encoding="utf-8",
    )
    return forecast, outputs
