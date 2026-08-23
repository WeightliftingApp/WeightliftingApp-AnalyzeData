import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]


class ChartLanguageGalleryTest(unittest.TestCase):
    def test_gallery_renders_all_three_archetypes_at_reviewable_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/render_chart_language_gallery.py"),
                    "--output-dir",
                    temp_dir,
                ],
                cwd=REPO_ROOT,
                env={**os.environ, "PYTHONPATH": "src:."},
                check=True,
                capture_output=True,
                text=True,
            )

            paths = [Path(line) for line in completed.stdout.splitlines() if line]
            self.assertEqual([path.name for path in paths], [
                "hero.png",
                "comparison.png",
                "diagnostic.png",
            ])
            for path in paths:
                self.assertTrue(path.is_file())
                with Image.open(path) as image:
                    self.assertEqual(image.size, (1400, 840))


if __name__ == "__main__":
    unittest.main()
