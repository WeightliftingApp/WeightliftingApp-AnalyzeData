import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import pandas as pd

from dexa.charts import plot_lean_mass_vs_bodyweight
from generate_bench_frontier_update import render_frontier_update


def dexa_totals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-06-01", "2026-01-01"]),
            "weight_lb": [200.0, 210.0, 205.0],
            "lean_soft_tissue_lb": [160.0, 164.0, 163.0],
            "bone_mineral_content_lb": [9.0, 9.1, 9.2],
        }
    )


def bench_attempts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("2019-01-01", "w1", 190.0, 350.0, 225.0, 10),
            ("2020-01-01", "w2", 200.0, 400.0, 275.0, 8),
            ("2021-01-01", "w3", 210.0, 450.0, 315.0, 8),
            ("2021-06-01", "w4", 205.0, 390.0, 275.0, 6),
            ("2026-08-21", "w5", 205.0, 460.0, 315.0, 14),
        ],
        columns=["date", "workout_id", "bodyweight", "one_rm", "weight", "reps"],
    ).assign(date=lambda frame: pd.to_datetime(frame["date"]))


class DexaChartSemanticsTest(unittest.TestCase):
    def test_retains_scan_labels_trends_contours_axes_and_footer(self):
        captured = {}

        def capture(fig, output_path, **_):
            captured["fig"] = fig
            return output_path

        with patch("dexa.charts.save_chart", side_effect=capture):
            plot_lean_mass_vs_bodyweight(dexa_totals(), Path("unused.png"))

        fig = captured["fig"]
        ax = fig.axes[0]
        text = "\n".join(item.get_text() for item in [*fig.texts, *ax.texts])
        self.assertIn("LEAN MASS VS BODYWEIGHT", text)
        self.assertIn("3 DEXA SCANS", text)
        self.assertIn("LATEST  2026.01  /  163.0 LB LEAN", text)
        self.assertIn("BODY FAT CONTOURS: 1 PP", text)
        self.assertIn("BLUE = CUT  /  RED = BULK", text)
        self.assertEqual(ax.get_xlabel(), "BODYWEIGHT (LB)")
        self.assertEqual(ax.get_ylabel(), "LEAN SOFT TISSUE (LB)")
        self.assertGreaterEqual(len(ax.lines), 2)
        self.assertGreaterEqual(len(ax.patches), 2)
        self.assertGreaterEqual(len(ax.collections), 4)
        plt.close(fig)


class BenchChartSemanticsTest(unittest.TestCase):
    def test_retains_frontiers_advance_metadata_legend_axes_and_model_footer(self):
        captured = {}

        def capture(fig, output_path, **_):
            captured["fig"] = fig
            return output_path

        with patch("generate_bench_frontier_update.save_chart", side_effect=capture):
            result = render_frontier_update(
                bench_attempts(), Path("unused.png"), pd.Timestamp("2026-08-21")
            )

        fig = captured["fig"]
        ax = fig.axes[0]
        text = "\n".join(item.get_text() for item in [*fig.texts, *ax.texts])
        legend = [item.get_text() for item in ax.get_legend().get_texts()]
        self.assertEqual(result["previous_frontier_points"], 3)
        self.assertEqual(result["current_frontier_points"], 3)
        self.assertEqual(result["set"], "315x14")
        self.assertIn("BENCH PRESS", text)
        self.assertIn("5 WORKOUTS  /  5 ATTEMPTS", text)
        self.assertIn("NEW FRONTIER  ·  315×14", text)
        self.assertIn("FRONTIER: NON-DOMINATED", text)
        self.assertEqual(ax.get_xlabel(), "COST PROXY · BODYWEIGHT (LB)")
        self.assertEqual(ax.get_ylabel(), "CAPABILITY SCORE · 1RME (LB)")
        self.assertEqual(legend, ["PREVIOUS FRONTIER  n=3", "TODAY'S ADVANCE"])
        self.assertEqual(len(ax.lines), 2)
        self.assertGreaterEqual(len(ax.collections), 3)
        plt.close(fig)


if __name__ == "__main__":
    unittest.main()
