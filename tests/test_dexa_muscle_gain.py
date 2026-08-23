"""Focused tests for the longitudinal DEXA muscle-gain estimator."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PathCollection

from dexa.muscle_gain import (
    MuscleGainAssumptions,
    estimate_muscle_gain,
    leave_one_scan_out_adjusted_gains,
    summarize_training_evidence,
)
from dexa.muscle_gain_charts import plot_muscle_gain_estimate
from dexa.muscle_gain_pipeline import run_muscle_gain_report
from dexa.muscle_gain_report import render_muscle_gain_report


def synthetic_totals() -> pd.DataFrame:
    dates = pd.to_datetime(
        [
            "2020-01-01",
            "2020-10-01",
            "2021-07-01",
            "2022-04-01",
            "2023-01-01",
            "2023-10-01",
            "2024-01-01",
        ]
    )
    years = (dates - dates[0]).days / 365.2425
    weights = np.array([180.0, 205.0, 188.0, 213.0, 195.0, 218.0, 202.0])
    lean = 92.0 + 0.40 * weights + 2.0 * years
    bone = np.full(len(dates), 8.5)
    fat = weights - lean - bone
    return pd.DataFrame(
        {
            "date": dates,
            "weight_lb": weights,
            "lean_soft_tissue_lb": lean,
            "bone_mineral_content_lb": bone,
            "fat_free_mass_lb": lean + bone,
            "fat_mass_lb": fat,
            "body_fat_pct": 100.0 * fat / weights,
            "ffmi": np.full(len(dates), 23.0),
            "normalized_ffmi": np.full(len(dates), 23.0),
            "bmi": np.full(len(dates), 28.0),
            "height_in": np.full(len(dates), 72.0),
            "notes": [""] * len(dates),
        }
    )


def synthetic_regions(totals: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for position in [0, 2, 4, 6]:
        scan = totals.iloc[position]
        years = (scan.date - totals.date.iloc[0]).days / 365.2425
        for region, base, weight_slope, time_slope in [
            ("Arms", 10.0, 0.08, 0.4),
            ("Legs", 20.0, 0.12, 0.6),
        ]:
            rows.append(
                {
                    "date": scan.date,
                    "region": region,
                    "lean_soft_tissue_lb": (
                        base + weight_slope * scan.weight_lb + time_slope * years
                    ),
                    "fat_mass_lb": 1.0,
                    "bone_mineral_content_lb": 1.0,
                    "body_fat_pct": 10.0,
                }
            )
    return pd.DataFrame(rows)


def fast_assumptions(**overrides) -> MuscleGainAssumptions:
    values = {"simulations": 4_000, "seed": 17}
    values.update(overrides)
    return MuscleGainAssumptions(**values)


class MuscleGainEstimatorTest(unittest.TestCase):
    def test_recovers_weight_and_time_coefficients(self):
        totals = synthetic_totals()
        estimate = estimate_muscle_gain(
            totals, synthetic_regions(totals), fast_assumptions()
        )

        self.assertAlmostEqual(estimate.bodyweight_slope, 0.40, places=10)
        self.assertAlmostEqual(estimate.annual_adjusted_lean_slope_lb, 2.0, places=10)
        self.assertAlmostEqual(
            estimate.full_span_adjusted_lean_gain_lb,
            2.0 * estimate.earliest_to_latest.years,
            places=10,
        )
        self.assertIsNotNone(estimate.regional)
        self.assertAlmostEqual(
            estimate.regional.adjusted_appendicular_change_lb,
            estimate.earliest_to_latest.years,
            places=10,
        )

    def test_seed_reproduces_interval_draws(self):
        totals = synthetic_totals()
        first = estimate_muscle_gain(totals, assumptions=fast_assumptions())
        second = estimate_muscle_gain(totals, assumptions=fast_assumptions())

        np.testing.assert_array_equal(
            first.muscle_gain_draws_lb, second.muscle_gain_draws_lb
        )
        self.assertEqual(first.muscle_gain_low_95_lb, second.muscle_gain_low_95_lb)
        self.assertEqual(first.muscle_gain_high_95_lb, second.muscle_gain_high_95_lb)

    def test_recent_window_uses_scan_nearest_three_years(self):
        estimate = estimate_muscle_gain(
            synthetic_totals(), assumptions=fast_assumptions()
        )
        self.assertEqual(str(estimate.recent.start_date), "2020-10-01")
        self.assertEqual(str(estimate.recent.end_date), "2024-01-01")

    def test_leave_one_out_returns_one_result_per_scan(self):
        gains = leave_one_scan_out_adjusted_gains(synthetic_totals())
        self.assertEqual(len(gains), len(synthetic_totals()))
        np.testing.assert_allclose(gains, np.full(len(gains), gains[0]), atol=1e-9)

    def test_rejects_sparse_totals_and_bad_assumptions(self):
        with self.assertRaisesRegex(ValueError, "at least five scans"):
            estimate_muscle_gain(synthetic_totals().head(4))
        with self.assertRaisesRegex(ValueError, "scan error"):
            estimate_muscle_gain(
                synthetic_totals(),
                assumptions=fast_assumptions(scan_error_sd_lb=-1.0),
            )


class TrainingEvidenceTest(unittest.TestCase):
    def test_compares_endpoint_years_without_sizing_muscle(self):
        workouts = pd.DataFrame(
            {
                "workout_id": ["a", "b", "c", "d"],
                "date": pd.to_datetime(
                    ["2018-01-01", "2019-08-01", "2023-08-01", "2024-08-01"]
                ),
            }
        )
        sets = pd.DataFrame(
            {
                "workout_id": ["b", "b", "d", "d"],
                "date": pd.to_datetime(
                    ["2019-08-01", "2019-08-01", "2024-08-01", "2024-08-01"]
                ),
                "display_name": ["Back Squats"] * 4,
                "one_rm": [300.0, 310.0, 350.0, 360.0],
                "reps": [5, 3, 5, 3],
            }
        )

        evidence = summarize_training_evidence(
            workouts,
            sets,
            pd.Timestamp("2020-01-01").date(),
            pd.Timestamp("2025-01-01").date(),
        )

        self.assertEqual(evidence.workouts_before_baseline, 2)
        self.assertEqual(evidence.workouts_during_scan_window, 2)
        self.assertEqual(len(evidence.comparisons), 1)
        self.assertGreater(evidence.comparisons[0].change_pct, 0)


class MuscleGainReportTest(unittest.TestCase):
    def test_chart_axes_are_independent_and_upper_panel_has_every_scan(self):
        totals = synthetic_totals()
        estimate = estimate_muscle_gain(
            totals, synthetic_regions(totals), fast_assumptions()
        )
        captured = {}

        def capture(figure, output_path, *, dpi, bbox_inches=None):
            captured["figure"] = figure
            return output_path

        with patch("dexa.muscle_gain_charts.save_chart", side_effect=capture):
            plot_muscle_gain_estimate(estimate, Path("unused.png"))

        figure = captured["figure"]
        upper, lower = figure.axes
        self.assertFalse(upper.get_shared_x_axes().joined(upper, lower))
        scan_collections = [
            collection
            for collection in upper.collections
            if isinstance(collection, PathCollection)
            and len(collection.get_offsets()) == len(totals)
        ]
        self.assertEqual(len(scan_collections), 1)

        lower_limit, upper_limit = lower.get_xlim()
        raw_change = estimate.earliest_to_latest.lean_soft_tissue_change_lb
        raw_change_95 = 1.96 * np.sqrt(2.0) * estimate.assumed_scan_error_sd_lb
        for endpoint in (
            raw_change - raw_change_95,
            raw_change + raw_change_95,
            estimate.muscle_gain_low_95_lb,
            estimate.muscle_gain_high_95_lb,
        ):
            self.assertLess(lower_limit, endpoint)
            self.assertGreater(upper_limit, endpoint)
        plt.close(figure)

    def test_report_states_the_measurement_distinction_and_interval(self):
        totals = synthetic_totals()
        estimate = estimate_muscle_gain(
            totals, synthetic_regions(totals), fast_assumptions()
        )
        report = render_muscle_gain_report(estimate)

        self.assertIn("DEXA lean soft tissue includes", report)
        self.assertIn("It is not skeletal muscle", report)
        self.assertIn("95% interval", report)
        self.assertIn("Hydration and glycogen", report)
        self.assertIn("Regional appendicular conversion", report)

    def test_pipeline_writes_report_and_shared_style_chart(self):
        totals = synthetic_totals()
        regions = synthetic_regions(totals)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            totals_path = root / "dexa.csv"
            regions_path = root / "dexa_regions.csv"
            totals.to_csv(totals_path, index=False)
            regions.to_csv(regions_path, index=False)

            _, _, outputs = run_muscle_gain_report(
                totals_path,
                regions_path,
                root / "output",
                fast_assumptions(),
            )

            self.assertTrue(outputs.report.is_file())
            self.assertTrue(outputs.chart.is_file())
            self.assertGreater(outputs.chart.stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
