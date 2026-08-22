import json
import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = REPO_ROOT / "src"


def cell_source(notebook: str, index: int) -> str:
    data = json.loads((NOTEBOOK_DIR / notebook).read_text())
    value = data["cells"][index]["source"]
    return "".join(value) if isinstance(value, list) else value


class NotebookDesignLanguageTest(unittest.TestCase):
    def test_priority_migration_is_idempotent(self):
        subprocess.run(
            [
                str(REPO_ROOT / ".venv/bin/python"),
                str(REPO_ROOT / "scripts/upgrade_notebook_design_language.py"),
                "--check",
            ],
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": "src:."},
            check=True,
            capture_output=True,
            text=True,
        )

    def test_three_scale_charts_use_aligned_panels(self):
        wilks = cell_source("analyze_wilks.ipynb", 2)
        intensity = cell_source("analyze_workout_intensity.ipynb", 3)

        for chart in (wilks, intensity):
            self.assertIn("stacked_canvas(", chart)
            self.assertIn("ChartArchetype.", chart)
            self.assertNotIn("twinx(", chart)
        self.assertIn("PANELS SHARE TIME, NOT UNITS", wilks)
        self.assertIn("BODYWEIGHT AND TRAINING DENSITY, ON HONEST SCALES", intensity)

    def test_priority_titles_and_labels_state_their_evidence_role(self):
        big_three = cell_source("analyze_big_three.ipynb", 3)
        projection = cell_source("analyze_big_three.ipynb", 4)
        prs = cell_source("analyze_pr_szn.ipynb", 5)
        users = cell_source("analyze_users.ipynb", 4)

        self.assertIn("BIG THREE PR FRONTIERS KEEP MOVING UP", big_three)
        self.assertIn('style_legend(ax, loc="lower right")', big_three)
        self.assertIn("label_line_ends(", projection)
        self.assertIn("REPEATED ANNUAL PEAKS", prs)
        self.assertNotIn("SEASONAL PEAKS", prs)
        self.assertIn("TOP 1% OF RECORDED BENCH 1RMS", users)
        self.assertIn("annotate_reference_line(", users)


if __name__ == "__main__":
    unittest.main()
