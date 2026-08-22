import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
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
from dexa.charts import scan_sequence_footer
from dexa.report import render_markdown
from scripts.analyze_dexa import fit_lean_mass_trend as compatibility_trend
from scripts.analyze_dexa import main as cli_main


def totals_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-15", "2025-06-10", "2025-08-20"]),
            "weight_lb": [200.0, 220.0, 210.0],
            "lean_soft_tissue_lb": [171.0, 178.0, 175.8],
            "fat_mass_lb": [20.0, 33.0, 25.2],
            "bone_mineral_content_lb": [9.0, 9.0, 9.0],
            "body_fat_pct": [10.0, 15.0, 12.0],
            "fat_free_mass_lb": [180.0, 187.0, 184.8],
            "ffmi": [24.41, 25.36, 25.06],
            "normalized_ffmi": [24.23, 25.18, 24.88],
            "bmi": [27.12, 29.84, 28.48],
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
            ("2025-06-10", previous),
            ("2025-08-20", latest),
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


def future_totals_fixture() -> pd.DataFrame:
    totals = totals_fixture()
    future = pd.DataFrame(
        {
            "date": [pd.Timestamp("2027-01-15")],
            "weight_lb": [218.0],
            "lean_soft_tissue_lb": [181.0],
            "fat_mass_lb": [27.5],
            "bone_mineral_content_lb": [9.5],
            "body_fat_pct": [12.61],
            "fat_free_mass_lb": [190.5],
            "ffmi": [25.80],
            "normalized_ffmi": [25.60],
            "bmi": [29.60],
            "height_in": [72.0],
            "notes": ["future scan"],
        }
    )
    return pd.concat([totals, future], ignore_index=True)


def future_regions_fixture() -> pd.DataFrame:
    regions = regions_fixture()
    values = {
        "Arms": (3.8, 28.5, 1.4, 11.3),
        "Legs": (10.5, 58.0, 3.2, 14.6),
        "Trunk": (10.2, 84.4, 3.0, 10.5),
        "Android (Waist)": (1.0, 12.2, 0.2, 7.5),
        "Gynoid (Hips)": (4.8, 29.5, 1.0, 13.6),
    }
    future = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2027-01-15"),
                "region": region,
                "fat_mass_lb": measurements[0],
                "lean_soft_tissue_lb": measurements[1],
                "bone_mineral_content_lb": measurements[2],
                "body_fat_pct": measurements[3],
            }
            for region, measurements in values.items()
        ]
    )
    return pd.concat([regions, future], ignore_index=True)


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


class ChartTextTest(unittest.TestCase):
    def test_scan_sequence_footer_uses_actual_scan_count(self):
        self.assertEqual(
            scan_sequence_footer(12),
            "1 TO 12 = TIME  /  BLUE = CUT  /  RED = BULK  /  BAR = VS TREND",
        )


class AnalyzeBodyCompositionTest(unittest.TestCase):
    def test_preserves_latest_scan_calculations(self):
        analysis = analyze_body_composition(totals_fixture(), regions_fixture())

        self.assertAlmostEqual(analysis.total_loss, 10.0)
        self.assertAlmostEqual(analysis.fat_loss, 7.8)
        self.assertAlmostEqual(analysis.lean_loss, 2.2)
        self.assertAlmostEqual(analysis.fat_share, 7.8 / 10.0)
        self.assertAlmostEqual(analysis.delta["body_fat_pct"], -3.0)

        markdown = render_markdown(analysis)
        self.assertIn("Total mass fell 10.0 lb to 210.0 lb", markdown)
        self.assertIn("Fat mass fell 7.8 lb to 25.2 lb", markdown)
        self.assertIn("| FFMI | 25.36 | 25.06 | -0.30 |", markdown)

    def test_current_scan_uses_analysis_values_in_interpretation(self):
        totals = totals_fixture()
        totals.loc[totals.index[-1], "body_fat_pct"] = 12.34
        totals.loc[totals.index[-1], "ffmi"] = 26.11
        totals.loc[totals.index[-1], "normalized_ffmi"] = 25.99
        totals.loc[totals.index[-1], "bmi"] = 28.88

        analysis = analyze_body_composition(totals, regions_fixture())
        markdown = render_markdown(analysis)

        self.assertIn("current CSV value is **12.3%**", markdown)
        self.assertIn("**26.11 raw / 25.99 height-normalized**", markdown)
        self.assertIn("current value is **28.88**", markdown)

    def test_default_current_scan_omits_supplemental_claims(self):
        analysis = analyze_body_composition(totals_fixture(), regions_fixture())

        markdown = render_markdown(analysis)

        self.assertIn("Supplemental interpretation unavailable", markdown)
        supplemental_claims = [
            "**Fat distribution:**",
            "**VAT:**",
            "**Bone:**",
            "**Symmetry:**",
            "## Honest read",
            "## Practical next move",
            "BodySpec report dated",
        ]
        for claim in supplemental_claims:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, markdown)

    def test_future_scan_omits_stale_supplemental_claims(self):
        analysis = analyze_body_composition(
            future_totals_fixture(), future_regions_fixture()
        )

        markdown = render_markdown(analysis)

        self.assertIn("# DEXA analysis - 2027-01-15", markdown)
        self.assertIn("**12.0% to 12.6%**", markdown)
        self.assertIn("**25.80 raw / 25.60 height-normalized**", markdown)
        self.assertIn("**29.60**", markdown)
        self.assertIn("Supplemental interpretation unavailable", markdown)
        stale_claims = [
            "approximately the leanest",
            "exceptionally muscular",
            "**VAT:**",
            "**Bone:**",
            "**Symmetry:**",
            "The cut worked",
            "## Practical next move",
            "BodySpec report dated",
        ]
        for claim in stale_claims:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, markdown)

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

        self.assertIn("# DEXA analysis - 2025-08-20", markdown)


class ReportPipelineTest(unittest.TestCase):
    def test_cli_report_run_warns_and_does_not_modify_source_csvs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            totals_path = root / "dexa.csv"
            regions_path = root / "dexa_regions.csv"
            output_dir = root / "outputs"
            totals_fixture().to_csv(totals_path, index=False)
            regions_fixture().to_csv(regions_path, index=False)
            totals_before = totals_path.read_bytes()
            regions_before = regions_path.read_bytes()

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                cli_main(
                    [
                        "--totals",
                        str(totals_path),
                        "--regions",
                        str(regions_path),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(totals_path.read_bytes(), totals_before)
            self.assertEqual(regions_path.read_bytes(), regions_before)
            self.assertIn("may contain personal health data", stderr.getvalue())
            self.assertTrue((output_dir / "dexa-analysis-2025-08-20.md").is_file())
            self.assertTrue((output_dir / "dexa-composition-history.png").is_file())
            self.assertTrue(
                (output_dir / "dexa-lean-mass-vs-bodyweight.png").is_file()
            )


if __name__ == "__main__":
    unittest.main()
