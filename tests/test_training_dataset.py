import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from training_dataset import (
    BODYWEIGHT_COLUMNS,
    EXERCISE_COLUMNS,
    SET_COLUMNS,
    WORKOUT_COLUMNS,
    TrainingDataset,
    load_training_dataset,
)


EXAMPLE_WLD = Path(__file__).resolve().parents[1] / "data" / "example-chappy.wld"


def wld_payload(workouts):
    """Build the smallest export payload the schema will accept."""
    return {
        "version": 1,
        "typeList": {"list": []},
        "settings": {"weightInLbs": True},
        "user": {"dateCreated": "2017-08-10 19:36", "name": "Test"},
        "workouts": workouts,
    }


def workout(date="2024-01-03 07:30", uuid="w1", exercises=(), **overrides):
    record = {
        "uuid": uuid,
        "name": "Morning Workout",
        "date": date,
        "duration": 3600,
        "dateModified": False,
        "supersets": [],
        "exercises": list(exercises),
    }
    record.update(overrides)
    return record


def exercise(name="Barbell Bench Press", iteration="Flat", sets=(), **overrides):
    record = {
        "name": name,
        "iteration": iteration,
        "category": "Chest",
        "style": "reps_weight",
        "sets": list(sets),
    }
    record.update(overrides)
    return record


class LoaderFixture(unittest.TestCase):
    def temp_dir(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def write_wld(self, payload):
        path = self.temp_dir() / "fixture.wld"
        path.write_text(json.dumps(payload))
        return path

    def load(self, payload, **kwargs):
        """Write ``payload`` to a temporary .wld file and load it."""
        return load_training_dataset(self.write_wld(payload), **kwargs)

    def write_csv(self, text):
        path = self.temp_dir() / "weight.csv"
        path.write_text(text)
        return path


class ExampleExportTest(unittest.TestCase):
    """The committed example export must load through the public interface."""

    @classmethod
    def setUpClass(cls):
        if not EXAMPLE_WLD.exists():
            raise unittest.SkipTest(f"missing example export: {EXAMPLE_WLD}")
        cls.data = load_training_dataset(EXAMPLE_WLD)

    def test_frames_use_the_documented_columns_in_order(self):
        self.assertEqual(list(self.data.workouts.columns), list(WORKOUT_COLUMNS))
        self.assertEqual(list(self.data.exercises.columns), list(EXERCISE_COLUMNS))
        self.assertEqual(list(self.data.sets.columns), list(SET_COLUMNS))
        self.assertEqual(list(self.data.bodyweight.columns), list(BODYWEIGHT_COLUMNS))
        self.assertEqual(self.data.source_path, str(EXAMPLE_WLD))

    def test_row_counts_agree_across_the_three_frames(self):
        self.assertEqual(len(self.data.sets), int(self.data.workouts["set_count"].sum()))
        self.assertEqual(
            len(self.data.sets), int(self.data.exercises["set_count"].sum())
        )
        self.assertEqual(
            len(self.data.exercises), int(self.data.workouts["exercise_count"].sum())
        )

    def test_identifiers_join_sets_to_exercises_to_workouts(self):
        self.assertTrue(
            self.data.sets["exercise_id"].isin(self.data.exercises["exercise_id"]).all()
        )
        self.assertTrue(
            self.data.exercises["workout_id"]
            .isin(self.data.workouts["workout_id"])
            .all()
        )
        self.assertEqual(
            self.data.exercises["exercise_id"].nunique(), len(self.data.exercises)
        )
        self.assertEqual(self.data.sets["set_id"].nunique(), len(self.data.sets))

    def test_rows_are_sorted_oldest_first_and_weeks_start_on_monday(self):
        self.assertTrue(self.data.workouts["date"].is_monotonic_increasing)
        self.assertTrue(self.data.sets["date"].is_monotonic_increasing)
        self.assertEqual(set(self.data.workouts["week_of"].dt.weekday.unique()), {0})

    def test_totals_match_the_nested_schema_traversal(self):
        from schema import WLD

        wld = WLD(file_path=str(EXAMPLE_WLD))
        self.assertEqual(
            float(self.data.workouts["volume"].sum()),
            float(sum(w.volume() for w in wld.workouts)),
        )
        self.assertEqual(len(self.data.workouts), len(wld.workouts))


class NormalizationTest(LoaderFixture):
    def test_parses_both_recorded_date_formats_and_derives_the_week(self):
        data = self.load(
            wld_payload(
                [
                    workout(uuid="w1", date="2024-01-03 07:30"),
                    workout(uuid="w2", date="2024-01-06 3:04 p.m."),
                ]
            )
        )

        self.assertEqual(
            list(data.workouts["date"]),
            [pd.Timestamp("2024-01-03 07:30"), pd.Timestamp("2024-01-06 15:04")],
        )
        # Both sessions fall in the week that starts Monday 2024-01-01.
        self.assertEqual(
            list(data.workouts["week_of"]),
            [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-01")],
        )

    def test_display_name_combines_iteration_and_name(self):
        data = self.load(
            wld_payload(
                [
                    workout(
                        exercises=[
                            exercise(sets=[{"reps": 5}]),
                            exercise(name="Back Squats", iteration=None, sets=[{"reps": 5}]),
                        ]
                    )
                ]
            )
        )

        self.assertEqual(
            list(data.exercises["display_name"]),
            ["Flat Barbell Bench Press", "Back Squats"],
        )
        self.assertIsNone(data.exercises["iteration"].iloc[1])
        self.assertEqual(
            list(data.sets["display_name"]),
            ["Flat Barbell Bench Press", "Back Squats"],
        )

    def test_source_set_values_are_preserved_and_aggregated(self):
        data = self.load(
            wld_payload(
                [
                    workout(
                        exercises=[
                            exercise(
                                sets=[
                                    {"reps": 5, "weight": 225, "volume": 1125, "oneRM": 253},
                                    {"reps": 3, "weight": 245.5, "volume": 736, "oneRM": 267},
                                ]
                            )
                        ]
                    )
                ]
            )
        )

        self.assertEqual(list(data.sets["reps"]), [5.0, 3.0])
        self.assertEqual(list(data.sets["weight"]), [225.0, 245.5])
        self.assertEqual(list(data.sets["set_index"]), [0, 1])
        self.assertEqual(data.exercises["best_one_rm"].iloc[0], 267.0)
        self.assertEqual(data.exercises["volume"].iloc[0], 1861.0)
        self.assertEqual(data.workouts["volume"].iloc[0], 1861.0)
        self.assertEqual(data.workouts["set_count"].iloc[0], 2)


class MissingValueTest(LoaderFixture):
    def test_unrecorded_set_fields_stay_missing(self):
        data = self.load(
            wld_payload([workout(exercises=[exercise(sets=[{"reps": 12}])])])
        )

        row = data.sets.iloc[0]
        self.assertEqual(row["reps"], 12.0)
        for column in ("weight", "one_rm", "volume", "duration_seconds", "rpe", "rir"):
            self.assertTrue(pd.isna(row[column]), column)
        self.assertIsNone(row["custom"])

    def test_aggregates_are_missing_rather_than_zero_when_nothing_was_recorded(self):
        data = self.load(
            wld_payload([workout(exercises=[exercise(sets=[{"reps": 12}, {"reps": 10}])])])
        )

        self.assertTrue(pd.isna(data.exercises["volume"].iloc[0]))
        self.assertTrue(pd.isna(data.exercises["best_one_rm"].iloc[0]))
        self.assertTrue(pd.isna(data.workouts["volume"].iloc[0]))

    def test_exercise_without_sets_keeps_its_row_and_emits_no_set_rows(self):
        data = self.load(
            wld_payload(
                [
                    workout(
                        exercises=[
                            exercise(sets=[]),
                            exercise(name="Back Squats", sets=[{"reps": 5}]),
                        ]
                    )
                ]
            )
        )

        self.assertEqual(len(data.exercises), 2)
        self.assertEqual(list(data.exercises["set_count"]), [0, 1])
        self.assertEqual(len(data.sets), 1)
        self.assertEqual(data.workouts["exercise_count"].iloc[0], 2)
        self.assertEqual(data.workouts["set_count"].iloc[0], 1)


class EdgeCaseTest(LoaderFixture):
    def test_export_without_workouts_keeps_columns_and_dtypes(self):
        empty = self.load(wld_payload([]))
        populated = self.load(
            wld_payload([workout(exercises=[exercise(sets=[{"reps": 5, "weight": 135}])])])
        )

        for name in ("workouts", "exercises", "sets"):
            empty_frame = getattr(empty, name)
            populated_frame = getattr(populated, name)
            self.assertEqual(len(empty_frame), 0, name)
            self.assertEqual(
                list(empty_frame.columns), list(populated_frame.columns), name
            )
            self.assertEqual(
                empty_frame.dtypes.to_dict(), populated_frame.dtypes.to_dict(), name
            )

    def test_export_missing_a_required_section_raises_a_readable_error(self):
        payload = wld_payload([])
        del payload["typeList"]

        with self.assertRaises(ValueError) as raised:
            self.load(payload)

        self.assertIn("typeList", str(raised.exception))

    def test_unparseable_workout_date_raises_value_error(self):
        with self.assertRaises(ValueError) as raised:
            self.load(wld_payload([workout(date="last Tuesday")]))

        self.assertIn("last Tuesday", str(raised.exception))

    def test_missing_file_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_training_dataset(self.temp_dir() / "absent.wld")

    def test_from_wld_matches_loading_the_same_file(self):
        from schema import WLD

        path = self.write_wld(
            wld_payload([workout(exercises=[exercise(sets=[{"reps": 5, "oneRM": 253}])])])
        )

        loaded = load_training_dataset(path)
        direct = TrainingDataset.from_wld(WLD(file_path=str(path)))

        pd.testing.assert_frame_equal(loaded.sets, direct.sets)
        self.assertIsNone(direct.source_path)
        self.assertIn("sets=1", repr(direct))


class BodyweightTest(LoaderFixture):
    def load_bodyweight(self, text):
        return self.load(
            wld_payload([workout()]), bodyweight_path=self.write_csv(text)
        ).bodyweight

    def test_reads_exported_headers_and_keeps_missing_weeks_missing(self):
        frame = self.load_bodyweight(
            "Week of,Average\n"
            "2024-01-01,192.6\n"
            "2024-01-08,\n"      # week with no measurement
            "2024-01-15,0\n"     # formula cell without a measurement
            "2024-01-22,-5\n"    # impossible reading
            "2024-01-29,198.25\n"
        )

        self.assertEqual(list(frame.columns), list(BODYWEIGHT_COLUMNS))
        self.assertEqual(len(frame), 5)
        self.assertEqual(frame["bodyweight"].iloc[0], 192.6)
        self.assertEqual(frame["bodyweight"].iloc[4], 198.25)
        self.assertEqual(list(frame["bodyweight"].isna()), [False, True, True, True, False])

    def test_accepts_canonical_headers_and_normalizes_order_and_duplicates(self):
        frame = self.load_bodyweight(
            "week_of,bodyweight\n"
            "2024-01-08 06:00:00,195\n"
            "2024-01-01,192.6\n"
            "2024-01-08,196\n"   # later row for the same week wins
            "not a date,200\n"   # unusable row is dropped
        )

        self.assertEqual(
            list(frame["week_of"]),
            [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-08")],
        )
        self.assertEqual(list(frame["bodyweight"]), [192.6, 196.0])

    def test_csv_without_bodyweight_columns_raises_value_error(self):
        with self.assertRaises(ValueError) as raised:
            self.load_bodyweight("date,pounds\n2024-01-01,192.6\n")

        self.assertIn("week_of", str(raised.exception))

    def test_bodyweight_is_empty_but_typed_when_no_path_is_given(self):
        data = self.load(wld_payload([workout()]))

        self.assertEqual(len(data.bodyweight), 0)
        self.assertEqual(list(data.bodyweight.columns), list(BODYWEIGHT_COLUMNS))
        self.assertEqual(data.bodyweight["week_of"].dtype, "datetime64[ns]")
        self.assertEqual(data.bodyweight["bodyweight"].dtype, "float64")


if __name__ == "__main__":
    unittest.main()
