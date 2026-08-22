import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.compare_notebook_charts import compare_notebook_images


class CompareNotebookImagesTest(unittest.TestCase):
    def test_pairs_images_by_extracted_notebook_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            baseline = root / "before"
            after = root / "after"
            output = root / "comparison"
            relative = Path("analysis_files") / "analysis_2_0.png"
            (baseline / relative).parent.mkdir(parents=True)
            (after / relative).parent.mkdir(parents=True)
            Image.new("RGB", (20, 10), "white").save(baseline / relative)
            Image.new("RGB", (20, 10), "black").save(after / relative)

            report = compare_notebook_images(baseline, after, output)

            self.assertTrue(report["all_images_paired"])
            self.assertEqual(report["paired_count"], 1)
            self.assertTrue(
                (output / "side-by-side" / relative).is_file()
            )
            self.assertTrue((output / "comparison-report.json").is_file())
            self.assertTrue((output / "overview.png").is_file())
            gallery = (output / "gallery.md").read_text()
            self.assertIn("Paired images: 1", gallery)
            self.assertIn(str(relative), gallery)

    def test_reports_missing_and_added_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            baseline = root / "before"
            after = root / "after"
            output = root / "comparison"
            baseline.mkdir()
            after.mkdir()
            Image.new("RGB", (5, 5)).save(baseline / "missing.png")
            Image.new("RGB", (5, 5)).save(after / "added.png")

            report = compare_notebook_images(baseline, after, output)

            self.assertFalse(report["all_images_paired"])
            self.assertEqual(report["missing_after"], ["missing.png"])
            self.assertEqual(report["added_after"], ["added.png"])


if __name__ == "__main__":
    unittest.main()
