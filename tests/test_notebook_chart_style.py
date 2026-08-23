import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = REPO_ROOT / "src"
SHARED_CANVASES = ("chart_canvas(", "stacked_canvas(", "frame_figure(")


def cell_source(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else source


class NotebookChartStyleCoverageTest(unittest.TestCase):
    def test_every_rendered_notebook_chart_uses_the_shared_frame(self):
        chart_cells = []
        chart_notebooks = set()
        for notebook_path in sorted(NOTEBOOKS.glob("*.ipynb")):
            notebook = json.loads(notebook_path.read_text())
            for index, cell in enumerate(notebook["cells"]):
                source = cell_source(cell)
                if cell.get("cell_type") != "code" or "plt.show" not in source:
                    continue
                chart_cells.append((notebook_path.name, index))
                chart_notebooks.add(notebook_path.name)
                self.assertTrue(
                    any(helper in source for helper in SHARED_CANVASES),
                    f"{notebook_path.name} cell {index} bypasses chart_style",
                )

        self.assertEqual(len(chart_cells), 26)
        self.assertEqual(len(chart_notebooks), 11)

    def test_chart_free_streak_notebook_stays_chart_free(self):
        path = NOTEBOOKS / "analyze_workout_streaks.ipynb"
        notebook = json.loads(path.read_text())
        source = "\n".join(cell_source(cell) for cell in notebook["cells"])

        self.assertNotIn("plt.show", source)
        self.assertNotIn("from chart_style import", source)


if __name__ == "__main__":
    unittest.main()
