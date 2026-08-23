import unittest
from datetime import date, datetime

import pandas as pd

from analysis_utils import (
    build_big_three_pr_history,
    build_trimmed_trailing_bodyweight,
    calculate_workout_streaks,
    mark_pareto_frontier,
)


class CalculateWorkoutStreaksTest(unittest.TestCase):
    def test_strict_streak_uses_calendar_dates_not_elapsed_hours(self):
        workout_dates = [
            datetime(2026, 7, 1, 23, 30),
            datetime(2026, 7, 2, 6, 0),
            datetime(2026, 7, 4, 5, 0),
        ]

        streaks, gaps = calculate_workout_streaks(workout_dates)

        self.assertEqual(
            [(s.start, s.end, s.calendar_days) for s in streaks],
            [
                (date(2026, 7, 1), date(2026, 7, 2), 2),
                (date(2026, 7, 4), date(2026, 7, 4), 1),
            ],
        )
        self.assertEqual(gaps[0].rest_days, 1)

    def test_one_rest_day_policy_keeps_two_day_spacing_in_one_streak(self):
        workout_dates = [date(2026, 7, 1), date(2026, 7, 3), date(2026, 7, 5)]

        streaks, gaps = calculate_workout_streaks(
            workout_dates, max_days_between_workouts=2
        )

        self.assertEqual(len(streaks), 1)
        self.assertEqual(streaks[0].calendar_days, 5)
        self.assertEqual(streaks[0].workout_days, 3)
        self.assertEqual(gaps, [])

    def test_multiple_workouts_on_one_day_do_not_inflate_workout_days(self):
        workout_dates = [
            datetime(2026, 7, 1, 7),
            datetime(2026, 7, 1, 18),
            datetime(2026, 7, 2, 7),
        ]

        streaks, _ = calculate_workout_streaks(workout_dates)

        self.assertEqual(streaks[0].workout_days, 2)
        self.assertEqual(streaks[0].workouts, 3)

    def test_empty_input_and_invalid_policy(self):
        self.assertEqual(calculate_workout_streaks([]), ([], []))
        with self.assertRaises(ValueError):
            calculate_workout_streaks([date(2026, 7, 1)], 0)


class MarkParetoFrontierTest(unittest.TestCase):
    def test_marks_only_points_not_beaten_by_an_equal_or_lighter_bodyweight(self):
        attempts = pd.DataFrame(
            {
                "bodyweight": [190.0, 200.0, 205.0, 210.0, 215.0],
                "one_rm": [400.0, 450.0, 440.0, 450.0, 470.0],
            }
        )

        result = mark_pareto_frontier(attempts)

        self.assertEqual(
            result.loc[result["is_pareto"], ["bodyweight", "one_rm"]].values.tolist(),
            [[190.0, 400.0], [200.0, 450.0], [215.0, 470.0]],
        )

    def test_keeps_tied_attempts_at_the_same_frontier_coordinate(self):
        attempts = pd.DataFrame(
            {
                "bodyweight": [190.0, 190.0, 195.0],
                "one_rm": [400.0, 400.0, 390.0],
            }
        )

        result = mark_pareto_frontier(attempts)

        self.assertEqual(result["is_pareto"].tolist(), [True, True, False])

    def test_invalid_attempts_remain_in_output_but_are_not_frontier_points(self):
        attempts = pd.DataFrame(
            {
                "bodyweight": [190.0, None, 200.0],
                "one_rm": [400.0, 500.0, None],
            }
        )

        result = mark_pareto_frontier(attempts)

        self.assertEqual(result["is_pareto"].tolist(), [True, False, False])


class BuildTrimmedTrailingBodyweightTest(unittest.TestCase):
    def test_drops_one_high_and_low_from_each_complete_seven_day_window(self):
        weights = pd.DataFrame(
            {
                "date": pd.date_range("2026-08-15", periods=7, freq="D"),
                "weight": [200.0, 201.0, 202.0, 250.0, 203.0, 204.0, 100.0],
            }
        )

        result = build_trimmed_trailing_bodyweight(weights)

        self.assertTrue(result.iloc[:6]["bodyweight"].isna().all())
        self.assertAlmostEqual(result.iloc[-1]["bodyweight"], 202.0)

    def test_averages_middle_five(self):
        daily = pd.DataFrame(
            {
                "date": pd.date_range("2026-08-15", periods=7),
                "weight": [214.0, 212.8, 215.2, 215.1, 215.6, 214.3, 210.4],
            }
        )

        result = build_trimmed_trailing_bodyweight(daily)
        latest = result.iloc[-1]

        self.assertAlmostEqual(latest["bodyweight"], 214.28)
        self.assertTrue(result.iloc[:-1]["bodyweight"].isna().all())

    def test_missing_calendar_day_invalidates_window(self):
        daily = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    [
                        "2026-08-15",
                        "2026-08-16",
                        "2026-08-17",
                        "2026-08-19",
                        "2026-08-20",
                        "2026-08-21",
                    ]
                ),
                "weight": [214.0, 212.8, 215.2, 215.6, 214.3, 210.4],
            }
        )

        result = build_trimmed_trailing_bodyweight(daily)

        self.assertTrue(result["bodyweight"].isna().all())

    def test_rejects_invalid_trim_and_missing_columns(self):
        with self.assertRaises(ValueError):
            build_trimmed_trailing_bodyweight(
                pd.DataFrame({"date": ["2026-08-21"], "weight": [210.4]}),
                window_days=7,
                trim_each_side=4,
            )
        with self.assertRaises(ValueError):
            build_trimmed_trailing_bodyweight(pd.DataFrame({"date": []}))

class BuildBigThreePrHistoryTest(unittest.TestCase):
    def setUp(self):
        self.records = pd.DataFrame(
            [
                ("2018-09-01", "Bench", 300.0, "Flat Barbell Bench Press"),
                ("2018-09-02", "Squat", 400.0, "Back Squats"),
                ("2018-09-03", "Deadlift", 450.0, "Sumo Deadlifts"),
                ("2018-09-10", "Deadlift", 440.0, "Conventional Deadlifts"),
                ("2018-10-03", "Bench", 310.0, "Flat Barbell Bench Press"),
                ("2018-10-04", "Deadlift", 460.0, "Conventional Deadlifts"),
                ("2018-10-04", "Deadlift", 455.0, "Sumo Deadlifts"),
                ("2018-10-12", "Squat", 390.0, "Back Squats"),
            ],
            columns=["date", "lift", "one_rm", "variant"],
        )
        self.weights = pd.DataFrame(
            [
                ("2018-09-24", 192.6),
                ("2018-10-01", 194.5),
            ],
            columns=["week_of", "bodyweight"],
        )

    def test_seeds_each_lift_and_combined_total_at_first_weight_week(self):
        history = build_big_three_pr_history(self.records, self.weights)
        baseline = history[history["date"] == pd.Timestamp("2018-09-24")]

        values = dict(zip(baseline["series"], baseline["one_rm"]))
        self.assertEqual(values["Bench"], 300.0)
        self.assertEqual(values["Squat"], 400.0)
        self.assertEqual(values["Deadlift"], 450.0)
        self.assertEqual(values["Combined"], 1150.0)
        self.assertTrue((baseline["bodyweight"] == 192.6).all())
        self.assertTrue((baseline["is_baseline"]).all())

    def test_emits_only_real_prs_and_uses_best_deadlift_variant(self):
        history = build_big_three_pr_history(self.records, self.weights)

        bench = history[(history["series"] == "Bench") & ~history["is_baseline"]]
        squat = history[(history["series"] == "Squat") & ~history["is_baseline"]]
        deadlift = history[(history["series"] == "Deadlift") & ~history["is_baseline"]]

        self.assertEqual(bench["one_rm"].tolist(), [310.0])
        self.assertTrue(squat.empty)
        self.assertEqual(deadlift["one_rm"].tolist(), [460.0])
        self.assertEqual(deadlift["variant"].tolist(), ["Conventional Deadlifts"])

    def test_combined_updates_on_each_component_pr_and_maps_weekly_weight(self):
        history = build_big_three_pr_history(self.records, self.weights)
        combined = history[history["series"] == "Combined"].reset_index(drop=True)

        self.assertEqual(combined["one_rm"].tolist(), [1150.0, 1160.0, 1170.0])
        self.assertEqual(
            combined["date"].dt.strftime("%Y-%m-%d").tolist(),
            ["2018-09-24", "2018-10-03", "2018-10-04"],
        )
        self.assertEqual(combined["bodyweight"].tolist(), [192.6, 194.5, 194.5])
        self.assertEqual(combined["trigger"].tolist(), ["Baseline", "Bench", "Deadlift"])

    def test_missing_weight_week_remains_missing_instead_of_being_invented(self):
        records = pd.concat(
            [
                self.records,
                pd.DataFrame(
                    [("2018-10-20", "Bench", 320.0, "Flat Barbell Bench Press")],
                    columns=self.records.columns,
                ),
            ],
            ignore_index=True,
        )
        history = build_big_three_pr_history(records, self.weights)
        event = history[
            (history["series"] == "Bench")
            & (history["date"] == pd.Timestamp("2018-10-20"))
        ].iloc[0]
        self.assertTrue(pd.isna(event["bodyweight"]))


if __name__ == "__main__":
    unittest.main()
