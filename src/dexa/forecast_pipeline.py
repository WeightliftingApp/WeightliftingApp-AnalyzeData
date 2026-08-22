"""Read DEXA totals, run the bulk-ceiling forecast, and write its outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .forecast import (
    BulkCeilingForecast,
    ForecastAssumptions,
    forecast_bulk_ceiling,
    probability_curve_frame,
)
from .forecast_charts import plot_bulk_ceiling
from .forecast_report import render_markdown
from .ingestion import load_totals


@dataclass(frozen=True)
class ForecastOutputs:
    markdown: Path
    probability_curve: Path
    chart: Path


def run_forecast_report(
    totals_path: Path,
    output_dir: Path,
    assumptions: ForecastAssumptions | None = None,
) -> tuple[BulkCeilingForecast, ForecastOutputs]:
    """Read the totals CSV once, then write a report, a CSV, and a chart.

    The input path is only ever read. Every write lands under `output_dir`.
    """
    totals = load_totals(totals_path)
    forecast = forecast_bulk_ceiling(totals, assumptions)
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
