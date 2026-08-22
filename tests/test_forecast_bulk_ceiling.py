"""Tests for the bulk-ceiling forecaster.

Every fixture here is synthetic. The real DEXA export is personal data that is
excluded from version control, so nothing in this file depends on it.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from dexa.forecast import (
    MINIMUM_BULK_INTERVALS,
    MINIMUM_INTERVAL_GAIN_LB,
    PROBABILITY_CURVE_COLUMNS,
    SAFETY_CONFIDENCE,
    ForecastAssumptions,
    constant_ffm_ceiling_lb,
    crossing_weight_lb,
    extract_bulk_intervals,
    forecast_bulk_ceiling,
    measurement_implied_lean_fraction_sd,
    modeled_body_fat_pct,
    probability_curve_frame,
    probability_under_target,
    safety_ceiling_lb,
    simulate_crossing_weights,
)
from dexa.forecast_pipeline import run_forecast_report
from dexa.forecast_report import render_markdown
from scripts.forecast_bulk_ceiling import main, parse_args


def totals_frame(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    """Build a totals frame from (date, weight, fat-free mass) triples."""
    dates, weights, fat_free = zip(*rows)
    weights = np.array(weights, dtype=float)
    fat_free = np.array(fat_free, dtype=float)
    fat = weights - fat_free
    return pd.DataFrame(
        {
            "date": pd.to_datetime(list(dates)),
            "weight_lb": weights,
            "lean_soft_tissue_lb": fat_free - 9.0,
            "fat_mass_lb": fat,
            "bone_mineral_content_lb": np.full(len(weights), 9.0),
            "body_fat_pct": 100.0 * fat / weights,
            "fat_free_mass_lb": fat_free,
            "ffmi": np.full(len(weights), 25.0),
            "normalized_ffmi": np.full(len(weights), 25.0),
            "bmi": np.full(len(weights), 29.0),
            "height_in": np.full(len(weights), 72.0),
            "notes": [""] * len(weights),
        }
    )


# Five positive-weight intervals separated by cuts, the same shape as the real
# record. Lean fractions are 0.30, 0.25, 0.50, 0.40, 0.50.
FIVE_INTERVAL_ROWS = [
    ("2022-01-01", 190.0, 168.0),
    ("2022-06-01", 210.0, 174.0),
    ("2022-12-01", 196.0, 170.0),
    ("2023-04-01", 216.0, 175.0),
    ("2023-09-01", 200.0, 172.0),
    ("2024-02-01", 220.0, 182.0),
    ("2024-08-01", 205.0, 176.0),
    ("2025-01-01", 225.0, 184.0),
    ("2025-07-01", 208.0, 178.0),
    ("2026-01-01", 228.0, 188.0),
]


def five_interval_totals() -> pd.DataFrame:
    return totals_frame(FIVE_INTERVAL_ROWS)


# The same five lean fractions, but anchored on a scan that is far from the
# target. This is the shape of the real record, where assuming zero fat-free
# gain really is the most conservative of the three headline figures.
LEAN_ANCHOR_ROWS = [
    ("2022-01-01", 190.0, 178.0),
    ("2022-06-01", 210.0, 184.0),
    ("2022-12-01", 196.0, 180.0),
    ("2023-04-01", 216.0, 185.0),
    ("2023-09-01", 200.0, 182.0),
    ("2024-02-01", 220.0, 192.0),
    ("2024-08-01", 205.0, 186.0),
    ("2025-01-01", 225.0, 194.0),
    ("2025-07-01", 208.0, 188.0),
    ("2026-01-01", 228.0, 198.0),
]


def lean_anchor_totals() -> pd.DataFrame:
    return totals_frame(LEAN_ANCHOR_ROWS)


def fast_assumptions(**overrides) -> ForecastAssumptions:
    """Small, seeded assumptions so tests stay quick and deterministic."""
    defaults = {"simulations": 4000, "seed": 7}
    defaults.update(overrides)
    return ForecastAssumptions(**defaults)


class ConstantFfmCeilingTest(unittest.TestCase):
    def test_matches_the_closed_form(self):
        # 180 lb of fat-free mass is 80% of bodyweight at 20% body fat.
        self.assertAlmostEqual(constant_ffm_ceiling_lb(180.0, 20.0), 225.0)
        self.assertAlmostEqual(constant_ffm_ceiling_lb(186.6, 20.0), 233.25)
        self.assertAlmostEqual(constant_ffm_ceiling_lb(180.0, 10.0), 200.0)

    def test_result_actually_reads_the_target(self):
        ceiling = constant_ffm_ceiling_lb(186.6, 20.0)
        body_fat_pct = 100.0 * (1.0 - 186.6 / ceiling)
        self.assertAlmostEqual(body_fat_pct, 20.0)

    def test_zero_lean_fraction_reduces_to_the_constant_ffm_case(self):
        self.assertAlmostEqual(
            crossing_weight_lb(214.8, 186.6, 0.0, 20.0),
            constant_ffm_ceiling_lb(186.6, 20.0),
        )

    def test_rejects_nonpositive_fat_free_mass(self):
        with self.assertRaises(ValueError):
            constant_ffm_ceiling_lb(0.0, 20.0)
        with self.assertRaises(ValueError):
            constant_ffm_ceiling_lb(-5.0, 20.0)


class CrossingWeightTest(unittest.TestCase):
    def test_solved_weight_reads_the_target(self):
        weight, fat_free, lean_fraction, target = 214.8, 186.6, 0.4, 20.0
        crossing = crossing_weight_lb(weight, fat_free, lean_fraction, target)
        projected_fat_free = fat_free + lean_fraction * (crossing - weight)
        self.assertAlmostEqual(
            100.0 * (1.0 - projected_fat_free / crossing), target, places=9
        )

    def test_gaining_lean_mass_raises_the_ceiling(self):
        baseline = crossing_weight_lb(214.8, 186.6, 0.0, 20.0)
        with_gain = crossing_weight_lb(214.8, 186.6, 0.4, 20.0)
        self.assertGreater(with_gain, baseline)

    def test_no_crossing_when_lean_gain_outpaces_the_target(self):
        # k >= 1 - t means body fat falls as weight rises.
        self.assertEqual(crossing_weight_lb(214.8, 186.6, 0.80, 20.0), np.inf)
        self.assertEqual(crossing_weight_lb(214.8, 186.6, 0.95, 20.0), np.inf)

    def test_returns_current_weight_when_already_at_target(self):
        # 160 lb fat-free at 200 lb is exactly 20%.
        self.assertAlmostEqual(crossing_weight_lb(200.0, 160.0, 0.4, 20.0), 200.0)
        self.assertAlmostEqual(crossing_weight_lb(200.0, 150.0, 0.4, 20.0), 200.0)

    def test_accepts_arrays_and_returns_floats_for_scalars(self):
        vectorized = crossing_weight_lb(
            214.8, 186.6, np.array([0.0, 0.4, 0.9]), 20.0
        )
        self.assertEqual(vectorized.shape, (3,))
        np.testing.assert_allclose(vectorized[0], 233.25)
        self.assertEqual(vectorized[2], np.inf)
        self.assertIsInstance(crossing_weight_lb(214.8, 186.6, 0.4, 20.0), float)


class ExtractBulkIntervalsTest(unittest.TestCase):
    def test_keeps_only_positive_weight_intervals(self):
        intervals, excluded = extract_bulk_intervals(five_interval_totals())

        self.assertEqual(len(intervals), 5)
        self.assertEqual(excluded, ())
        np.testing.assert_allclose(
            [interval.lean_fraction for interval in intervals],
            [0.30, 0.25, 0.50, 0.40, 0.50],
        )
        self.assertTrue(all(interval.weight_gain_lb > 0 for interval in intervals))

    def test_reports_gains_and_dates_per_interval(self):
        intervals, _ = extract_bulk_intervals(five_interval_totals())
        first = intervals[0]

        self.assertEqual(str(first.start_date), "2022-01-01")
        self.assertEqual(str(first.end_date), "2022-06-01")
        self.assertAlmostEqual(first.weight_gain_lb, 20.0)
        self.assertAlmostEqual(first.fat_free_gain_lb, 6.0)

    def test_sorts_by_date_before_pairing(self):
        shuffled = five_interval_totals().sort_values("weight_lb")
        intervals, _ = extract_bulk_intervals(shuffled)

        self.assertEqual(len(intervals), 5)
        self.assertEqual(str(intervals[0].start_date), "2022-01-01")

    def test_separates_gains_below_the_minimum(self):
        totals = totals_frame(
            [
                ("2024-01-01", 200.0, 170.0),
                ("2024-02-01", 201.0, 170.4),  # +1.0 lb, below the minimum
                ("2024-03-01", 215.0, 176.0),
            ]
        )

        intervals, excluded = extract_bulk_intervals(totals)

        self.assertEqual(len(intervals), 1)
        self.assertEqual(len(excluded), 1)
        self.assertLess(excluded[0].weight_gain_lb, MINIMUM_INTERVAL_GAIN_LB)

    def test_ignores_flat_and_falling_intervals(self):
        totals = totals_frame(
            [
                ("2024-01-01", 200.0, 170.0),
                ("2024-02-01", 200.0, 171.0),  # no weight change
                ("2024-03-01", 190.0, 168.0),  # a cut
            ]
        )

        intervals, excluded = extract_bulk_intervals(totals)

        self.assertEqual(intervals, ())
        self.assertEqual(excluded, ())

    def test_requires_two_scans(self):
        with self.assertRaisesRegex(ValueError, "at least two scans"):
            extract_bulk_intervals(totals_frame([("2024-01-01", 200.0, 170.0)]))

    def test_reports_missing_columns(self):
        totals = five_interval_totals().drop(columns=["fat_free_mass_lb"])

        with self.assertRaisesRegex(ValueError, "fat_free_mass_lb"):
            extract_bulk_intervals(totals)


class ReproducibilityTest(unittest.TestCase):
    def test_same_seed_reproduces_every_draw(self):
        arguments = dict(
            current_weight_lb=214.8,
            current_fat_free_mass_lb=186.6,
            lean_fractions=np.array([0.30, 0.25, 0.50, 0.40, 0.50]),
            target_body_fat_pct=20.0,
            simulations=2000,
            seed=11,
            measurement_error_pp=0.8,
            partition_noise_scale=1.0,
        )

        first = simulate_crossing_weights(**arguments)
        second = simulate_crossing_weights(**arguments)

        np.testing.assert_array_equal(
            first.crossing_weight_lb, second.crossing_weight_lb
        )
        np.testing.assert_array_equal(first.lean_fraction, second.lean_fraction)

    def test_a_different_seed_gives_different_draws(self):
        arguments = dict(
            current_weight_lb=214.8,
            current_fat_free_mass_lb=186.6,
            lean_fractions=np.array([0.30, 0.25, 0.50, 0.40, 0.50]),
            target_body_fat_pct=20.0,
            simulations=2000,
            measurement_error_pp=0.8,
            partition_noise_scale=1.0,
        )

        first = simulate_crossing_weights(seed=11, **arguments)
        second = simulate_crossing_weights(seed=12, **arguments)

        self.assertFalse(
            np.array_equal(first.crossing_weight_lb, second.crossing_weight_lb)
        )

    def test_whole_forecast_reproduces_under_a_seed(self):
        totals = five_interval_totals()

        first = forecast_bulk_ceiling(totals, fast_assumptions())
        second = forecast_bulk_ceiling(totals, fast_assumptions())

        self.assertEqual(first.safety_ceiling_lb, second.safety_ceiling_lb)
        self.assertEqual(first.median_crossing_lb, second.median_crossing_lb)
        self.assertEqual(first.prediction_low_lb, second.prediction_low_lb)
        np.testing.assert_array_equal(
            first.probability_under_target, second.probability_under_target
        )
        np.testing.assert_array_equal(
            first.body_fat_median_pct, second.body_fat_median_pct
        )

    def test_measurement_error_of_zero_still_produces_spread(self):
        # With no scan error the only remaining uncertainty is the resampled k.
        forecast = forecast_bulk_ceiling(
            five_interval_totals(), fast_assumptions(measurement_error_pp=0.0)
        )

        self.assertGreater(forecast.median_crossing_lb, forecast.safety_ceiling_lb)


class InvalidTargetTest(unittest.TestCase):
    def test_rejects_targets_outside_zero_to_one_hundred(self):
        totals = five_interval_totals()
        for target in (0.0, -3.0, 100.0, 140.0):
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError, "between 0 and 100"):
                    forecast_bulk_ceiling(
                        totals, fast_assumptions(target_body_fat_pct=target)
                    )

    def test_rejects_a_non_finite_target(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            constant_ffm_ceiling_lb(180.0, float("nan"))

    def test_rejects_a_target_at_or_below_the_current_reading(self):
        totals = five_interval_totals()
        current = totals.iloc[-1]
        current_pct = 100.0 * (
            1.0 - current["fat_free_mass_lb"] / current["weight_lb"]
        )

        with self.assertRaisesRegex(ValueError, "no bulk headroom"):
            forecast_bulk_ceiling(
                totals, fast_assumptions(target_body_fat_pct=current_pct - 1.0)
            )

    def test_rejects_a_cap_at_or_below_the_current_weight(self):
        with self.assertRaisesRegex(ValueError, "above the current scan weight"):
            forecast_bulk_ceiling(
                five_interval_totals(), fast_assumptions(max_weight_lb=100.0)
            )

    def test_rejects_nonsense_simulation_settings(self):
        with self.assertRaisesRegex(ValueError, "at least 1"):
            forecast_bulk_ceiling(
                five_interval_totals(), fast_assumptions(simulations=0)
            )
        with self.assertRaisesRegex(ValueError, "must not be negative"):
            forecast_bulk_ceiling(
                five_interval_totals(), fast_assumptions(measurement_error_pp=-1.0)
            )
        with self.assertRaisesRegex(ValueError, "grid step"):
            forecast_bulk_ceiling(
                five_interval_totals(), fast_assumptions(grid_step_lb=0.0)
            )


class TooFewIntervalsTest(unittest.TestCase):
    def test_rejects_fewer_intervals_than_the_minimum(self):
        totals = totals_frame(
            [
                ("2024-01-01", 200.0, 170.0),
                ("2024-06-01", 215.0, 176.0),
                ("2024-12-01", 205.0, 173.0),
                ("2025-06-01", 220.0, 179.0),
            ]
        )
        intervals, _ = extract_bulk_intervals(totals)
        self.assertEqual(len(intervals), 2)

        with self.assertRaisesRegex(ValueError, "at least 3 positive-weight"):
            forecast_bulk_ceiling(totals, fast_assumptions())

    def test_tiny_gains_do_not_count_toward_the_minimum(self):
        totals = totals_frame(
            [
                ("2024-01-01", 200.0, 170.0),
                ("2024-03-01", 215.0, 176.0),
                ("2024-05-01", 205.0, 173.0),
                ("2024-07-01", 220.0, 179.0),
                ("2024-09-01", 210.0, 175.0),
                ("2024-11-01", 211.0, 175.4),  # +1.0 lb, excluded
            ]
        )

        with self.assertRaisesRegex(ValueError, "found 2"):
            forecast_bulk_ceiling(totals, fast_assumptions())

    def test_the_real_record_size_still_clears_the_minimum(self):
        intervals, _ = extract_bulk_intervals(five_interval_totals())
        self.assertGreaterEqual(len(intervals), MINIMUM_BULK_INTERVALS)


class SafetyBoundSemanticsTest(unittest.TestCase):
    def setUp(self):
        self.forecast = forecast_bulk_ceiling(
            five_interval_totals(), fast_assumptions()
        )

    def test_safety_ceiling_is_the_lower_one_sided_quantile(self):
        expected = float(
            np.quantile(
                self.forecast.draws.crossing_weight_lb, 1.0 - SAFETY_CONFIDENCE
            )
        )
        self.assertAlmostEqual(self.forecast.safety_ceiling_lb, expected)

    def test_ninety_five_percent_of_paths_are_still_under_at_the_ceiling(self):
        share = float(
            np.mean(
                self.forecast.draws.crossing_weight_lb
                > self.forecast.safety_ceiling_lb
            )
        )
        self.assertAlmostEqual(share, SAFETY_CONFIDENCE, places=2)

    def test_one_sided_ceiling_is_less_strict_than_the_two_sided_lower_end(self):
        # The two-sided 95% interval starts at the 2.5% quantile, which is a
        # 97.5% one-sided guarantee. Conflating them costs real pounds.
        self.assertGreater(
            self.forecast.safety_ceiling_lb, self.forecast.prediction_low_lb
        )
        self.assertLess(
            self.forecast.safety_ceiling_lb, self.forecast.median_crossing_lb
        )

    def test_constant_ffm_reference_is_below_the_median_crossing(self):
        self.assertLess(
            self.forecast.constant_ffm_ceiling_lb, self.forecast.median_crossing_lb
        )

    def test_constant_ffm_reference_is_strictest_when_the_anchor_is_lean(self):
        lean = forecast_bulk_ceiling(lean_anchor_totals(), fast_assumptions())

        self.assertLess(lean.constant_ffm_ceiling_lb, lean.prediction_low_lb)
        self.assertLess(lean.constant_ffm_ceiling_lb, lean.safety_ceiling_lb)

    def test_constant_ffm_reference_can_exceed_the_safety_ceiling(self):
        # Near the target, scan error on the current reading alone can push the
        # modeled ceiling below the zero-gain calculation. The report has to
        # describe the ordering it found rather than assume one.
        self.assertGreater(
            self.forecast.constant_ffm_ceiling_lb, self.forecast.safety_ceiling_lb
        )

    def test_probability_curve_falls_monotonically(self):
        curve = self.forecast.probability_under_target
        self.assertTrue(np.all(np.diff(curve) <= 1e-12))
        self.assertAlmostEqual(curve[0], float(curve.max()))
        self.assertTrue(np.all((curve >= 0.0) & (curve <= 1.0)))

    def test_the_curve_starts_below_one_when_scan_error_can_already_cross(self):
        # The fixture's latest scan reads 17.5%, only 2.5 pp under target, so
        # 0.8 pp of assumed scan error puts a few paths over on day one.
        self.assertLess(self.forecast.probability_under_target[0], 1.0)

        far_from_target = forecast_bulk_ceiling(
            five_interval_totals(), fast_assumptions(target_body_fat_pct=30.0)
        )
        self.assertAlmostEqual(
            far_from_target.probability_under_target[0], 1.0, places=6
        )

    def test_probability_curve_agrees_with_the_simulated_body_fat_paths(self):
        # Two routes to the same number: counting paths that have not crossed
        # yet, and reading body fat off those paths directly.
        paths = modeled_body_fat_pct(
            self.forecast.draws,
            self.forecast.current_weight_lb,
            self.forecast.weight_grid_lb,
        )
        direct = (
            paths < self.forecast.assumptions.target_body_fat_pct
        ).mean(axis=0)

        np.testing.assert_allclose(
            direct, self.forecast.probability_under_target, atol=1e-12
        )

    def test_a_stricter_target_lowers_the_ceiling(self):
        stricter = forecast_bulk_ceiling(
            five_interval_totals(), fast_assumptions(target_body_fat_pct=18.0)
        )
        self.assertLess(
            stricter.safety_ceiling_lb, self.forecast.safety_ceiling_lb
        )

    def test_more_assumed_scan_error_lowers_the_ceiling(self):
        noisier = forecast_bulk_ceiling(
            five_interval_totals(), fast_assumptions(measurement_error_pp=1.24)
        )
        self.assertLess(noisier.safety_ceiling_lb, self.forecast.safety_ceiling_lb)

    def test_helper_rejects_a_confidence_outside_zero_to_one(self):
        crossing = self.forecast.draws.crossing_weight_lb
        for confidence in (0.0, 1.0, -0.5, 2.0):
            with self.subTest(confidence=confidence):
                with self.assertRaisesRegex(ValueError, "between 0 and 1"):
                    safety_ceiling_lb(crossing, confidence)

    def test_probability_helper_counts_uncrossed_paths(self):
        crossing = np.array([220.0, 230.0, 240.0, np.inf])
        grid = np.array([215.0, 225.0, 235.0, 245.0])

        np.testing.assert_allclose(
            probability_under_target(crossing, grid), [1.0, 0.75, 0.5, 0.25]
        )


class SensitivityTest(unittest.TestCase):
    def test_leave_one_out_refits_cover_every_interval(self):
        forecast = forecast_bulk_ceiling(five_interval_totals(), fast_assumptions())

        self.assertIsNotNone(forecast.jackknife)
        self.assertEqual(len(forecast.jackknife.dropped_label), 5)
        self.assertEqual(len(forecast.jackknife.safety_ceiling_lb), 5)
        self.assertGreater(forecast.jackknife.lean_fraction_spread, 0.0)

    def test_sensitivity_refits_can_be_skipped(self):
        forecast = forecast_bulk_ceiling(
            five_interval_totals(), fast_assumptions(), with_sensitivity=False
        )

        self.assertIsNone(forecast.jackknife)
        self.assertIsNone(forecast.sensitivity)

    def test_switching_off_the_future_bulk_term_raises_the_ceiling(self):
        forecast = forecast_bulk_ceiling(five_interval_totals(), fast_assumptions())

        self.assertGreater(
            forecast.sensitivity.zero_partition_noise_lb, forecast.safety_ceiling_lb
        )
        self.assertGreater(
            forecast.sensitivity.zero_measurement_error_lb,
            forecast.safety_ceiling_lb,
        )

    def test_measurement_implied_spread_uses_the_typical_interval(self):
        intervals, _ = extract_bulk_intervals(five_interval_totals())

        implied = measurement_implied_lean_fraction_sd(214.8, intervals, 0.8)

        # sqrt(2) * (214.8 * 0.008) / median gain of 20 lb.
        self.assertAlmostEqual(implied, np.sqrt(2.0) * 1.7184 / 20.0, places=6)

    def test_measurement_implied_spread_needs_an_interval(self):
        with self.assertRaisesRegex(ValueError, "at least one interval"):
            measurement_implied_lean_fraction_sd(214.8, (), 0.8)


class OutputSchemaTest(unittest.TestCase):
    def setUp(self):
        self.forecast = forecast_bulk_ceiling(
            five_interval_totals(), fast_assumptions()
        )

    def test_probability_curve_has_a_fixed_column_order(self):
        frame = probability_curve_frame(self.forecast)

        self.assertEqual(tuple(frame.columns), PROBABILITY_CURVE_COLUMNS)
        self.assertEqual(len(frame), len(self.forecast.weight_grid_lb))
        self.assertTrue(frame["probability_under_target"].between(0.0, 1.0).all())
        self.assertTrue(frame["weight_lb"].is_monotonic_increasing)
        self.assertFalse(frame.isna().to_numpy().any())

    def test_probability_curve_spans_the_current_weight_to_the_cap(self):
        frame = probability_curve_frame(self.forecast)

        self.assertAlmostEqual(
            frame["weight_lb"].iloc[0], self.forecast.current_weight_lb
        )
        self.assertLessEqual(
            frame["weight_lb"].iloc[-1], self.forecast.resolved_max_weight_lb + 1e-9
        )

    def test_body_fat_band_brackets_its_median(self):
        frame = probability_curve_frame(self.forecast)

        self.assertTrue(
            (frame["body_fat_pct_p2_5"] <= frame["body_fat_pct_median"]).all()
        )
        self.assertTrue(
            (frame["body_fat_pct_median"] <= frame["body_fat_pct_p97_5"]).all()
        )

    def test_report_labels_the_estimates_assumptions_and_warning(self):
        markdown = render_markdown(self.forecast)

        self.assertIn("Sparse data warning", markdown)
        self.assertIn("5 positive-weight DEXA intervals", markdown)
        self.assertIn("not medical advice", markdown)
        self.assertIn("modeled estimates, not measurements", markdown)
        self.assertIn("Constant fat-free mass reference", markdown)
        self.assertIn("One-sided 95% safety ceiling", markdown)
        self.assertIn("Two-sided 95% prediction interval", markdown)
        self.assertIn("## Assumptions", markdown)
        self.assertIn("Population priors", markdown)
        self.assertIn("Extrapolation cap", markdown)
        self.assertIn("## Limits", markdown)
        self.assertIn("Not backtested", markdown)
        self.assertIn(f"{self.forecast.safety_ceiling_lb:.1f} lb", markdown)

    def test_report_states_where_the_constant_ffm_reference_landed(self):
        near_target = render_markdown(self.forecast)
        lean = render_markdown(
            forecast_bulk_ceiling(lean_anchor_totals(), fast_assumptions())
        )

        self.assertIn("lands **above** the 95% safety ceiling", near_target)
        self.assertIn("Take the lower of the two.", near_target)
        self.assertIn("strictest of the three figures", lean)
        self.assertNotIn("lands **above**", lean)

    def test_report_names_the_chart_and_curve_files(self):
        markdown = render_markdown(
            self.forecast, chart_filename="chart.png", curve_filename="curve.csv"
        )

        self.assertIn("![Bulk ceiling forecast](chart.png)", markdown)
        self.assertIn("`curve.csv`", markdown)

    def test_forecast_and_rendering_write_nothing(self):
        totals = five_interval_totals()

        with (
            patch("builtins.open", side_effect=AssertionError("unexpected write")),
            patch.object(Path, "open", side_effect=AssertionError("unexpected write")),
            patch.object(
                Path, "write_text", side_effect=AssertionError("unexpected write")
            ),
        ):
            forecast = forecast_bulk_ceiling(totals, fast_assumptions())
            markdown = render_markdown(forecast)
            probability_curve_frame(forecast)

        self.assertIn("# Bulk ceiling forecast, 20% body fat", markdown)


class ForecastPipelineTest(unittest.TestCase):
    def test_run_writes_three_outputs_and_leaves_the_input_alone(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            totals_path = root / "dexa.csv"
            output_dir = root / "outputs"
            five_interval_totals().to_csv(totals_path, index=False)
            before = totals_path.read_bytes()

            forecast, outputs = run_forecast_report(
                totals_path, output_dir, fast_assumptions()
            )

            self.assertEqual(totals_path.read_bytes(), before)
            self.assertTrue(outputs.markdown.is_file())
            self.assertTrue(outputs.probability_curve.is_file())
            self.assertTrue(outputs.chart.is_file())
            self.assertEqual(
                outputs.markdown.name, "bulk-ceiling-20pct-2026-01-01.md"
            )
            self.assertEqual(
                outputs.probability_curve.name,
                "bulk-ceiling-20pct-probability-curve.csv",
            )
            self.assertEqual(
                outputs.chart.name, "bulk-ceiling-20pct-forecast.png"
            )

            written = pd.read_csv(outputs.probability_curve)
            self.assertEqual(tuple(written.columns), PROBABILITY_CURVE_COLUMNS)
            self.assertEqual(len(written), len(forecast.weight_grid_lb))

    def test_a_fractional_target_gets_a_filesystem_safe_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            totals_path = root / "dexa.csv"
            five_interval_totals().to_csv(totals_path, index=False)

            _, outputs = run_forecast_report(
                totals_path,
                root / "outputs",
                fast_assumptions(target_body_fat_pct=22.5),
            )

            self.assertIn("22-5pct", outputs.markdown.name)


class CommandLineTest(unittest.TestCase):
    def test_defaults_match_the_module_defaults(self):
        args = parse_args([])

        self.assertEqual(args.target_body_fat_pct, 20.0)
        self.assertEqual(args.seed, 20260821)
        self.assertEqual(args.simulations, 20000)
        self.assertEqual(args.measurement_error_pp, 0.8)
        self.assertEqual(args.partition_noise_scale, 1.0)
        self.assertIsNone(args.max_weight_lb)

    def test_every_assumption_is_overridable(self):
        args = parse_args(
            [
                "--target-body-fat-pct",
                "18",
                "--simulations",
                "500",
                "--seed",
                "3",
                "--measurement-error-pp",
                "0.5",
                "--partition-noise-scale",
                "0",
                "--max-weight-lb",
                "250",
            ]
        )

        self.assertEqual(args.target_body_fat_pct, 18.0)
        self.assertEqual(args.simulations, 500)
        self.assertEqual(args.seed, 3)
        self.assertEqual(args.measurement_error_pp, 0.5)
        self.assertEqual(args.partition_noise_scale, 0.0)
        self.assertEqual(args.max_weight_lb, 250.0)

    def test_main_writes_outputs_and_warns_about_sparse_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            totals_path = root / "dexa.csv"
            output_dir = root / "outputs"
            five_interval_totals().to_csv(totals_path, index=False)

            with patch("builtins.print") as printed:
                main(
                    [
                        "--totals",
                        str(totals_path),
                        "--output-dir",
                        str(output_dir),
                        "--simulations",
                        "2000",
                    ]
                )

            printed_text = "\n".join(
                str(call.args[0]) for call in printed.call_args_list if call.args
            )
            self.assertIn("WARNING", printed_text)
            self.assertIn("5 positive-weight DEXA intervals", printed_text)
            self.assertIn("Constant-FFM reference", printed_text)
            self.assertIn("One-sided 95% safety ceiling", printed_text)
            self.assertEqual(len(list(output_dir.iterdir())), 3)
            self.assertEqual(totals_path.parent.stat().st_nlink, root.stat().st_nlink)


if __name__ == "__main__":
    unittest.main()
