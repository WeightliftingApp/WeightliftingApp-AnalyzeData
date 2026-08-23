import ast
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import training_dataset
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


class DtypeContractTest(LoaderFixture):
    """The documented dtypes are asserted literally, not compared across frames.

    Comparing an empty frame's dtypes against a populated one only proves the
    two agree; both drifted together under pandas 3, which infers microsecond
    resolution from Python datetimes and second resolution from an empty
    column. These assertions name the dtype the documentation promises.
    """

    DATE_COLUMNS = {
        "workouts": ("date", "week_of"),
        "exercises": ("date", "week_of"),
        "sets": ("date", "week_of"),
        "bodyweight": ("week_of",),
    }
    TEXT_COLUMNS = {
        "workouts": ("workout_id", "name"),
        "exercises": ("exercise_id", "workout_id", "name", "iteration"),
        "sets": ("set_id", "exercise_id", "name", "iteration", "custom"),
    }

    def populated(self):
        return self.load(
            wld_payload(
                [
                    workout(
                        exercises=[
                            exercise(sets=[{"reps": 5, "weight": 135, "custom": "belt"}])
                        ]
                    )
                ]
            ),
            bodyweight_path=self.write_csv("Week of,Average\n2024-01-01,192.6\n"),
        )

    def assert_date_columns(self, data, label):
        for frame_name, columns in self.DATE_COLUMNS.items():
            frame = getattr(data, frame_name)
            for column in columns:
                self.assertEqual(
                    str(frame[column].dtype),
                    "datetime64[ns]",
                    f"{label} {frame_name}.{column}",
                )

    def test_populated_date_columns_are_nanosecond_datetimes(self):
        self.assert_date_columns(self.populated(), "populated")

    def test_empty_date_columns_are_nanosecond_datetimes(self):
        self.assert_date_columns(self.load(wld_payload([])), "empty")

    def test_text_columns_stay_object_when_populated_and_when_empty(self):
        for label, data in (
            ("populated", self.populated()),
            ("empty", self.load(wld_payload([]))),
        ):
            for frame_name, columns in self.TEXT_COLUMNS.items():
                frame = getattr(data, frame_name)
                for column in columns:
                    self.assertEqual(
                        str(frame[column].dtype),
                        "object",
                        f"{label} {frame_name}.{column}",
                    )

    def test_missing_text_values_are_none_and_never_nan(self):
        data = self.load(
            wld_payload(
                [
                    workout(
                        exercises=[
                            exercise(iteration=None, sets=[{"reps": 5}]),
                            exercise(sets=[{"reps": 5, "custom": "belt"}]),
                        ]
                    )
                ]
            )
        )

        self.assertIsNone(data.exercises["iteration"].iloc[0])
        self.assertIsNone(data.sets["iteration"].iloc[0])
        self.assertIsNone(data.sets["custom"].iloc[0])
        self.assertEqual(data.sets["custom"].iloc[1], "belt")
        for frame_name, columns in self.TEXT_COLUMNS.items():
            frame = getattr(data, frame_name)
            for column in columns:
                for position, value in enumerate(frame[column]):
                    self.assertTrue(
                        value is None or isinstance(value, str),
                        f"{frame_name}.{column}[{position}] is {value!r}",
                    )

    def test_numeric_columns_keep_their_documented_dtypes(self):
        for label, data in (
            ("populated", self.populated()),
            ("empty", self.load(wld_payload([]))),
        ):
            self.assertEqual(str(data.workouts["set_count"].dtype), "int64", label)
            self.assertEqual(str(data.workouts["volume"].dtype), "float64", label)
            self.assertEqual(str(data.sets["reps"].dtype), "float64", label)
            self.assertEqual(
                str(data.bodyweight["bodyweight"].dtype), "float64", label
            )


class WorkoutIdTest(LoaderFixture):
    """Exercise and set ids derive from the workout uuid, so it must be sound."""

    def test_missing_uuid_is_rejected_with_the_offending_workout(self):
        with self.assertRaises(ValueError) as raised:
            self.load(
                wld_payload(
                    [
                        workout(uuid="w1", date="2024-01-03 07:30"),
                        workout(uuid=None, date="2024-01-05 08:00"),
                    ]
                )
            )

        message = str(raised.exception)
        self.assertIn("workout 1", message)
        self.assertIn("2024-01-05 08:00", message)
        self.assertIn("uuid", message)

    def test_blank_uuid_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            self.load(wld_payload([workout(uuid="   ")]))

        self.assertIn("has no uuid", str(raised.exception))

    def test_duplicate_uuid_names_both_workouts(self):
        with self.assertRaises(ValueError) as raised:
            self.load(
                wld_payload(
                    [
                        workout(uuid="w1", date="2024-01-03 07:30"),
                        workout(uuid="w2", date="2024-01-04 07:30"),
                        workout(uuid="w1", date="2024-01-05 07:30"),
                    ]
                )
            )

        message = str(raised.exception)
        self.assertIn("'w1'", message)
        self.assertIn("workout 0", message)
        self.assertIn("workout 2", message)

    def test_from_wld_validates_ids_too(self):
        from schema import WLD

        path = self.write_wld(
            wld_payload([workout(uuid="w1"), workout(uuid="w1", date="2024-01-05 08:00")])
        )

        with self.assertRaises(ValueError):
            TrainingDataset.from_wld(WLD(file_path=str(path)))


class MalformedExportTest(LoaderFixture):
    """Malformed structure reaches the caller as a located ValueError."""

    def load_raw(self, payload):
        path = self.temp_dir() / "fixture.wld"
        path.write_text(json.dumps(payload))
        return load_training_dataset(path)

    def assert_invalid(self, payload, *expected_fragments):
        with self.assertRaises(ValueError) as raised:
            self.load_raw(payload)

        message = str(raised.exception)
        self.assertIn("is not a valid .wld export", message)
        for fragment in expected_fragments:
            self.assertIn(fragment, message)
        return message

    def test_null_top_level(self):
        self.assert_invalid(None, "expected an object at the top level", "null")

    def test_list_top_level(self):
        self.assert_invalid([{"workouts": []}], "expected an object", "a list")

    def test_null_section(self):
        payload = wld_payload([])
        payload["workouts"] = None
        self.assert_invalid(payload, "'workouts' section is null")

    def test_workouts_that_are_not_a_list(self):
        payload = wld_payload([])
        payload["workouts"] = {"w1": {}}
        self.assert_invalid(payload, "'workouts' must be a list", "an object")

    def test_settings_that_are_not_an_object(self):
        payload = wld_payload([])
        payload["settings"] = []
        self.assert_invalid(payload, "'settings' must be an object", "a list")

    def test_type_list_without_its_list_entry(self):
        payload = wld_payload([])
        payload["typeList"] = {}
        self.assert_invalid(payload, "'typeList' must be an object containing")

    def test_null_workout_entry(self):
        self.assert_invalid(
            wld_payload([workout(), None]), "workout 1 must be an object", "null"
        )

    def test_null_exercises_list(self):
        self.assert_invalid(
            wld_payload([{**workout(), "exercises": None}]),
            "workout 0 has an invalid 'exercises' value",
            "null",
        )

    def test_null_sets_list(self):
        self.assert_invalid(
            wld_payload([workout(exercises=[{**exercise(), "sets": None}])]),
            "workout 0 exercise 0 has an invalid 'sets' value",
            "null",
        )

    def test_null_set_entry(self):
        self.assert_invalid(
            wld_payload([workout(exercises=[exercise(sets=[{"reps": 5}, None])])]),
            "workout 0 exercise 0 set 1 must be an object",
            "null",
        )

    def test_file_that_is_not_json(self):
        path = self.temp_dir() / "fixture.wld"
        path.write_text("{not json")

        with self.assertRaises(ValueError) as raised:
            load_training_dataset(path)

        self.assertIn("is not a valid .wld export", str(raised.exception))


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

    def test_each_row_is_parsed_on_its_own_terms(self):
        # pandas 2 infers one format from the first row and coerces every other
        # layout in the column to NaT. Each row below uses a different layout.
        frame = self.load_bodyweight(
            "Week of,Average\n"
            "2024-01-01 06:00:00,192.6\n"
            "2024-01-08,195.1\n"
            "1/15/2024,196.4\n"
        )

        self.assertEqual(
            list(frame["week_of"]),
            [
                pd.Timestamp("2024-01-01"),
                pd.Timestamp("2024-01-08"),
                pd.Timestamp("2024-01-15"),
            ],
        )
        self.assertEqual(list(frame["bodyweight"]), [192.6, 195.1, 196.4])

    def test_date_parsing_avoids_apis_that_pandas_1_4_lacks(self):
        # pandas 1.4 has neither ``format="mixed"`` nor a working
        # ``infer_datetime_format`` for this case, and this environment cannot
        # install pandas 1.4 to prove compatibility by running the suite, so
        # the constraint is asserted against the module's own calls.
        tree = ast.parse(Path(training_dataset.__file__).read_text())
        pandas_2_only = [
            keyword.arg
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "attr", "") == "to_datetime"
            for keyword in node.keywords
            if keyword.arg in ("format", "infer_datetime_format")
        ]

        self.assertEqual(pandas_2_only, [])

    def test_bodyweight_is_empty_but_typed_when_no_path_is_given(self):
        data = self.load(wld_payload([workout()]))

        self.assertEqual(len(data.bodyweight), 0)
        self.assertEqual(list(data.bodyweight.columns), list(BODYWEIGHT_COLUMNS))
        self.assertEqual(data.bodyweight["week_of"].dtype, "datetime64[ns]")
        self.assertEqual(data.bodyweight["bodyweight"].dtype, "float64")


if __name__ == "__main__":
    unittest.main()
