import unittest
from datetime import date, datetime

from analysis_utils import calculate_workout_streaks


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


if __name__ == "__main__":
    unittest.main()
