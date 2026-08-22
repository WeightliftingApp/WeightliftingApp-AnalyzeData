"""Read source data and write the local muscle-gain report artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from training_dataset import load_training_dataset

from .ingestion import load_regions, load_totals
from .muscle_gain import (
    MuscleGainAssumptions,
    MuscleGainEstimate,
    TrainingEvidence,
    estimate_muscle_gain,
    summarize_training_evidence,
)
from .muscle_gain_charts import plot_muscle_gain_estimate
from .muscle_gain_report import render_muscle_gain_report


@dataclass(frozen=True)
class MuscleGainOutputs:
    """Paths written by one muscle-gain analysis run."""

    report: Path
    chart: Path


def run_muscle_gain_report(
    totals_path: Path,
    regions_path: Path,
    output_dir: Path,
    assumptions: MuscleGainAssumptions | None = None,
    training_log_path: Path | None = None,
) -> tuple[MuscleGainEstimate, TrainingEvidence | None, MuscleGainOutputs]:
    """Run the estimator and write its report and chart."""
    totals = load_totals(totals_path)
    regions = load_regions(regions_path)
    estimate = estimate_muscle_gain(totals, regions, assumptions)
    training = None
    if training_log_path is not None:
        dataset = load_training_dataset(training_log_path)
        training = summarize_training_evidence(
            dataset.workouts,
            dataset.sets,
            estimate.earliest_to_latest.start_date,
            estimate.earliest_to_latest.end_date,
        )

    outputs = MuscleGainOutputs(
        report=output_dir / "report.md",
        chart=output_dir / "muscle-gain-estimate.png",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_muscle_gain_estimate(estimate, outputs.chart)
    outputs.report.write_text(
        render_muscle_gain_report(estimate, training, outputs.chart.name),
        encoding="utf-8",
    )
    return estimate, training, outputs
