import unittest

import pandas as pd

from training_program_analysis import (
    add_press_family,
    estimate_muscle_stimulus,
    prepare_set_records,
    summarize_category_window,
)


class PrepareSetRecordsTest(unittest.TestCase):
    def test_normalizes_dates_and_marks_only_positive_rep_sets(self):
        records = pd.DataFrame(
            {
                "date": ["2026-07-01 08:00:00", "bad-date", "2026-07-03"],
                "reps": [8, 10, 0],
                "weight": [225, 100, 50],
                "volume": [1800, 1000, 0],
                "one_rm": [285, 120, 0],
            }
        )

        result = prepare_set_records(records)

        self.assertEqual(result["date"].iloc[0], pd.Timestamp("2026-07-01"))
        self.assertTrue(pd.isna(result["date"].iloc[1]))
        self.assertEqual(result["week_of"].iloc[0], pd.Timestamp("2026-06-29"))
        self.assertEqual(result["is_recorded_set"].tolist(), [True, True, False])


class SummarizeCategoryWindowTest(unittest.TestCase):
    def test_reports_direct_sets_and_distinct_sessions_per_week(self):
        records = prepare_set_records(
            pd.DataFrame(
                {
                    "date": ["2026-07-01", "2026-07-01", "2026-07-05", "2026-07-08"],
                    "workout_id": [1, 1, 2, 3],
                    "category": ["Chest", "Chest", "Chest", "Chest"],
                    "reps": [8, 8, 8, 0],
                    "weight": [200, 200, 205, 0],
                    "volume": [1600, 1600, 1640, 0],
                    "one_rm": [250, 250, 256, 0],
                }
            )
        )

        result = summarize_category_window(
            records,
            start=pd.Timestamp("2026-07-01"),
            end=pd.Timestamp("2026-07-14"),
            window_weeks=2,
        ).set_index("category")

        self.assertEqual(result.loc["Chest", "direct_sets"], 3)
        self.assertEqual(result.loc["Chest", "sessions"], 2)
        self.assertEqual(result.loc["Chest", "sets_per_week"], 1.5)
        self.assertEqual(result.loc["Chest", "sessions_per_week"], 1.0)


class EstimateMuscleStimulusTest(unittest.TestCase):
    def test_pressing_counts_primary_and_fractional_secondary_stimulus(self):
        flat_bench = estimate_muscle_stimulus(
            name="Barbell Bench Press", iteration="Flat", category="Chest"
        )
        overhead = estimate_muscle_stimulus(
            name="Overhead Press", iteration="Barbell", category="Shoulders"
        )

        self.assertEqual(flat_bench, {"Chest": 1.0, "Triceps": 0.5, "Shoulders": 0.5})
        self.assertEqual(overhead, {"Shoulders": 1.0, "Triceps": 0.5})

    def test_back_pulls_add_fractional_biceps_stimulus(self):
        result = estimate_muscle_stimulus(
            name="Lat Pulldowns", iteration="Wide-grip", category="Back"
        )
        self.assertEqual(result, {"Back": 1.0, "Biceps": 0.5})

    def test_leg_exercises_split_into_auditable_subgroups(self):
        self.assertEqual(
            estimate_muscle_stimulus("Leg Extensions", "Two-legged", "Legs"),
            {"Quads": 1.0},
        )
        self.assertEqual(
            estimate_muscle_stimulus("Leg Curls", "Sitting", "Legs"),
            {"Hamstrings": 1.0},
        )
        self.assertEqual(
            estimate_muscle_stimulus("Deadlifts", "Conventional", "Legs"),
            {"Hamstrings": 1.0, "Glutes": 0.5, "Back": 0.5},
        )
        self.assertEqual(
            estimate_muscle_stimulus("Hip Abductions", "Outer", "Legs"),
            {"Glutes": 1.0},
        )


class AddPressFamilyTest(unittest.TestCase):
    def test_classifies_comparable_press_families_without_mixing_variants(self):
        records = pd.DataFrame(
            {
                "name": [
                    "Barbell Bench Press",
                    "Barbell Bench Press",
                    "Close-grip Bench Press",
                    "Overhead Press",
                    "Arnold Press",
                    "Pec Deck",
                ],
                "iteration": ["Flat", "Incline", float("nan"), "Barbell", "Seated", float("nan")],
            }
        )

        result = add_press_family(records)

        self.assertEqual(
            result["press_family"].tolist(),
            [
                "Flat barbell bench",
                "Incline barbell bench",
                "Close-grip bench",
                "Barbell overhead press",
                "Other overhead press",
                None,
            ],
        )


if __name__ == "__main__":
    unittest.main()
