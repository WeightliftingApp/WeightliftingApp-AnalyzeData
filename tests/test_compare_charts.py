import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.compare_charts import compare_pair


class CompareChartsTest(unittest.TestCase):
    def test_writes_review_images_and_reports_coarse_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before.png"
            after = root / "after.png"
            output = root / "comparisons"
            Image.new("RGB", (20, 10), "#f5f2ea").save(before)
            changed = Image.new("RGB", (20, 10), "#f5f2ea")
            changed.putpixel((5, 5), (0, 0, 0))
            changed.save(after)

            result = compare_pair(before, after, output)

            self.assertTrue(result["dimensions_match"])
            self.assertEqual(result["before"]["dimensions"], [20, 10])
            self.assertGreater(result["metrics"]["mean_abs_channel_difference"], 0)
            self.assertGreater(result["metrics"]["changed_pixel_fraction_over_8"], 0)
            self.assertTrue((output / "before-side-by-side.png").is_file())
            self.assertTrue((output / "before-diff.png").is_file())


if __name__ == "__main__":
    unittest.main()
