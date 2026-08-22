import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection, PathCollection, PolyCollection
from matplotlib.colors import to_rgba
from PIL import Image

from chart_style import FORECAST_FRAME, PALETTE
from dexa.charts import plot_lean_mass_vs_bodyweight
from dexa.forecast import (
    PREDICTION_COVERAGE,
    PREDICTION_COVERAGE_INNER,
    SAFETY_CONFIDENCE,
    ForecastAssumptions,
    forecast_bulk_ceiling,
)
from dexa.forecast_charts import model_footer, plot_bulk_ceiling
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


# Alternating bulk and cut scans. Every fixture below is synthetic: the real
# DEXA export is personal data and is excluded from version control.
FORECAST_ROWS = [
    ("2022-01-01", 190.0, 168.0),
    ("2022-06-01", 210.0, 174.0),
    ("2022-12-01", 196.0, 170.0),
    ("2023-04-01", 216.0, 175.0),
    ("2023-09-01", 200.0, 172.0),
    ("2024-02-01", 220.0, 182.0),
    ("2024-08-01", 205.0, 176.0),
    ("2025-01-01", 225.0, 184.0),
    ("2025-07-01", 208.0, 178.0),
    ("2026-01-01", 228.0, 188.0),
]


def forecast_totals(rows=FORECAST_ROWS) -> pd.DataFrame:
    """Build a totals frame from (date, weight, fat-free mass) triples."""
    dates, weights, fat_free = zip(*rows)
    weights = np.array(weights, dtype=float)
    fat_free = np.array(fat_free, dtype=float)
    fat = weights - fat_free
    return pd.DataFrame(
        {
            "date": pd.to_datetime(list(dates)),
            "weight_lb": weights,
            "lean_soft_tissue_lb": fat_free - 9.0,
            "fat_mass_lb": fat,
            "bone_mineral_content_lb": np.full(len(weights), 9.0),
            "body_fat_pct": 100.0 * fat / weights,
            "fat_free_mass_lb": fat_free,
            "ffmi": np.full(len(weights), 25.0),
            "normalized_ffmi": np.full(len(weights), 25.0),
            "bmi": np.full(len(weights), 29.0),
            "height_in": np.full(len(weights), 72.0),
            "notes": [""] * len(weights),
        }
    )


def bulk_forecast(**overrides):
    """A small seeded forecast, fast enough to run inside a chart test."""
    settings = {"simulations": 2000, "seed": 7}
    settings.update(overrides)
    return forecast_bulk_ceiling(forecast_totals(), ForecastAssumptions(**settings))


def render_forecast(forecast):
    """Return the forecast figure instead of writing it to disk."""
    captured = {}

    def capture(fig, output_path, **_):
        captured["fig"] = fig
        return output_path

    with patch("dexa.forecast_charts.save_chart", side_effect=capture):
        plot_bulk_ceiling(forecast, Path("unused.png"))
    return captured["fig"]


def figure_text(fig) -> str:
    parts = [item.get_text() for item in fig.texts]
    for ax in fig.axes:
        parts.extend(item.get_text() for item in ax.texts)
    return "\n".join(parts)


def band_collections(ax):
    """The filled prediction bands in draw order: the 95% band, then the 80%."""
    return [item for item in ax.collections if isinstance(item, PolyCollection)]


class ForecastChartSemanticsTest(unittest.TestCase):
    def test_keeps_both_panels_every_layer_and_every_claim(self):
        forecast = bulk_forecast()
        fig = render_forecast(forecast)
        upper, lower = fig.axes
        text = figure_text(fig)
        legend = [item.get_text() for item in upper.get_legend().get_texts()]

        self.assertEqual(len(fig.axes), 2)
        self.assertIn("HOW HEAVY BEFORE 20% BODY FAT", text)
        self.assertIn(
            f"{forecast.interval_count} POSITIVE-WEIGHT DEXA INTERVALS", text
        )
        self.assertIn(
            f"{forecast.resampling_unit_count} RESAMPLING UNITS"
            f"  /  ANCHOR {forecast.current_date}",
            text,
        )
        self.assertEqual(
            legend,
            [
                "95% PREDICTION BAND",
                "80% PREDICTION BAND",
                "MEDIAN MODELED READING",
                "20% TARGET",
                f"{forecast.current_date} SCAN",
            ],
        )
        self.assertEqual(upper.get_ylabel(), "MODELED BODY FAT (%)")
        self.assertEqual(lower.get_ylabel(), "PROBABILITY UNDER 20% (%)")
        self.assertEqual(lower.get_xlabel(), "BODYWEIGHT (LB)")
        self.assertEqual(upper.get_xlabel(), "")

        # Median, target line, probability curve, safety confidence line, and
        # the two dashed reference weights, one drawn on each panel.
        self.assertEqual(len(upper.lines), 4)
        self.assertEqual(len(lower.lines), 3)
        np.testing.assert_allclose(
            upper.lines[0].get_ydata(), forecast.body_fat_median_pct
        )
        np.testing.assert_allclose(
            lower.lines[0].get_ydata(), forecast.probability_under_target * 100.0
        )
        np.testing.assert_allclose(
            lower.lines[0].get_xdata(), forecast.weight_grid_lb
        )
        self.assertEqual(lower.get_ylim(), (0.0, 104.0))
        self.assertEqual(list(lower.get_yticks()), [0, 25, 50, 75, 100])

        # The current scan is plotted on the upper panel and annotated with the
        # same two numbers it is plotted at.
        scans = [
            item
            for item in upper.collections
            if isinstance(item, PathCollection) and len(item.get_offsets()) == 1
        ]
        self.assertEqual(len(scans), 1)
        np.testing.assert_allclose(
            scans[0].get_offsets()[0],
            [forecast.current_weight_lb, forecast.current_body_fat_pct],
        )
        self.assertIn(
            f"{forecast.current_weight_lb:.1f} LB\n"
            f"{forecast.current_body_fat_pct:.1f}%",
            text,
        )
        plt.close(fig)

    def test_eighty_percent_band_nests_inside_the_ninety_five_percent_band(self):
        forecast = bulk_forecast()
        fig = render_forecast(forecast)
        upper = fig.axes[0]
        outer, inner = band_collections(upper)

        self.assertEqual(len(band_collections(upper)), 2)
        self.assertLess(outer.get_alpha(), inner.get_alpha())
        self.assertTrue(
            np.all(forecast.body_fat_low_95_pct <= forecast.body_fat_low_80_pct)
        )
        self.assertTrue(
            np.all(forecast.body_fat_high_80_pct <= forecast.body_fat_high_95_pct)
        )
        outer_y = outer.get_paths()[0].vertices[:, 1]
        inner_y = inner.get_paths()[0].vertices[:, 1]
        self.assertLessEqual(outer_y.min(), inner_y.min())
        self.assertGreaterEqual(outer_y.max(), inner_y.max())
        self.assertEqual(
            f"{PREDICTION_COVERAGE:.0%}/{PREDICTION_COVERAGE_INNER:.0%}", "95%/80%"
        )
        plt.close(fig)

    def test_semantic_colors_come_from_the_shared_palette(self):
        forecast = bulk_forecast()
        fig = render_forecast(forecast)
        upper, lower = fig.axes
        median, target = upper.lines[0], upper.lines[1]
        constant_ffm = next(
            item
            for item in upper.texts
            if item.get_text().startswith("CONSTANT FFM")
        )
        safety = next(
            item
            for item in upper.texts
            if "SAFETY CEILING" in item.get_text()
        )

        self.assertEqual(to_rgba(median.get_color()), to_rgba(PALETTE.frontier))
        self.assertEqual(to_rgba(target.get_color()), to_rgba(PALETTE.negative))
        self.assertEqual(
            to_rgba(constant_ffm.get_color()), to_rgba(PALETTE.reference)
        )
        self.assertEqual(to_rgba(safety.get_color()), to_rgba(PALETTE.frontier))
        self.assertEqual(
            to_rgba(lower.lines[0].get_color()), to_rgba(PALETTE.frontier)
        )
        self.assertEqual(
            to_rgba(lower.lines[1].get_color()), to_rgba(PALETTE.negative)
        )
        for band in band_collections(upper):
            self.assertEqual(
                tuple(band.get_facecolor()[0][:3]), to_rgba(PALETTE.frontier)[:3]
            )
        plt.close(fig)

    def test_model_footer_discloses_the_simulation_and_sparse_evidence(self):
        forecast = bulk_forecast(simulations=2000, seed=7)
        fig = render_forecast(forecast)
        left, right = fig.texts[-2], fig.texts[-1]

        self.assertTrue(forecast.is_sparse)
        self.assertEqual(
            left.get_text(),
            "SEED 7  /  2,000 DRAWS  /  0.38 PP ASSUMED SCAN ERROR"
            f"  /  SPARSE: {forecast.resampling_unit_count} UNITS",
        )
        self.assertEqual(
            right.get_text(), "MODELED, NOT MEASURED  /  BANDS = 80% INSIDE 95%"
        )
        plt.close(fig)

    def test_unidentified_safety_ceiling_is_stated_rather_than_drawn(self):
        # A cap just above the current scan leaves the ceiling unresolved.
        forecast = bulk_forecast(max_weight_lb=231.0)
        fig = render_forecast(forecast)
        upper, lower = fig.axes
        text = figure_text(fig)

        self.assertFalse(forecast.safety_ceiling.identified)
        self.assertIn(
            f"{SAFETY_CONFIDENCE:.0%} SAFETY CEILING "
            f"{forecast.safety_ceiling.describe_short()}",
            text,
        )
        self.assertEqual(
            [
                item
                for item in lower.collections
                if isinstance(item, PathCollection)
            ],
            [],
        )
        self.assertNotIn("SAFETY CEILING\n", text)
        plt.close(fig)

    def test_output_keeps_the_preserved_canvas_size_and_dpi(self):
        forecast = bulk_forecast()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "forecast.png"
            plot_bulk_ceiling(forecast, output_path)
            with Image.open(output_path) as image:
                self.assertEqual(image.size, (2200, 1800))
        self.assertEqual(FORECAST_FRAME.figsize, (11, 9))
        self.assertEqual(FORECAST_FRAME.dpi, 200)


class ForecastChartLayoutTest(unittest.TestCase):
    """Guard the one-row footer and the axis labels against collisions.

    Both footer strings and both y-axis labels grow with the assumptions, so a
    longer target, a larger draw count, or a longer seed must not push text
    into its neighbour. These assert a real gap rather than bare non-overlap,
    so a change that merely grazes past a collision still fails.
    """

    #: Minimum clear space between two text blocks sharing a row, in pixels of
    #: the 2200 x 1800 canvas. Roughly three monospace characters.
    MINIMUM_GAP_PX = 40.0

    def drawn(self, forecast):
        fig = render_forecast(forecast)
        fig.canvas.draw()
        return fig, fig.canvas.get_renderer()

    def assert_clear(self, renderer, left, right):
        left_box = left.get_window_extent(renderer)
        right_box = right.get_window_extent(renderer)
        self.assertGreaterEqual(
            right_box.x0 - left_box.x1,
            self.MINIMUM_GAP_PX,
            f"{left.get_text()!r} crowds {right.get_text()!r}",
        )

    def test_the_two_footer_columns_keep_a_gap_at_their_widest(self):
        forecast = bulk_forecast()
        fig, renderer = self.drawn(forecast)
        left, right = fig.texts[-2], fig.texts[-1]

        # The note this chart actually writes, sparse warning included.
        self.assertTrue(forecast.is_sparse)
        self.assertIn("SPARSE", left.get_text())
        self.assert_clear(renderer, left, right)
        self.assertGreaterEqual(left.get_window_extent(renderer).x0, 0.0)
        self.assertLessEqual(right.get_window_extent(renderer).x1, fig.bbox.x1)

        # Then the longest note the generator can produce: a ten-digit seed
        # and a seven-figure draw count. The string comes from `model_footer`,
        # so this measures the real text without simulating a million paths.
        widest = replace(
            forecast,
            assumptions=replace(
                forecast.assumptions, simulations=1_000_000, seed=1_234_567_890
            ),
        )
        left.set_text(model_footer(widest))
        fig.canvas.draw()

        self.assertIn("SEED 1234567890  /  1,000,000 DRAWS", left.get_text())
        self.assert_clear(fig.canvas.get_renderer(), left, right)
        plt.close(fig)

    def test_the_header_block_clears_the_metadata_column(self):
        forecast = bulk_forecast(target_body_fat_pct=22.5)
        fig, renderer = self.drawn(forecast)
        title, subtitle = fig.texts[0], fig.texts[1]

        self.assertIn("22.5% BODY FAT", title.get_text())
        for header in (title, subtitle):
            for metadata in fig.texts[2:4]:
                self.assert_clear(renderer, header, metadata)
        plt.close(fig)

    def test_each_y_axis_label_fits_inside_its_own_panel(self):
        forecast = bulk_forecast(target_body_fat_pct=22.5)
        fig, renderer = self.drawn(forecast)

        self.assertEqual(fig.axes[1].get_ylabel(), "PROBABILITY UNDER 22.5% (%)")
        for axis in fig.axes:
            label_box = axis.yaxis.label.get_window_extent(renderer)
            panel_box = axis.get_window_extent(renderer)
            self.assertLessEqual(label_box.height, panel_box.height)
            self.assertGreaterEqual(label_box.x0, 0.0)
            self.assertLess(label_box.x1, panel_box.x0)
        plt.close(fig)


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
