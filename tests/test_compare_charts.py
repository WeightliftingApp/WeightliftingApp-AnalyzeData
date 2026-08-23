import tempfile
import unittest
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from scripts.compare_charts import (
    MAX_CHANGED_PIXEL_FRACTION,
    MAX_CROSS_RENDERER_CHANGED_FRACTION,
    compare_pair,
    evaluate_comparison,
    read_renderer,
)


def write_stamped(image: Image.Image, path: Path, renderer: str | None = None):
    """Save an image, stamping the Software chunk the way Matplotlib does."""
    metadata = None
    if renderer is not None:
        metadata = PngInfo()
        metadata.add_text(
            "Software", f"Matplotlib version{renderer}, https://matplotlib.org/"
        )
    image.save(path, pnginfo=metadata)
    return image


def write_png(path: Path, color: str, size=(20, 10), renderer: str | None = None):
    """Write a flat PNG, optionally stamped with a renderer version."""
    return write_stamped(Image.new("RGB", size, color), path, renderer)


class CompareChartsTest(unittest.TestCase):
    def test_small_pixel_drift_passes_broad_check_and_writes_review_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before.png"
            after = root / "after.png"
            output = root / "comparisons"
            write_png(before, "#f5f2ea", renderer="3.11.1")
            changed = write_png(after, "#f5f2ea", renderer="3.11.1")
            changed.putpixel((5, 5), (0, 0, 0))
            write_stamped(changed, after, renderer="3.11.1")

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
            write_png(before, "white", renderer="3.11.1")
            write_png(after, "black", renderer="3.11.1")

            result = compare_pair(before, after, root / "comparisons")

            self.assertFalse(result["broad_check"]["passed"])
            self.assertIn("exceeds", result["broad_check"]["failures"][0])

    def test_dimension_mismatch_fails_broad_check(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before.png"
            after = root / "after.png"
            write_png(before, "white", renderer="3.11.1")
            write_png(after, "white", size=(21, 10), renderer="3.11.1")

            result = compare_pair(before, after, root / "comparisons")

            self.assertFalse(result["broad_check"]["passed"])
            self.assertIn("dimensions differ", result["broad_check"]["failures"])


class RendererDetectionTest(unittest.TestCase):
    def test_reads_the_matplotlib_version_out_of_the_software_chunk(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "stamped.png"
            write_png(path, "#f5f2ea", renderer="3.11.1")

            with Image.open(path) as image:
                self.assertEqual(read_renderer(image), "matplotlib 3.11.1")

    def test_an_unstamped_png_reports_no_renderer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plain.png"
            write_png(path, "#f5f2ea")

            with Image.open(path) as image:
                self.assertIsNone(read_renderer(image))


class RendererAwareGateTest(unittest.TestCase):
    """The gate has to answer only the question its two inputs support.

    Matplotlib 3.11 changed FreeType, which re-flows every string by a
    fraction of a pixel. On this repository's baselines that reads as 0.0352
    with the generators untouched, so a strict 0.01 fidelity threshold across
    a renderer change reports a regression that did not happen.
    """

    def test_matching_renderers_keep_the_strict_fidelity_threshold(self):
        check = evaluate_comparison(
            True,
            0.0006,
            before_renderer="matplotlib 3.10.0",
            after_renderer="matplotlib 3.10.0",
        )

        self.assertTrue(check["passed"])
        self.assertEqual(check["mode"], "strict")
        self.assertTrue(check["renderer_match"])
        self.assertEqual(
            check["max_changed_pixel_fraction"], MAX_CHANGED_PIXEL_FRACTION
        )
        self.assertEqual(check["notes"], [])

    def test_matching_renderers_still_fail_a_real_regression(self):
        check = evaluate_comparison(
            True,
            0.05,
            before_renderer="matplotlib 3.10.0",
            after_renderer="matplotlib 3.10.0",
        )

        self.assertFalse(check["passed"])
        self.assertIn("exceeds", check["failures"][0])

    def test_a_renderer_change_is_reported_rather_than_certified(self):
        check = evaluate_comparison(
            True,
            0.035209,
            before_renderer="matplotlib 3.10.0",
            after_renderer="matplotlib 3.11.1",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["mode"], "cross-renderer")
        self.assertFalse(check["renderer_match"])
        self.assertEqual(len(check["failures"]), 1)
        self.assertIn("not certifiable by pixel count", check["failures"][0])
        self.assertIn("matplotlib 3.10.0", check["failures"][0])
        self.assertIn("glyph re-flow", check["notes"][0])

    def test_an_acknowledged_renderer_change_passes_and_says_so(self):
        check = evaluate_comparison(
            True,
            0.035209,
            before_renderer="matplotlib 3.10.0",
            after_renderer="matplotlib 3.11.1",
            accept_renderer_drift=True,
        )

        self.assertTrue(check["passed"])
        self.assertEqual(
            check["max_changed_pixel_fraction"], MAX_CROSS_RENDERER_CHANGED_FRACTION
        )
        self.assertIn("reviewer accepted the renderer mismatch", check["notes"])

    def test_acknowledging_a_renderer_change_does_not_wave_through_a_blank_chart(self):
        check = evaluate_comparison(
            True,
            0.9,
            before_renderer="matplotlib 3.10.0",
            after_renderer="matplotlib 3.11.1",
            accept_renderer_drift=True,
        )

        self.assertFalse(check["passed"])
        self.assertIn("exceeds", check["failures"][0])

    def test_a_renderer_change_never_excuses_a_dimension_change(self):
        check = evaluate_comparison(
            False,
            0.0,
            before_renderer="matplotlib 3.10.0",
            after_renderer="matplotlib 3.11.1",
            accept_renderer_drift=True,
        )

        self.assertFalse(check["passed"])
        self.assertIn("dimensions differ", check["failures"])

    def test_two_unknown_renderers_are_not_treated_as_a_match(self):
        # Absent metadata is not evidence of a shared renderer. Two unknowns
        # are two unknowns, which is the case this gate cannot certify.
        check = evaluate_comparison(True, 0.0001)

        self.assertFalse(check["passed"])
        self.assertEqual(check["mode"], "cross-renderer")
        self.assertFalse(check["renderer_match"])
        self.assertIn("not certifiable by pixel count", check["failures"][0])
        self.assertIn("do not both record which renderer", check["notes"][0])

    def test_a_missing_renderer_on_one_side_is_also_uncertifiable(self):
        check = evaluate_comparison(
            True, 0.0001, before_renderer="matplotlib 3.10.0", after_renderer=None
        )

        self.assertFalse(check["passed"])
        self.assertFalse(check["renderer_match"])
        self.assertIn("matplotlib 3.10.0 -> unknown", check["notes"][0])

    def test_compare_pair_reads_the_renderers_off_the_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before, after = root / "before.png", root / "after.png"
            write_png(before, "#f5f2ea", renderer="3.10.0")
            write_png(after, "#f5f2ea", renderer="3.11.1")

            result = compare_pair(before, after, root / "comparisons")
            accepted = compare_pair(
                before,
                after,
                root / "comparisons",
                accept_renderer_drift=True,
            )

            self.assertEqual(result["before"]["renderer"], "matplotlib 3.10.0")
            self.assertEqual(result["after"]["renderer"], "matplotlib 3.11.1")
            self.assertFalse(result["broad_check"]["passed"])
            self.assertTrue(accepted["broad_check"]["passed"])


if __name__ == "__main__":
    unittest.main()
