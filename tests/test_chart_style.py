import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
from PIL import Image

from chart_style import (
    ANNOTATION_STYLES,
    CATEGORICAL_COLORS,
    NOTEBOOK_AXES,
    PALETTE,
    PARETO_AXES,
    PARETO_FRAME,
    AnnotationKind,
    ChartArchetype,
    add_footer,
    add_header,
    annotate_point,
    annotate_reference_line,
    chart_canvas,
    format_count,
    format_delta,
    format_percent,
    format_weight,
    label_line_ends,
    notebook_frame,
    plot_estimate_interval,
    save_chart,
    stacked_canvas,
    style_axes,
    style_legend,
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

    def test_notebook_frame_preserves_requested_dimensions(self):
        frame = notebook_frame((15, 6), dpi=120)

        self.assertEqual(frame.figsize, (15, 6))
        self.assertEqual(frame.dpi, 120)
        self.assertEqual(frame.plot_bounds, (0.09, 0.96, 0.80, 0.17))
        self.assertEqual(len(CATEGORICAL_COLORS), 7)
        self.assertTrue(NOTEBOOK_AXES.axis_below)

        with patch("chart_style.plt.subplots", wraps=plt.subplots) as subplots:
            with chart_canvas(frame) as (fig, _):
                self.assertEqual(subplots.call_args.kwargs["dpi"], 120)
                plt.close(fig)

    def test_notebook_archetypes_change_hierarchy_without_changing_dimensions(self):
        hero = notebook_frame((12, 6), archetype=ChartArchetype.HERO)
        comparison = notebook_frame((12, 6), archetype="comparison")
        diagnostic = notebook_frame((12, 6), archetype=ChartArchetype.DIAGNOSTIC)

        self.assertEqual(hero.figsize, comparison.figsize)
        self.assertEqual(comparison.figsize, diagnostic.figsize)
        self.assertGreater(hero.title_size, comparison.title_size)
        self.assertGreater(comparison.title_size, diagnostic.title_size)
        self.assertLess(hero.plot_bounds[2], comparison.plot_bounds[2])
        self.assertGreater(diagnostic.plot_bounds[2], comparison.plot_bounds[2])
        with self.assertRaisesRegex(ValueError, "unknown chart archetype"):
            notebook_frame((8, 5), archetype="poster")

    def test_shared_formatters_use_consistent_units_and_signs(self):
        self.assertEqual(format_weight(1234.5, decimals=1), "1,234.5 lb")
        self.assertEqual(format_percent(12.34, decimals=1), "12.3%")
        self.assertEqual(format_percent(12.34, decimals=1, signed=True), "+12.3%")
        self.assertEqual(format_count(1234.4), "1,234")
        self.assertEqual(format_delta(-2.75, decimals=1), "-2.8 lb")


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

    def test_shared_legend_uses_the_editorial_frame(self):
        with chart_canvas(notebook_frame((8, 5))) as (fig, ax):
            ax.plot([0, 1], [0, 1], label="SERIES")
            legend = style_legend(ax, loc="upper left")

            self.assertEqual(legend.get_texts()[0].get_text(), "SERIES")
            self.assertEqual(
                tuple(round(value, 4) for value in legend.get_frame().get_facecolor()),
                (0.9804, 0.9725, 0.949, 0.96),
            )
            plt.close(fig)

    def test_stacked_canvas_can_keep_unrelated_x_axes_independent(self):
        frame = notebook_frame((8, 6))
        with stacked_canvas(
            frame, (2, 1), 0.25, sharex=False
        ) as (fig, axes):
            axes[0].set_xlim(2020, 2026)
            axes[1].set_xlim(-5, 10)

            self.assertEqual(axes[0].get_xlim(), (2020, 2026))
            self.assertEqual(axes[1].get_xlim(), (-5, 10))
            plt.close(fig)

    def test_header_rejects_more_metadata_than_the_frame_can_place(self):
        with chart_canvas(PARETO_FRAME) as (fig, _):
            with self.assertRaisesRegex(ValueError, "at most two"):
                add_header(fig, PARETO_FRAME, "T", "S", ("1", "2", "3"))
            plt.close(fig)

    def test_annotation_vocabulary_controls_tags_and_colors(self):
        with chart_canvas(notebook_frame((8, 5))) as (fig, ax):
            point = annotate_point(
                ax,
                1,
                2,
                "+4.0 lb",
                kind=AnnotationKind.CHANGE,
            )
            line, reference = annotate_reference_line(
                ax,
                1.5,
                "TARGET",
                kind=AnnotationKind.REFERENCE,
            )

            self.assertEqual(point.get_text(), "CHANGE  +4.0 lb")
            self.assertEqual(point.get_gid(), "annotation:change")
            self.assertEqual(point.get_color(), ANNOTATION_STYLES[AnnotationKind.CHANGE].color)
            self.assertEqual(reference.get_text(), "REFERENCE\nTARGET")
            self.assertEqual(line.get_gid(), "reference-line:reference")
            plt.close(fig)

    def test_direct_line_labels_separate_close_endpoints(self):
        with chart_canvas(notebook_frame((8, 5))) as (fig, ax):
            first, = ax.plot([0, 1], [0, 1], color=PALETTE.frontier, label="FIRST")
            second, = ax.plot([0, 1], [0, 1.01], color=PALETTE.advance, label="SECOND")
            labels = label_line_ends(ax, (first, second), min_gap_points=16)
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            baselines = sorted(label.get_window_extent(renderer).y0 for label in labels)

            self.assertEqual([label.get_text() for label in labels], ["FIRST", "SECOND"])
            self.assertGreaterEqual(baselines[1] - baselines[0], 10)
            with self.assertRaisesRegex(ValueError, "at most 1"):
                label_line_ends(ax, (first, second), max_labels=1)
            plt.close(fig)

    def test_estimate_interval_validates_complete_bounds(self):
        with chart_canvas(notebook_frame((8, 5))) as (fig, ax):
            container = plot_estimate_interval(
                ax,
                estimate=1.5,
                low=-3,
                high=6,
                y=0,
                label="MUSCLE",
            )

            self.assertEqual(container.lines[0].get_gid(), "estimate-point")
            with self.assertRaisesRegex(ValueError, "low <= estimate <= high"):
                plot_estimate_interval(ax, estimate=7, low=-3, high=6, y=1)
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
