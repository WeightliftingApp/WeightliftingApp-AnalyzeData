import unittest

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from chart_lint import assert_chart_lint_clean, lint_figure
from chart_style import (
    NOTEBOOK_AXES,
    PALETTE,
    AnnotationKind,
    add_footer,
    add_header,
    annotate_point,
    chart_canvas,
    notebook_frame,
    style_axes,
)


class ChartLintTest(unittest.TestCase):
    def test_clean_editorial_chart_has_no_objective_issues(self):
        frame = notebook_frame((8, 5))
        with chart_canvas(frame) as (fig, ax):
            ax.plot([0, 1], [100, 110], color=PALETTE.frontier, label="TREND")
            ax.set_xlabel("DATE")
            ax.set_ylabel("WEIGHT (LB)")
            style_axes(ax, NOTEBOOK_AXES)
            add_header(fig, frame, "TITLE", "Subtitle", ())
            add_footer(fig, frame, "MODEL", "READING", right_weight="normal")
            annotate_point(ax, 1, 110, "110 LB", kind=AnnotationKind.LATEST)

            issues = lint_figure(fig, expected_units={(0, "y"): "LB"})

            self.assertEqual(issues, ())
            assert_chart_lint_clean(fig, expected_units={(0, "y"): "LB"})
            plt.close(fig)

    def test_linter_reports_default_color_missing_labels_and_units(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])

        issues = lint_figure(fig, expected_units={(0, "y"): "LB"})
        codes = {issue.code for issue in issues}

        self.assertIn("default-series-color", codes)
        self.assertIn("missing-x-label", codes)
        self.assertIn("missing-y-label", codes)
        self.assertIn("missing-y-unit", codes)
        with self.assertRaisesRegex(AssertionError, "default-series-color"):
            assert_chart_lint_clean(fig)
        plt.close(fig)

    def test_linter_reports_dense_date_ticks_and_automatic_legend(self):
        dates = pd.date_range("2025-01-01", periods=20, freq="D")
        fig, ax = plt.subplots()
        ax.plot(dates, range(20), color=PALETTE.frontier, label="SERIES")
        ax.set_xlabel("DATE")
        ax.set_ylabel("VALUE")
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.legend(loc="best")

        codes = {issue.code for issue in lint_figure(fig, max_date_ticks=8)}

        self.assertIn("dense-date-ticks", codes)
        self.assertIn("automatic-legend-location", codes)
        plt.close(fig)

    def test_linter_detects_overlapping_figure_text(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1], color=PALETTE.frontier)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        fig.text(0.5, 0.5, "SAME PLACE", ha="center")
        fig.text(0.5, 0.5, "COLLISION", ha="center")

        codes = {issue.code for issue in lint_figure(fig)}

        self.assertIn("overlapping-figure-text", codes)
        plt.close(fig)


if __name__ == "__main__":
    unittest.main()
