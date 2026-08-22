import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.compare_charts import MAX_CHANGED_PIXEL_FRACTION, compare_pair


class CompareChartsTest(unittest.TestCase):
    def test_small_pixel_drift_passes_broad_check_and_writes_review_images(self):
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
            self.assertTrue(result["broad_check"]["passed"])
            self.assertEqual(
                result["broad_check"]["max_changed_pixel_fraction"],
                MAX_CHANGED_PIXEL_FRACTION,
            )
            self.assertEqual(result["broad_check"]["failures"], [])
            self.assertTrue((output / "before-side-by-side.png").is_file())
            self.assertTrue((output / "before-diff.png").is_file())

    def test_large_pixel_drift_fails_broad_check(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before.png"
            after = root / "after.png"
            Image.new("RGB", (20, 10), "white").save(before)
            Image.new("RGB", (20, 10), "black").save(after)

            result = compare_pair(before, after, root / "comparisons")

            self.assertFalse(result["broad_check"]["passed"])
            self.assertIn("exceeds", result["broad_check"]["failures"][0])

    def test_dimension_mismatch_fails_broad_check(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before.png"
            after = root / "after.png"
            Image.new("RGB", (20, 10), "white").save(before)
            Image.new("RGB", (21, 10), "white").save(after)

            result = compare_pair(before, after, root / "comparisons")

            self.assertFalse(result["broad_check"]["passed"])
            self.assertIn("dimensions differ", result["broad_check"]["failures"])


if __name__ == "__main__":
    unittest.main()
