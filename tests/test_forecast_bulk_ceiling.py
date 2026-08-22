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
    CONSERVATIVE_MEASUREMENT_ERROR_PP,
    DEFAULT_MEASUREMENT_ERROR_PP,
    DEFAULT_RESAMPLE_UNIT,
    MINIMUM_BULK_INTERVALS,
    MINIMUM_INTERVAL_GAIN_LB,
    PLANNING_WEIGHT_TOLERANCE_LB,
    PREDICTION_COVERAGE_INNER,
    PROBABILITY_CURVE_COLUMNS,
    RESAMPLE_UNIT_BLOCK,
    RESAMPLE_UNIT_INTERVAL,
    SAFETY_CONFIDENCE,
    ForecastAssumptions,
    PlanningInputs,
    WeightEstimate,
    build_planning_outlook,
    constant_ffm_ceiling_lb,
    crossing_weight_lb,
    deconvolved_lean_fraction_sd,
    extract_bulk_intervals,
    forecast_bulk_ceiling,
    group_intervals_into_blocks,
    leave_one_bulk_out_score,
    measurement_implied_lean_fraction_sd,
    modeled_body_fat_pct,
    probability_curve_frame,
    probability_under_target,
    safety_ceiling_lb,
    simulate_body_fat_readings,
    simulate_crossing_weights,
    smoothed_bodyweight_lb,
)
from dexa.forecast_pipeline import planning_from_weight_log, run_forecast_report
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


# Three rising scans in a row make two intervals that meet at the middle scan,
# so those two share that scan's measurement error.
SHARED_SCAN_ROWS = [
    ("2022-01-01", 190.0, 178.0),
    ("2022-06-01", 210.0, 184.0),
    ("2022-12-01", 196.0, 180.0),
    ("2023-04-01", 216.0, 185.0),
    ("2023-09-01", 226.0, 190.0),
    ("2024-02-01", 210.0, 184.0),
    ("2024-08-01", 230.0, 192.0),
]


def shared_scan_totals() -> pd.DataFrame:
    return totals_frame(SHARED_SCAN_ROWS)


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

        self.assertEqual(first.safety_ceiling, second.safety_ceiling)
        self.assertEqual(first.median_crossing, second.median_crossing)
        self.assertEqual(first.prediction_low_95, second.prediction_low_95)
        self.assertEqual(first.prediction_low_80, second.prediction_low_80)
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

        self.assertGreater(
            forecast.median_crossing.raw_lb, forecast.safety_ceiling.raw_lb
        )


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
        self.assertAlmostEqual(self.forecast.safety_ceiling.raw_lb, expected)

    def test_ninety_five_percent_of_paths_are_still_under_at_the_ceiling(self):
        share = float(
            np.mean(
                self.forecast.draws.crossing_weight_lb
                > self.forecast.safety_ceiling.raw_lb
            )
        )
        self.assertAlmostEqual(share, SAFETY_CONFIDENCE, places=2)

    def test_one_sided_ceiling_is_less_strict_than_the_two_sided_lower_end(self):
        # The two-sided 95% interval starts at the 2.5% quantile, which is a
        # 97.5% one-sided guarantee. Conflating them costs real pounds.
        self.assertGreater(
            self.forecast.safety_ceiling.raw_lb, self.forecast.prediction_low_95.raw_lb
        )
        self.assertLess(
            self.forecast.safety_ceiling.raw_lb, self.forecast.median_crossing.raw_lb
        )

    def test_eighty_percent_interval_sits_inside_the_ninety_five(self):
        self.assertGreater(
            self.forecast.prediction_low_80.raw_lb,
            self.forecast.prediction_low_95.raw_lb,
        )
        self.assertLess(
            self.forecast.prediction_high_80.raw_lb,
            self.forecast.prediction_high_95.raw_lb,
        )

    def test_eighty_percent_lower_end_is_looser_than_the_safety_ceiling(self):
        # The 10% quantile is a 90% one-sided guarantee, weaker than 95%.
        self.assertGreater(
            self.forecast.prediction_low_80.raw_lb,
            self.forecast.safety_ceiling.raw_lb,
        )

    def test_constant_ffm_reference_is_below_the_median_crossing(self):
        self.assertLess(
            self.forecast.constant_ffm_ceiling_lb,
            self.forecast.median_crossing.raw_lb,
        )

    def test_constant_ffm_reference_is_strictest_when_the_anchor_is_lean(self):
        lean = forecast_bulk_ceiling(lean_anchor_totals(), fast_assumptions())

        self.assertLess(lean.constant_ffm_ceiling_lb, lean.prediction_low_95.raw_lb)
        self.assertLess(lean.constant_ffm_ceiling_lb, lean.safety_ceiling.raw_lb)

    def test_constant_ffm_reference_can_exceed_the_safety_ceiling(self):
        # Near the target, scan error on the current reading alone can push the
        # modeled ceiling below the zero-gain calculation. It takes the
        # conservative error setting to surface on this fixture, but the report
        # has to describe the ordering it found rather than assume one.
        near_target = forecast_bulk_ceiling(
            five_interval_totals(),
            fast_assumptions(measurement_error_pp=CONSERVATIVE_MEASUREMENT_ERROR_PP),
        )

        self.assertGreater(
            near_target.constant_ffm_ceiling_lb, near_target.safety_ceiling.raw_lb
        )

    def test_probability_curve_falls_monotonically(self):
        curve = self.forecast.probability_under_target
        self.assertTrue(np.all(np.diff(curve) <= 1e-12))
        self.assertAlmostEqual(curve[0], float(curve.max()))
        self.assertTrue(np.all((curve >= 0.0) & (curve <= 1.0)))

    def test_the_curve_starts_below_one_when_scan_error_can_already_cross(self):
        # The fixture's latest scan reads 17.5%, only 2.5 pp under target, so a
        # conservative 0.8 pp of assumed scan error puts a few paths over on day
        # one. At the DXA-specific default it does not.
        noisy = forecast_bulk_ceiling(
            five_interval_totals(),
            fast_assumptions(measurement_error_pp=CONSERVATIVE_MEASUREMENT_ERROR_PP),
        )
        self.assertLess(noisy.probability_under_target[0], 1.0)

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
            stricter.safety_ceiling.raw_lb, self.forecast.safety_ceiling.raw_lb
        )

    def test_more_assumed_scan_error_lowers_the_ceiling(self):
        noisier = forecast_bulk_ceiling(
            five_interval_totals(),
            fast_assumptions(measurement_error_pp=CONSERVATIVE_MEASUREMENT_ERROR_PP),
        )
        self.assertLess(
            noisier.safety_ceiling.raw_lb, self.forecast.safety_ceiling.raw_lb
        )

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
        self.assertEqual(len(forecast.jackknife.safety_ceiling), 5)
        self.assertGreater(forecast.jackknife.lean_fraction_spread, 0.0)

    def test_sensitivity_refits_can_be_skipped(self):
        forecast = forecast_bulk_ceiling(
            five_interval_totals(),
            fast_assumptions(),
            with_sensitivity=False,
            with_predictive_score=False,
        )

        self.assertIsNone(forecast.jackknife)
        self.assertIsNone(forecast.sensitivity)
        self.assertIsNone(forecast.predictive_score)

    def test_switching_off_the_future_bulk_term_raises_the_ceiling(self):
        forecast = forecast_bulk_ceiling(five_interval_totals(), fast_assumptions())

        self.assertGreater(
            forecast.sensitivity.zero_partition_noise.raw_lb,
            forecast.safety_ceiling.raw_lb,
        )
        self.assertGreater(
            forecast.sensitivity.zero_measurement_error.raw_lb,
            forecast.safety_ceiling.raw_lb,
        )

    def test_measurement_implied_spread_uses_the_typical_interval(self):
        intervals, _ = extract_bulk_intervals(five_interval_totals())

        implied = measurement_implied_lean_fraction_sd(214.8, intervals, 0.38)

        # sqrt(2) * (214.8 * 0.0038) / median gain of 20 lb.
        self.assertAlmostEqual(implied, np.sqrt(2.0) * 0.81624 / 20.0, places=6)

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

    def test_body_fat_bands_nest_around_the_median(self):
        frame = probability_curve_frame(self.forecast)

        self.assertTrue(
            (frame["body_fat_pct_p2_5"] <= frame["body_fat_pct_p10"]).all()
        )
        self.assertTrue(
            (frame["body_fat_pct_p10"] <= frame["body_fat_pct_median"]).all()
        )
        self.assertTrue(
            (frame["body_fat_pct_median"] <= frame["body_fat_pct_p90"]).all()
        )
        self.assertTrue(
            (frame["body_fat_pct_p90"] <= frame["body_fat_pct_p97_5"]).all()
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
        self.assertIn("Two-sided 80% prediction interval", markdown)
        self.assertIn("## Held-out predictive check", markdown)
        self.assertIn("## Planning", markdown)
        self.assertIn("Velasquez", markdown)
        self.assertIn("## Assumptions", markdown)
        self.assertIn("Population priors", markdown)
        self.assertIn("Extrapolation cap", markdown)
        self.assertIn("## Limits", markdown)
        self.assertIn("probabilities are not calibrated", markdown)
        self.assertIn(self.forecast.safety_ceiling.describe(), markdown)

    def test_report_states_where_the_constant_ffm_reference_landed(self):
        near_target = render_markdown(
            forecast_bulk_ceiling(
                five_interval_totals(),
                fast_assumptions(
                    measurement_error_pp=CONSERVATIVE_MEASUREMENT_ERROR_PP
                ),
            )
        )
        lean = render_markdown(
            forecast_bulk_ceiling(lean_anchor_totals(), fast_assumptions())
        )

        self.assertIn("lands above the 95% safety ceiling", near_target)
        self.assertIn("Take the lower of the two.", near_target)
        self.assertIn("strictest of the three figures", lean)
        self.assertNotIn("lands above the 95% safety ceiling", lean)

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
        self.assertEqual(args.measurement_error_pp, DEFAULT_MEASUREMENT_ERROR_PP)
        self.assertEqual(args.measurement_error_pp, 0.38)
        self.assertEqual(args.partition_noise_scale, 1.0)
        self.assertEqual(args.resample_unit, DEFAULT_RESAMPLE_UNIT)
        self.assertIsNone(args.max_weight_lb)
        self.assertIsNone(args.current_bodyweight_lb)
        self.assertIsNone(args.weekly_bulk_rate_lb)
        self.assertIsNone(args.weight_log)

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
                "--resample-unit",
                "interval",
                "--current-bodyweight-lb",
                "222",
                "--weekly-bulk-rate-lb",
                "0.75",
            ]
        )

        self.assertEqual(args.target_body_fat_pct, 18.0)
        self.assertEqual(args.simulations, 500)
        self.assertEqual(args.seed, 3)
        self.assertEqual(args.measurement_error_pp, 0.5)
        self.assertEqual(args.partition_noise_scale, 0.0)
        self.assertEqual(args.max_weight_lb, 250.0)
        self.assertEqual(args.resample_unit, "interval")
        self.assertEqual(args.current_bodyweight_lb, 222.0)
        self.assertEqual(args.weekly_bulk_rate_lb, 0.75)

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
            self.assertIn("Two-sided 80% prediction interval", printed_text)
            self.assertIn("Held-out check", printed_text)
            self.assertIn("Planning from", printed_text)
            self.assertEqual(len(list(output_dir.iterdir())), 3)
            self.assertEqual(totals_path.parent.stat().st_nlink, root.stat().st_nlink)


class CensoringTest(unittest.TestCase):
    """A cap must never turn an unidentified figure into an exact headline."""

    def low_cap_forecast(self):
        return forecast_bulk_ceiling(
            lean_anchor_totals(), fast_assumptions(max_weight_lb=230.0)
        )

    def test_quantiles_above_the_cap_are_reported_as_censored(self):
        forecast = self.low_cap_forecast()

        for name, estimate in (
            ("safety ceiling", forecast.safety_ceiling),
            ("median", forecast.median_crossing),
            ("95% low", forecast.prediction_low_95),
            ("95% high", forecast.prediction_high_95),
            ("80% low", forecast.prediction_low_80),
            ("80% high", forecast.prediction_high_80),
        ):
            with self.subTest(figure=name):
                self.assertTrue(estimate.censored)
                self.assertIsNone(estimate.value_lb)
                self.assertGreater(estimate.raw_lb, 230.0)

    def test_raw_values_are_kept_not_clamped(self):
        uncapped = forecast_bulk_ceiling(lean_anchor_totals(), fast_assumptions())
        capped = self.low_cap_forecast()

        # The cap changes what is reportable, never the underlying draw.
        self.assertAlmostEqual(
            capped.safety_ceiling.raw_lb, uncapped.safety_ceiling.raw_lb
        )
        self.assertAlmostEqual(
            capped.median_crossing.raw_lb, uncapped.median_crossing.raw_lb
        )

    def test_no_false_exact_headline_reaches_the_report(self):
        forecast = self.low_cap_forecast()
        markdown = render_markdown(forecast)

        self.assertIn("above 230.0 lb", markdown)
        # The bare cap must never appear as if it were the answer itself.
        self.assertNotIn("| **230.0 lb** |", markdown)
        self.assertNotIn("safety ceiling | **230.0 lb**", markdown)
        self.assertIn("never clamped to the cap", markdown)

    def test_probability_at_the_cap_is_still_reported(self):
        forecast = self.low_cap_forecast()

        self.assertGreaterEqual(forecast.probability_at_cap, 0.0)
        self.assertLessEqual(forecast.probability_at_cap, 1.0)
        self.assertIn("At the cap itself", render_markdown(forecast))

    def test_identified_figures_describe_themselves_exactly(self):
        estimate = WeightEstimate(241.37, 274.8)

        self.assertTrue(estimate.identified)
        self.assertEqual(estimate.describe(), "241.4 lb")
        self.assertEqual(estimate.describe_short(), "241.4 lb")
        self.assertAlmostEqual(estimate.value_lb, 241.37)

    def test_unreachable_figures_say_so(self):
        estimate = WeightEstimate(float("inf"), 274.8)

        self.assertTrue(estimate.censored)
        self.assertTrue(estimate.unreachable)
        self.assertIn("not identified below 274.8 lb", estimate.describe())

    def test_planning_reports_no_headroom_when_the_ceiling_is_censored(self):
        forecast = self.low_cap_forecast()

        self.assertIsNone(forecast.planning.headroom_lb)
        self.assertIsNone(forecast.planning.weeks_to_ceiling)
        self.assertIn("not identified", forecast.planning.unavailable_reason)


class BlockResamplingTest(unittest.TestCase):
    def test_intervals_meeting_at_a_scan_form_one_block(self):
        intervals, _ = extract_bulk_intervals(shared_scan_totals())
        blocks = group_intervals_into_blocks(intervals)

        # Intervals 2 and 3 both touch the 2023-04-01 scan.
        self.assertEqual(len(intervals), 4)
        self.assertEqual(blocks, ((0,), (1, 2), (3,)))

    def test_intervals_separated_by_cuts_stay_independent(self):
        intervals, _ = extract_bulk_intervals(five_interval_totals())

        self.assertEqual(
            group_intervals_into_blocks(intervals), ((0,), (1,), (2,), (3,), (4,))
        )

    def test_forecast_reports_the_effective_sample_size(self):
        forecast = forecast_bulk_ceiling(shared_scan_totals(), fast_assumptions())

        self.assertEqual(forecast.interval_count, 4)
        self.assertEqual(forecast.resampling_unit_count, 3)
        self.assertTrue(forecast.has_shared_endpoints)

    def test_report_names_shared_endpoint_dependence(self):
        markdown = render_markdown(
            forecast_bulk_ceiling(shared_scan_totals(), fast_assumptions())
        )

        self.assertIn("Intervals share scans", markdown)
        self.assertIn("effective sample size is 3, not 4", markdown)
        self.assertIn("some neighbouring bulks share a scan", markdown)

    def test_report_does_not_claim_sharing_when_intervals_are_independent(self):
        markdown = render_markdown(
            forecast_bulk_ceiling(five_interval_totals(), fast_assumptions())
        )

        self.assertIn("No two intervals share a scan", markdown)
        self.assertIn("the folds are at least independent of each other", markdown)
        self.assertNotIn("Intervals share scans", markdown)
        self.assertNotIn("neighbouring bulks share a scan", markdown)

    def test_interval_unit_treats_every_interval_as_independent(self):
        intervals, _ = extract_bulk_intervals(shared_scan_totals())
        blocks = group_intervals_into_blocks(intervals)

        with_blocks = simulate_crossing_weights(
            current_weight_lb=230.0,
            current_fat_free_mass_lb=192.0,
            lean_fractions=np.array([i.lean_fraction for i in intervals]),
            target_body_fat_pct=20.0,
            simulations=3000,
            seed=5,
            measurement_error_pp=0.38,
            partition_noise_scale=1.0,
            blocks=blocks,
        )
        without = simulate_crossing_weights(
            current_weight_lb=230.0,
            current_fat_free_mass_lb=192.0,
            lean_fractions=np.array([i.lean_fraction for i in intervals]),
            target_body_fat_pct=20.0,
            simulations=3000,
            seed=5,
            measurement_error_pp=0.38,
            partition_noise_scale=1.0,
            blocks=None,
        )

        self.assertFalse(
            np.array_equal(with_blocks.crossing_weight_lb, without.crossing_weight_lb)
        )

    def test_unknown_resample_unit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "resample unit must be one of"):
            forecast_bulk_ceiling(
                five_interval_totals(), fast_assumptions(resample_unit="scan")
            )


class MeasurementErrorDefaultTest(unittest.TestCase):
    def test_default_is_the_dxa_specific_figure(self):
        self.assertEqual(DEFAULT_MEASUREMENT_ERROR_PP, 0.38)
        self.assertEqual(CONSERVATIVE_MEASUREMENT_ERROR_PP, 0.8)
        self.assertEqual(
            ForecastAssumptions().measurement_error_pp, DEFAULT_MEASUREMENT_ERROR_PP
        )

    def test_observed_spread_survives_removing_scan_noise_at_the_default(self):
        forecast = forecast_bulk_ceiling(five_interval_totals(), fast_assumptions())

        self.assertLess(
            forecast.measurement_implied_lean_fraction_sd, forecast.lean_fraction_sd
        )
        self.assertIsNotNone(forecast.deconvolved_lean_fraction_sd)
        self.assertGreater(forecast.deconvolved_lean_fraction_sd, 0.0)

    def test_report_does_not_claim_the_spread_is_all_noise(self):
        markdown = render_markdown(
            forecast_bulk_ceiling(five_interval_totals(), fast_assumptions())
        )

        self.assertIn("Real interval-to-interval variation", markdown)
        self.assertNotIn("consistent with pure scan noise", markdown)
        self.assertNotIn("no evidence in this record", markdown)

    def test_deconvolution_returns_none_when_noise_exceeds_the_spread(self):
        self.assertIsNone(deconvolved_lean_fraction_sd(0.10, 0.20))
        self.assertAlmostEqual(
            deconvolved_lean_fraction_sd(0.13, 0.05), np.sqrt(0.13**2 - 0.05**2)
        )

    def test_sources_name_the_right_authors_and_scope(self):
        markdown = render_markdown(
            forecast_bulk_ceiling(five_interval_totals(), fast_assumptions())
        )

        self.assertIn("Velasquez et al. 2026", markdown)
        self.assertNotIn("Ober", markdown)
        self.assertIn("bioimpedance, not DXA", markdown)


class HeldOutPredictiveScoreTest(unittest.TestCase):
    def setUp(self):
        self.forecast = forecast_bulk_ceiling(
            five_interval_totals(), fast_assumptions()
        )
        self.score = self.forecast.predictive_score

    def test_every_bulk_is_held_out_once(self):
        intervals, _ = extract_bulk_intervals(five_interval_totals())

        self.assertEqual(len(self.score.folds), len(intervals))
        self.assertEqual(
            [fold.interval_label for fold in self.score.folds],
            [interval.label for interval in intervals],
        )

    def test_each_fold_trains_on_the_other_bulks_only(self):
        for fold in self.score.folds:
            with self.subTest(fold=fold.interval_label):
                self.assertEqual(fold.training_intervals, 4)

    def test_each_fold_predicts_at_the_held_out_bulks_actual_end_weight(self):
        intervals, _ = extract_bulk_intervals(five_interval_totals())

        for fold, interval in zip(self.score.folds, intervals):
            with self.subTest(fold=fold.interval_label):
                self.assertAlmostEqual(
                    fold.anchor_weight_lb, interval.start_weight_lb
                )
                self.assertAlmostEqual(
                    fold.target_weight_lb, interval.end_weight_lb
                )
                self.assertAlmostEqual(
                    fold.observed_body_fat_pct, interval.end_body_fat_pct
                )

    def test_coverage_flags_follow_the_predicted_ranges(self):
        for fold in self.score.folds:
            with self.subTest(fold=fold.interval_label):
                self.assertEqual(
                    fold.inside_80,
                    fold.predicted_low_80_pct
                    <= fold.observed_body_fat_pct
                    <= fold.predicted_high_80_pct,
                )
                self.assertLessEqual(fold.predicted_low_95_pct, fold.predicted_low_80_pct)
                self.assertGreaterEqual(
                    fold.predicted_high_95_pct, fold.predicted_high_80_pct
                )
                self.assertTrue(0.0 <= fold.observed_percentile <= 1.0)

    def test_coverage_is_a_share_of_folds(self):
        expected_80 = np.mean([fold.inside_80 for fold in self.score.folds])

        self.assertAlmostEqual(self.score.coverage_80, float(expected_80))
        self.assertGreaterEqual(self.score.coverage_95, self.score.coverage_80)
        self.assertGreater(self.score.median_absolute_error_pp, 0.0)

    def test_the_score_is_reproducible_and_distinct_per_fold(self):
        intervals, _ = extract_bulk_intervals(five_interval_totals())
        first = leave_one_bulk_out_score(intervals, fast_assumptions())
        second = leave_one_bulk_out_score(intervals, fast_assumptions())

        self.assertEqual(first, second)
        medians = [fold.predicted_median_pct for fold in first.folds]
        self.assertEqual(len(set(medians)), len(medians))

    def test_a_held_out_score_needs_the_interval_minimum(self):
        intervals, _ = extract_bulk_intervals(five_interval_totals())

        with self.assertRaisesRegex(ValueError, "at least 3 intervals"):
            leave_one_bulk_out_score(intervals[:2], fast_assumptions())

    def test_report_interpolates_the_actual_fold_counts(self):
        five_fold = render_markdown(self.forecast)
        four_fold = render_markdown(
            forecast_bulk_ceiling(shared_scan_totals(), fast_assumptions())
        )

        self.assertIn("across 5 folds", five_fold)
        self.assertIn("5 folds cannot validate", five_fold)
        self.assertIn("of 5 inside the 95% band", five_fold)
        self.assertIn("across 4 folds", four_fold)
        self.assertIn("4 folds cannot validate", four_fold)
        self.assertIn("of 4 inside the 95% band", four_fold)
        for markdown in (five_fold, four_fold):
            self.assertNotIn("five of five", markdown)

    def test_report_separates_the_held_out_check_from_refit_sensitivity(self):
        markdown = render_markdown(self.forecast)

        self.assertIn("## Held-out predictive check", markdown)
        self.assertIn("## Leave-one-out refit sensitivity", markdown)
        self.assertIn("This is not validation.", markdown)
        self.assertIn("Unlike a refit, this can be wrong.", markdown)
        self.assertNotIn("Not backtested", markdown)

    def test_body_fat_reading_simulation_rejects_a_nonpositive_weight(self):
        with self.assertRaisesRegex(ValueError, "target weight must be positive"):
            simulate_body_fat_readings(
                anchor_weight_lb=200.0,
                anchor_fat_free_mass_lb=170.0,
                lean_fractions=np.array([0.3, 0.4, 0.5]),
                target_weight_lb=0.0,
                simulations=100,
                seed=1,
                measurement_error_pp=0.38,
                partition_noise_scale=1.0,
            )


class PlanningInputTest(unittest.TestCase):
    def test_without_inputs_the_scan_weight_is_used_and_labelled(self):
        forecast = forecast_bulk_ceiling(lean_anchor_totals(), fast_assumptions())
        plan = forecast.planning

        self.assertTrue(plan.is_scan_fallback)
        self.assertAlmostEqual(
            plan.current_bodyweight_lb, forecast.current_weight_lb
        )
        self.assertIn("latest DEXA scan weight", plan.bodyweight_source)
        self.assertIsNone(plan.weeks_to_ceiling)
        self.assertIn("no weekly bulk rate", plan.unavailable_reason)

    def test_a_supplied_weight_moves_only_the_headroom(self):
        totals = lean_anchor_totals()
        baseline = forecast_bulk_ceiling(totals, fast_assumptions())
        planned = forecast_bulk_ceiling(
            totals,
            fast_assumptions(),
            PlanningInputs(current_bodyweight_lb=233.0),
        )

        self.assertEqual(baseline.safety_ceiling, planned.safety_ceiling)
        self.assertAlmostEqual(planned.planning.current_bodyweight_lb, 233.0)
        self.assertAlmostEqual(
            planned.planning.headroom_lb,
            planned.safety_ceiling.raw_lb - 233.0,
        )
        self.assertFalse(planned.planning.is_scan_fallback)

    def test_a_rate_turns_headroom_into_weeks(self):
        forecast = forecast_bulk_ceiling(
            lean_anchor_totals(),
            fast_assumptions(),
            PlanningInputs(current_bodyweight_lb=230.0, weekly_bulk_rate_lb=0.5),
        )
        plan = forecast.planning

        self.assertAlmostEqual(plan.weeks_to_ceiling, plan.headroom_lb / 0.5)
        self.assertIsNone(plan.unavailable_reason)

    def test_no_rate_means_no_duration(self):
        forecast = forecast_bulk_ceiling(
            lean_anchor_totals(),
            fast_assumptions(),
            PlanningInputs(current_bodyweight_lb=230.0),
        )

        self.assertIsNotNone(forecast.planning.headroom_lb)
        self.assertIsNone(forecast.planning.weeks_to_ceiling)

    def test_a_weight_already_past_the_ceiling_reports_zero_weeks(self):
        outlook = build_planning_outlook(
            PlanningInputs(current_bodyweight_lb=236.0, weekly_bulk_rate_lb=0.5),
            scan_weight_lb=234.0,
            scan_fat_free_mass_lb=195.0,
            safety_ceiling=WeightEstimate(233.0, 290.0),
        )

        self.assertLess(outlook.headroom_lb, 0.0)
        self.assertEqual(outlook.weeks_to_ceiling, 0.0)
        self.assertIsNone(outlook.unavailable_reason)

    def test_a_nonpositive_rate_is_rejected(self):
        for rate in (0.0, -0.5):
            with self.subTest(rate=rate):
                with self.assertRaisesRegex(ValueError, "positive number of pounds"):
                    forecast_bulk_ceiling(
                        lean_anchor_totals(),
                        fast_assumptions(),
                        PlanningInputs(weekly_bulk_rate_lb=rate),
                    )

    def test_a_nonsense_current_weight_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "positive number"):
            forecast_bulk_ceiling(
                lean_anchor_totals(),
                fast_assumptions(),
                PlanningInputs(current_bodyweight_lb=-5.0),
            )

    def test_a_weight_below_measured_fat_free_mass_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not physically possible"):
            build_planning_outlook(
                PlanningInputs(current_bodyweight_lb=180.0),
                scan_weight_lb=200.0,
                scan_fat_free_mass_lb=185.0,
                safety_ceiling=WeightEstimate(230.0, 260.0),
            )

    def test_a_weight_far_from_the_anchoring_scan_is_rejected(self):
        far = 228.0 + PLANNING_WEIGHT_TOLERANCE_LB + 1.0

        with self.assertRaisesRegex(ValueError, "beyond the .* tolerance"):
            forecast_bulk_ceiling(
                lean_anchor_totals(),
                fast_assumptions(),
                PlanningInputs(current_bodyweight_lb=far),
            )

    def test_report_labels_the_planning_source(self):
        fallback = render_markdown(
            forecast_bulk_ceiling(lean_anchor_totals(), fast_assumptions())
        )
        supplied = render_markdown(
            forecast_bulk_ceiling(
                lean_anchor_totals(),
                fast_assumptions(),
                PlanningInputs(
                    current_bodyweight_lb=230.0, weekly_bulk_rate_lb=0.5
                ),
            )
        )

        self.assertIn("latest DEXA scan weight (no current bodyweight supplied)", fallback)
        self.assertIn("Weeks to the safety ceiling | unavailable", fallback)
        self.assertIn("supplied on the command line", supplied)
        self.assertIn("0.50 lb/week", supplied)


class WeightLogTest(unittest.TestCase):
    def weight_log_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Week of": pd.to_datetime(
                    [
                        "2026-06-01",
                        "2026-06-08",
                        "2026-06-15",
                        "2026-06-22",
                        "2026-06-29",
                        "2026-07-06",
                    ]
                ),
                "Average": [210.0, 211.0, 0.0, 213.0, 214.0, 215.0],
            }
        )

    def test_smoothing_averages_the_most_recent_valid_weeks(self):
        smoothed = smoothed_bodyweight_lb(self.weight_log_frame(), weeks=3)

        self.assertAlmostEqual(smoothed, (213.0 + 214.0 + 215.0) / 3.0)

    def test_zero_and_missing_weeks_are_dropped(self):
        smoothed = smoothed_bodyweight_lb(self.weight_log_frame(), weeks=6)

        self.assertAlmostEqual(
            smoothed, (210.0 + 211.0 + 213.0 + 214.0 + 215.0) / 5.0
        )

    def test_missing_columns_are_reported(self):
        with self.assertRaisesRegex(ValueError, "Average"):
            smoothed_bodyweight_lb(pd.DataFrame({"Week of": []}))

    def test_an_empty_log_is_rejected(self):
        empty = pd.DataFrame({"Week of": ["2026-06-01"], "Average": [0.0]})

        with self.assertRaisesRegex(ValueError, "no usable weekly averages"):
            smoothed_bodyweight_lb(empty)

    def test_a_nonpositive_week_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "weeks must be at least 1"):
            smoothed_bodyweight_lb(self.weight_log_frame(), weeks=0)

    def test_the_loader_populates_a_weight_but_never_a_rate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "weight.csv"
            self.weight_log_frame().to_csv(path, index=False)

            planning = planning_from_weight_log(path, weeks=3)

            self.assertAlmostEqual(planning.current_bodyweight_lb, 214.0)
            self.assertIsNone(planning.weekly_bulk_rate_lb)
            self.assertIn("3-week mean", planning.bodyweight_source)
            self.assertIn("weight.csv", planning.bodyweight_source)


class GenericTextTest(unittest.TestCase):
    """Report prose must describe the run it was given, not the default run."""

    def test_simulation_note_only_claims_stability_for_the_default_count(self):
        default = render_markdown(
            forecast_bulk_ceiling(
                lean_anchor_totals(),
                ForecastAssumptions(seed=7),
                with_sensitivity=False,
                with_predictive_score=False,
            )
        )
        overridden = render_markdown(
            forecast_bulk_ceiling(lean_anchor_totals(), fast_assumptions())
        )

        self.assertIn("Checked against runs at four and ten times", default)
        self.assertIn("Overridden from the default", overridden)
        self.assertNotIn("Checked against runs", overridden)

    def test_cap_note_does_not_claim_the_default_margin_when_overridden(self):
        default = render_markdown(
            forecast_bulk_ceiling(lean_anchor_totals(), fast_assumptions())
        )
        overridden = render_markdown(
            forecast_bulk_ceiling(
                lean_anchor_totals(), fast_assumptions(max_weight_lb=250.0)
            )
        )

        self.assertIn("plus 60 lb", default)
        self.assertIn("Supplied on the command line", overridden)
        self.assertNotIn("plus 60 lb", overridden)

    def test_sparse_warning_only_fires_when_the_record_is_sparse(self):
        sparse = render_markdown(
            forecast_bulk_ceiling(lean_anchor_totals(), fast_assumptions())
        )

        self.assertIn("Sparse data warning", sparse)
        self.assertTrue(
            forecast_bulk_ceiling(lean_anchor_totals(), fast_assumptions()).is_sparse
        )

    def test_a_dense_record_drops_the_sparse_warning(self):
        rows = []
        weight, fat_free = 190.0, 170.0
        for index in range(20):
            rows.append((f"2020-{index % 12 + 1:02d}-0{index % 9 + 1}", weight, fat_free))
            if index % 2 == 0:
                weight, fat_free = weight + 8.0, fat_free + 3.0
            else:
                weight, fat_free = weight - 5.0, fat_free - 1.0
        frame = totals_frame(rows)
        frame["date"] = pd.to_datetime(
            [f"20{20 + index // 4:02d}-{(index % 4) * 3 + 1:02d}-01" for index in range(20)]
        )

        forecast = forecast_bulk_ceiling(frame, fast_assumptions())

        self.assertFalse(forecast.is_sparse)
        self.assertNotIn("Sparse data warning", render_markdown(forecast))


if __name__ == "__main__":
    unittest.main()
