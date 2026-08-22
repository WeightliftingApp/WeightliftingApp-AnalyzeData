import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

import matplotlib.pyplot as plt
from PIL import Image

from chart_style import (
    PALETTE,
    PARETO_AXES,
    PARETO_FRAME,
    add_footer,
    add_header,
    chart_canvas,
    save_chart,
    style_axes,
)


class ChartStyleConstantsTest(unittest.TestCase):
    def test_palette_and_frames_are_deterministic_and_immutable(self):
        self.assertEqual(PALETTE.paper, "#f5f2ea")
        self.assertEqual(PALETTE.advance, "#dc2626")
        self.assertEqual(PARETO_FRAME.figsize, (12, 6.75))
        self.assertEqual(PARETO_FRAME.dpi, 200)
        self.assertEqual(PARETO_FRAME.plot_bounds, (0.08, 0.96, 0.82, 0.17))
        with self.assertRaises(FrozenInstanceError):
            PALETTE.paper = "#ffffff"


class ChartFramingTest(unittest.TestCase):
    def test_canvas_header_footer_and_axes_share_one_frame(self):
        with chart_canvas(PARETO_FRAME) as (fig, ax):
            add_header(fig, PARETO_FRAME, "TITLE", "Subtitle", ("META 1", "META 2"))
            add_footer(fig, PARETO_FRAME, "MODEL NOTE", "READING NOTE")
            style_axes(ax, PARETO_AXES)

            self.assertEqual(tuple(fig.get_size_inches()), PARETO_FRAME.figsize)
            self.assertEqual(
                tuple(round(value, 4) for value in fig.get_facecolor()),
                (0.9608, 0.949, 0.9176, 1.0),
            )
            self.assertEqual(
                tuple(round(value, 4) for value in ax.get_facecolor()),
                (0.9804, 0.9725, 0.949, 1.0),
            )
            bounds = ax.get_position()
            self.assertAlmostEqual(bounds.x0, 0.08)
            self.assertAlmostEqual(bounds.x1, 0.96)
            self.assertAlmostEqual(bounds.y0, 0.17)
            self.assertAlmostEqual(bounds.y1, 0.82)
            self.assertEqual(
                [text.get_text() for text in fig.texts],
                [
                    "TITLE",
                    "Subtitle",
                    "META 1",
                    "META 2",
                    "MODEL NOTE",
                    "READING NOTE",
                ],
            )
            self.assertFalse(ax.spines["top"].get_visible())
            self.assertFalse(ax.spines["right"].get_visible())
            plt.close(fig)

    def test_header_rejects_more_metadata_than_the_frame_can_place(self):
        with chart_canvas(PARETO_FRAME) as (fig, _):
            with self.assertRaisesRegex(ValueError, "at most two"):
                add_header(fig, PARETO_FRAME, "T", "S", ("1", "2", "3"))
            plt.close(fig)


class SaveChartTest(unittest.TestCase):
    def test_save_creates_parent_and_uses_requested_dpi(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "nested" / "chart.png"
            fig, _ = plt.subplots(figsize=(2, 1), facecolor=PALETTE.paper)

            returned = save_chart(fig, output_path, dpi=100)

            self.assertEqual(returned, output_path)
            self.assertTrue(output_path.is_file())
            with Image.open(output_path) as image:
                self.assertEqual(image.size, (200, 100))
                self.assertEqual(image.mode, "RGBA")
            self.assertNotIn(fig.number, plt.get_fignums())


if __name__ == "__main__":
    unittest.main()
