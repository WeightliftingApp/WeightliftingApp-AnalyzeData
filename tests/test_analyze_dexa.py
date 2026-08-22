import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from dexa.calculations import (
    add_interval_efficiency,
    analyze_body_composition,
    fit_lean_mass_trend,
    modeled_body_fat_pct,
)
from dexa.pipeline import run_report
from dexa.report import render_markdown
from scripts.analyze_dexa import fit_lean_mass_trend as compatibility_trend


def totals_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2022-09-15", "2026-07-10", "2026-08-21"]),
            "weight_lb": [190.8, 223.2, 214.8],
            "lean_soft_tissue_lb": [168.0, 179.3, 177.4],
            "fat_mass_lb": [13.7, 34.8, 28.2],
            "bone_mineral_content_lb": [9.1, 9.1, 9.2],
            "body_fat_pct": [7.18, 15.59, 13.13],
            "fat_free_mass_lb": [177.1, 188.4, 186.6],
            "ffmi": [24.02, 25.55, 25.31],
            "normalized_ffmi": [23.84, 25.38, 25.13],
            "bmi": [25.88, 30.27, 29.13],
            "height_in": [72.0, 72.0, 72.0],
            "notes": ["baseline", "previous", "latest"],
        }
    )


def regions_fixture() -> pd.DataFrame:
    rows = []
    values = {
        "Arms": ((5.0, 29.0, 1.4, 14.1), (4.0, 27.9, 1.4, 12.0)),
        "Legs": ((13.0, 58.0, 3.1, 17.5), (11.0, 57.1, 3.1, 15.5)),
        "Trunk": ((15.0, 84.5, 2.9, 14.6), (11.0, 83.9, 2.9, 11.2)),
        "Android (Waist)": ((1.8, 12.0, 0.2, 12.9), (1.2, 11.8, 0.2, 8.9)),
        "Gynoid (Hips)": ((7.0, 29.3, 1.0, 18.8), (5.1, 28.9, 1.0, 15.0)),
    }
    for region, (previous, latest) in values.items():
        for scan_date, measurements in (
            ("2026-07-10", previous),
            ("2026-08-21", latest),
        ):
            rows.append(
                {
                    "date": pd.Timestamp(scan_date),
                    "region": region,
                    "fat_mass_lb": measurements[0],
                    "lean_soft_tissue_lb": measurements[1],
                    "bone_mineral_content_lb": measurements[2],
                    "body_fat_pct": measurements[3],
                }
            )
    return pd.DataFrame(rows)


class FitLeanMassTrendTest(unittest.TestCase):
    def test_returns_vertical_residuals_and_r_squared(self):
        totals = pd.DataFrame(
            {
                "weight_lb": [100.0, 120.0, 140.0],
                "lean_soft_tissue_lb": [60.0, 70.0, 80.0],
            }
        )

        slope, intercept, residuals, r_squared = fit_lean_mass_trend(totals)

        self.assertAlmostEqual(slope, 0.5)
        self.assertAlmostEqual(intercept, 10.0)
        np.testing.assert_allclose(residuals, [0.0, 0.0, 0.0], atol=1e-12)
        self.assertAlmostEqual(r_squared, 1.0)

    def test_script_keeps_calculation_import_compatibility(self):
        self.assertIs(compatibility_trend, fit_lean_mass_trend)


class ModeledBodyFatPctTest(unittest.TestCase):
    def test_accounts_for_lean_tissue_and_fixed_bone_mass(self):
        body_fat_pct = modeled_body_fat_pct(
            np.array([200.0]),
            np.array([160.0]),
            bone_mineral_content_lb=10.0,
        )

        np.testing.assert_allclose(body_fat_pct, [15.0])


class AddIntervalEfficiencyTest(unittest.TestCase):
    def test_uses_lean_gain_share_for_bulks_and_nonlean_loss_share_for_cuts(self):
        totals = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
                "weight_lb": [200.0, 210.0, 205.0],
                "lean_soft_tissue_lb": [160.0, 164.0, 163.0],
            }
        )

        result = add_interval_efficiency(totals)

        self.assertEqual(result["phase"].tolist(), ["BASELINE", "BULK", "CUT"])
        self.assertTrue(np.isnan(result.iloc[0]["interval_efficiency"]))
        self.assertAlmostEqual(result.iloc[1]["interval_efficiency"], 0.4)
        self.assertAlmostEqual(result.iloc[2]["interval_efficiency"], 0.8)


class AnalyzeBodyCompositionTest(unittest.TestCase):
    def test_preserves_latest_scan_calculations(self):
        analysis = analyze_body_composition(totals_fixture(), regions_fixture())

        self.assertAlmostEqual(analysis.total_loss, 8.4)
        self.assertAlmostEqual(analysis.fat_loss, 6.6)
        self.assertAlmostEqual(analysis.lean_loss, 1.9)
        self.assertAlmostEqual(analysis.fat_share, 6.6 / 8.4)
        self.assertAlmostEqual(analysis.delta["body_fat_pct"], -2.46)

        markdown = render_markdown(analysis)
        self.assertIn("**8.4 lb down**", markdown)
        self.assertIn("**79% of the scale loss came from fat**", markdown)
        self.assertIn("| FFMI | 25.55 | 25.31 | -0.24 |", markdown)

    def test_pure_analysis_and_rendering_do_not_write_files(self):
        totals = totals_fixture()
        regions = regions_fixture()

        with (
            patch("builtins.open", side_effect=AssertionError("unexpected write")),
            patch.object(Path, "open", side_effect=AssertionError("unexpected write")),
            patch.object(
                Path, "write_text", side_effect=AssertionError("unexpected write")
            ),
        ):
            analysis = analyze_body_composition(totals, regions)
            markdown = render_markdown(analysis)

        self.assertIn("# DEXA analysis — 2026-08-21", markdown)


class ReportPipelineTest(unittest.TestCase):
    def test_report_run_does_not_modify_source_csvs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            totals_path = root / "dexa.csv"
            regions_path = root / "dexa_regions.csv"
            output_dir = root / "outputs"
            totals_fixture().to_csv(totals_path, index=False)
            regions_fixture().to_csv(regions_path, index=False)
            totals_before = totals_path.read_bytes()
            regions_before = regions_path.read_bytes()

            outputs = run_report(totals_path, regions_path, output_dir)

            self.assertEqual(totals_path.read_bytes(), totals_before)
            self.assertEqual(regions_path.read_bytes(), regions_before)
            self.assertEqual(outputs.markdown.name, "dexa-analysis-2026-08-21.md")
            self.assertTrue(outputs.markdown.is_file())
            self.assertTrue(outputs.composition_chart.is_file())
            self.assertTrue(outputs.lean_mass_chart.is_file())


if __name__ == "__main__":
    unittest.main()
