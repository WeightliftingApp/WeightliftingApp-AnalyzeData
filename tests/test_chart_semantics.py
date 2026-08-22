import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.collections import LineCollection, PathCollection
from matplotlib.colors import to_rgba

from chart_style import PALETTE
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


def negative_residual_bulk_totals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-06-01", "2026-01-01"]),
            "weight_lb": [200.0, 210.0, 220.0],
            "lean_soft_tissue_lb": [160.0, 170.0, 165.0],
            "bone_mineral_content_lb": [9.0, 9.1, 9.2],
        }
    )


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
        self.assertIn("1 TO 3 = TIME", text)
        self.assertIn("BLUE = CUT  /  RED = BULK", text)
        self.assertEqual(ax.get_xlabel(), "BODYWEIGHT (LB)")
        self.assertEqual(ax.get_ylabel(), "LEAN SOFT TISSUE (LB)")
        self.assertEqual(len(ax.lines), 2)
        self.assertEqual(len(ax.patches), 2)
        scan_collections = [
            collection
            for collection in ax.collections
            if isinstance(collection, PathCollection)
            and len(collection.get_offsets()) == 3
        ]
        residual_collections = [
            collection
            for collection in ax.collections
            if isinstance(collection, LineCollection)
            and len(collection.get_segments()) == 3
        ]
        self.assertEqual(len(scan_collections), 1)
        self.assertEqual(len(residual_collections), 1)
        self.assertEqual(
            [
                sum(item.get_text() == str(scan) for item in ax.texts)
                for scan in range(1, 4)
            ],
            [1, 1, 1],
        )
        plt.close(fig)

    def test_negative_residual_bulk_uses_negative_and_bulk_semantic_colors(self):
        captured = {}

        def capture(fig, output_path, **_):
            captured["fig"] = fig
            return output_path

        with patch("dexa.charts.save_chart", side_effect=capture):
            plot_lean_mass_vs_bodyweight(
                negative_residual_bulk_totals(), Path("unused.png")
            )

        fig = captured["fig"]
        ax = fig.axes[0]
        residual_label = next(
            item for item in ax.texts if "VS TREND" in item.get_text()
        )
        efficiency_label = next(
            item for item in ax.texts if item.get_text().startswith("BULK EFF")
        )
        residual_bars = next(
            collection
            for collection in ax.collections
            if isinstance(collection, LineCollection)
            and len(collection.get_segments()) == 3
        )

        self.assertLess(float(residual_label.get_text().split()[0]), 0)
        self.assertEqual(to_rgba(residual_label.get_color()), to_rgba(PALETTE.negative))
        self.assertEqual(to_rgba(efficiency_label.get_color()), to_rgba(PALETTE.bulk))
        self.assertEqual(
            tuple(residual_bars.get_colors()[-1]),
            to_rgba(PALETTE.negative, alpha=0.78),
        )
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
        self.assertEqual(result["attempts"], 5)
        self.assertEqual(result["workouts"], 5)
        self.assertEqual(result["set"], "315x14")
        self.assertIn("BENCH PRESS", text)
        self.assertIn("5 WORKOUTS  /  5 ATTEMPTS", text)
        self.assertIn("NEW FRONTIER  ·  315×14", text)
        self.assertIn("FRONTIER: NON-DOMINATED", text)
        self.assertEqual(ax.get_xlabel(), "COST PROXY · BODYWEIGHT (LB)")
        self.assertEqual(ax.get_ylabel(), "CAPABILITY SCORE · 1RME (LB)")
        self.assertEqual(legend, ["PREVIOUS FRONTIER  n=3", "TODAY'S ADVANCE"])
        self.assertEqual(len(ax.lines), 2)
        self.assertEqual(len(ax.collections), 3)
        observation_counts = sorted(
            len(collection.get_offsets())
            for collection in ax.collections
            if isinstance(collection, PathCollection)
        )
        self.assertEqual(observation_counts, [1, 3, 5])
        plt.close(fig)


if __name__ == "__main__":
    unittest.main()
