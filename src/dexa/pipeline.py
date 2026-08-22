"""Orchestrate a read-only DEXA analysis and write its report outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .calculations import analyze_body_composition
from .charts import generate_charts
from .ingestion import load_dexa_data
from .report import render_markdown


@dataclass(frozen=True)
class ReportOutputs:
    markdown: Path
    composition_chart: Path
    lean_mass_chart: Path


def run_report(
    totals_path: Path,
    regions_path: Path,
    output_dir: Path,
) -> ReportOutputs:
    """Read source CSVs once and write charts plus a Markdown report."""
    totals, regions = load_dexa_data(totals_path, regions_path)
    analysis = analyze_body_composition(totals, regions)
    scan_date = analysis.latest["date"].date().isoformat()

    outputs = ReportOutputs(
        markdown=output_dir / f"dexa-analysis-{scan_date}.md",
        composition_chart=output_dir / "dexa-composition-history.png",
        lean_mass_chart=output_dir / "dexa-lean-mass-vs-bodyweight.png",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    generate_charts(
        analysis.totals,
        composition_path=outputs.composition_chart,
        lean_mass_path=outputs.lean_mass_chart,
    )
    outputs.markdown.write_text(
        render_markdown(analysis, outputs.lean_mass_chart.name), encoding="utf-8"
    )
    return outputs
