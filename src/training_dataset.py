"""Canonical normalized training dataset for Weightlifting App exports.

Analyses repeatedly walk the nested ``WLD -> Workout -> Exercise -> Set``
object graph and re-derive the same fields: display names, calendar dates,
per-exercise best estimated 1RMs, per-workout volume. This module does that
traversal once and returns flat pandas DataFrames with stable, documented
columns so callers can filter and group instead of nesting loops.

Typical use from a notebook in ``src/``::

    from training_dataset import load_training_dataset

    data = load_training_dataset(
        "../data/example-chappy.wld", bodyweight_path="../data/weight.csv"
    )
    bench = data.sets[data.sets["display_name"] == "Flat Barbell Bench Press"]
    bench.groupby("week_of")["one_rm"].max()

Column reference and normalization rules live in ``docs/training-dataset.md``.
Nothing here invents measurements: every numeric column is either a source
value or an aggregate of source values, and absent values stay missing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as date_type, datetime
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Union

import pandas as pd

from schema import WLD


PathLike = Union[str, Path]

# Stable public column order, derived from the dtype maps below so the two
# cannot drift. ``docs/training-dataset.md`` documents what each column means.

# Source numerics are float64 so that missing entries stay NaN and plot without
# masked-array handling. Only loader-computed counts, which are never missing,
# use int64.
_WORKOUT_DTYPES = {
    "workout_id": "object",
    "date": "datetime64[ns]",
    "week_of": "datetime64[ns]",
    "name": "object",
    "duration_seconds": "float64",
    "exercise_count": "int64",
    "set_count": "int64",
    "volume": "float64",
}

_EXERCISE_DTYPES = {
    "exercise_id": "object",
    "workout_id": "object",
    "exercise_index": "int64",
    "date": "datetime64[ns]",
    "week_of": "datetime64[ns]",
    "name": "object",
    "iteration": "object",
    "display_name": "object",
    "category": "object",
    "style": "object",
    "set_count": "int64",
    "volume": "float64",
    "best_one_rm": "float64",
}

_SET_DTYPES = {
    "set_id": "object",
    "exercise_id": "object",
    "workout_id": "object",
    "exercise_index": "int64",
    "set_index": "int64",
    "date": "datetime64[ns]",
    "week_of": "datetime64[ns]",
    "name": "object",
    "iteration": "object",
    "display_name": "object",
    "category": "object",
    "style": "object",
    "reps": "float64",
    "weight": "float64",
    "one_rm": "float64",
    "volume": "float64",
    "duration_seconds": "float64",
    "distance": "float64",
    "incline": "float64",
    "calories": "float64",
    "rpe": "float64",
    "rir": "float64",
    "custom": "object",
}

_BODYWEIGHT_DTYPES = {"week_of": "datetime64[ns]", "bodyweight": "float64"}

WORKOUT_COLUMNS: tuple[str, ...] = tuple(_WORKOUT_DTYPES)
EXERCISE_COLUMNS: tuple[str, ...] = tuple(_EXERCISE_DTYPES)
SET_COLUMNS: tuple[str, ...] = tuple(_SET_DTYPES)
BODYWEIGHT_COLUMNS: tuple[str, ...] = tuple(_BODYWEIGHT_DTYPES)

_BODYWEIGHT_HEADER_ALIASES = {"Week of": "week_of", "Average": "bodyweight"}

_SET_SOURCE_FIELDS = (
    ("reps", "reps"),
    ("weight", "weight"),
    ("one_rm", "oneRM"),
    ("volume", "volume"),
    ("duration_seconds", "duration"),
    ("distance", "distance"),
    ("incline", "incline"),
    ("calories", "calories"),
    ("rpe", "rpe"),
    ("rir", "rir"),
    ("custom", "custom"),
)


@dataclass(frozen=True)
class TrainingDataset:
    """Flat views of one export: workouts, exercises, sets, and bodyweight.

    Rows are sorted oldest first. ``workouts`` has one row per session,
    ``exercises`` one row per exercise instance, and ``sets`` one row per
    recorded set. ``exercise_id`` joins sets to exercises and ``workout_id``
    joins either to workouts; the frames also carry denormalized ``date``,
    ``week_of``, ``display_name``, ``category``, and ``style`` so most analyses
    need no join at all. ``bodyweight`` is empty (but keeps its columns) when no
    bodyweight file was supplied.
    """

    workouts: pd.DataFrame
    exercises: pd.DataFrame
    sets: pd.DataFrame
    bodyweight: pd.DataFrame
    source_path: Optional[str] = None

    @classmethod
    def from_wld(
        cls,
        wld: WLD,
        *,
        bodyweight_path: Optional[PathLike] = None,
        source_path: Optional[PathLike] = None,
    ) -> "TrainingDataset":
        """Normalize an already-loaded :class:`~schema.WLD` instance."""
        _validate_workout_ids(wld.workouts, source_path)

        workout_rows: list[dict[str, Any]] = []
        exercise_rows: list[dict[str, Any]] = []
        set_rows: list[dict[str, Any]] = []

        for workout in wld.workouts:
            date = pd.Timestamp(workout.date)
            week_of = _week_of(date)
            workout_id = workout.uuid
            workout_sets = 0
            workout_volumes: list[float] = []

            for exercise_index, exercise in enumerate(workout.exercises):
                exercise_id = f"{workout_id}:{exercise_index}"
                identity = {
                    "workout_id": workout_id,
                    "exercise_index": exercise_index,
                    "date": date,
                    "week_of": week_of,
                    "name": exercise.name,
                    "iteration": exercise.iteration,
                    "display_name": exercise.displayName(),
                    "category": exercise.category,
                    "style": exercise.style,
                }
                volumes: list[float] = []
                one_rms: list[float] = []

                for set_index, set_data in enumerate(exercise.sets):
                    row = {
                        "set_id": f"{exercise_id}:{set_index}",
                        "exercise_id": exercise_id,
                        "set_index": set_index,
                        **identity,
                    }
                    for column, attribute in _SET_SOURCE_FIELDS:
                        row[column] = getattr(set_data, attribute, None)
                    set_rows.append(row)
                    volumes.append(row["volume"])
                    one_rms.append(row["one_rm"])

                exercise_rows.append(
                    {
                        "exercise_id": exercise_id,
                        **identity,
                        "set_count": len(exercise.sets),
                        "volume": _sum(volumes),
                        "best_one_rm": _max(one_rms),
                    }
                )
                workout_sets += len(exercise.sets)
                workout_volumes.extend(volumes)

            workout_rows.append(
                {
                    "workout_id": workout_id,
                    "date": date,
                    "week_of": week_of,
                    "name": workout.name,
                    "duration_seconds": workout.duration,
                    "exercise_count": len(workout.exercises),
                    "set_count": workout_sets,
                    "volume": _sum(workout_volumes),
                }
            )

        workouts = _frame(workout_rows, _WORKOUT_DTYPES, ["date", "workout_id"])
        exercises = _frame(
            exercise_rows,
            _EXERCISE_DTYPES,
            ["date", "workout_id", "exercise_index"],
        )
        sets = _frame(
            set_rows,
            _SET_DTYPES,
            ["date", "workout_id", "exercise_index", "set_index"],
        )
        bodyweight = (
            _load_bodyweight(bodyweight_path)
            if bodyweight_path is not None
            else _frame([], _BODYWEIGHT_DTYPES, ["week_of"])
        )
        return cls(
            workouts=workouts,
            exercises=exercises,
            sets=sets,
            bodyweight=bodyweight,
            source_path=None if source_path is None else str(source_path),
        )

    def __repr__(self) -> str:
        return (
            f"TrainingDataset(workouts={len(self.workouts)}, "
            f"exercises={len(self.exercises)}, sets={len(self.sets)}, "
            f"bodyweight_weeks={len(self.bodyweight)})"
        )


def load_training_dataset(
    wld_path: PathLike, *, bodyweight_path: Optional[PathLike] = None
) -> TrainingDataset:
    """Load a ``.wld`` export, and optionally a bodyweight CSV, as flat frames.

    ``bodyweight_path`` accepts ``data/weight.csv`` as written by
    ``scripts/convert_weight_xlsx.py`` (``Week of``/``Average`` headers) or a
    file already using the canonical ``week_of``/``bodyweight`` headers.

    Raises ``FileNotFoundError`` when a path is missing and ``ValueError`` when
    a file exists but is not a usable export.
    """
    with open(wld_path, "r") as export:
        try:
            payload = json.load(export)
        except ValueError as error:
            raise ValueError(
                f"{wld_path} is not a valid .wld export: {error}"
            ) from error

    _validate_payload(payload, wld_path)
    try:
        wld = WLD(**payload)
    except (KeyError, TypeError, AttributeError) as error:
        # Anything the structural check above did not anticipate still reaches
        # the caller as a ValueError naming the file rather than as a raw
        # KeyError from deep inside the schema classes.
        raise ValueError(
            f"{wld_path} is not a valid .wld export: {error}"
        ) from error
    return TrainingDataset.from_wld(
        wld, bodyweight_path=bodyweight_path, source_path=wld_path
    )


_REQUIRED_SECTIONS = ("typeList", "settings", "user", "workouts")


def _describe(value: Any) -> str:
    """Name a malformed value the way the error messages should read."""
    if value is None:
        return "null"
    return {
        bool: "a boolean",
        int: "a number",
        float: "a number",
        str: "a string",
        list: "a list",
        dict: "an object",
    }.get(type(value), type(value).__name__)


def _validate_payload(payload: Any, source: PathLike) -> None:
    """Reject malformed exports with a message naming the offending record.

    The schema classes assume well formed input, so a null section or a null
    set otherwise surfaces as a bare ``TypeError`` from inside a list
    comprehension. Checking the shape first turns each of those into a
    ``ValueError`` that says which record is wrong.
    """

    def invalid(detail: str) -> ValueError:
        return ValueError(f"{source} is not a valid .wld export: {detail}")

    if not isinstance(payload, dict):
        raise invalid(
            f"expected an object at the top level, found {_describe(payload)}"
        )

    for section in _REQUIRED_SECTIONS:
        if section not in payload:
            raise invalid(f"missing the '{section}' section")
        if payload[section] is None:
            raise invalid(f"the '{section}' section is null")

    for section in ("settings", "user"):
        if not isinstance(payload[section], dict):
            raise invalid(
                f"'{section}' must be an object, found {_describe(payload[section])}"
            )
    if not isinstance(payload["typeList"], dict) or "list" not in payload["typeList"]:
        raise invalid("'typeList' must be an object containing a 'list' entry")
    if not isinstance(payload["workouts"], list):
        raise invalid(
            f"'workouts' must be a list, found {_describe(payload['workouts'])}"
        )

    for index, workout in enumerate(payload["workouts"]):
        if not isinstance(workout, dict):
            raise invalid(
                f"workout {index} must be an object, found {_describe(workout)}"
            )
        exercises = workout.get("exercises", [])
        if not isinstance(exercises, list):
            raise invalid(
                f"workout {index} has an invalid 'exercises' value: expected a "
                f"list, found {_describe(exercises)}"
            )
        for exercise_index, exercise in enumerate(exercises):
            label = f"workout {index} exercise {exercise_index}"
            if not isinstance(exercise, dict):
                raise invalid(
                    f"{label} must be an object, found {_describe(exercise)}"
                )
            sets = exercise.get("sets", [])
            if not isinstance(sets, list):
                raise invalid(
                    f"{label} has an invalid 'sets' value: expected a list, "
                    f"found {_describe(sets)}"
                )
            for set_index, set_record in enumerate(sets):
                if not isinstance(set_record, dict):
                    raise invalid(
                        f"{label} set {set_index} must be an object, found "
                        f"{_describe(set_record)}"
                    )


def _validate_workout_ids(workouts: Iterable[Any], source: Optional[PathLike]) -> None:
    """Require a present, unique uuid on every workout.

    Exercise and set identifiers are built from the workout uuid, so a missing
    or repeated uuid would silently produce colliding ``exercise_id`` and
    ``set_id`` values instead of failing.
    """
    prefix = "" if source is None else f"{source}: "
    first_seen: dict[str, int] = {}
    for index, workout in enumerate(workouts):
        workout_id = workout.uuid
        recorded = f"recorded {workout.date:%Y-%m-%d %H:%M}"
        if not isinstance(workout_id, str) or not workout_id.strip():
            raise ValueError(
                f"{prefix}workout {index} ({recorded}) has no uuid, but exercise "
                "and set identifiers are derived from it"
            )
        if workout_id in first_seen:
            raise ValueError(
                f"{prefix}workout uuid {workout_id!r} is used by both workout "
                f"{first_seen[workout_id]} and workout {index} ({recorded}); "
                "workout uuids must be unique because exercise and set "
                "identifiers are derived from them"
            )
        first_seen[workout_id] = index


def _week_of(date: pd.Timestamp) -> pd.Timestamp:
    """Return the Monday that starts ``date``'s week, at midnight."""
    normalized = date.normalize()
    return normalized - pd.Timedelta(days=normalized.weekday())


def _sum(values: Sequence[Any]) -> float:
    """Total the recorded values, or NaN when nothing was recorded."""
    recorded = [float(value) for value in values if _is_number(value)]
    return sum(recorded) if recorded else float("nan")


def _max(values: Sequence[Any]) -> float:
    recorded = [float(value) for value in values if _is_number(value)]
    return max(recorded) if recorded else float("nan")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _frame(
    rows: Sequence[dict[str, Any]],
    dtypes: dict[str, str],
    sort_by: Sequence[str],
) -> pd.DataFrame:
    """Build a column- and dtype-stable frame, including when ``rows`` is empty."""
    frame = pd.DataFrame(list(rows), columns=list(dtypes))
    for column, dtype in dtypes.items():
        series = frame[column]
        if dtype == "datetime64[ns]":
            # The trailing astype is not redundant: pandas 3 infers microsecond
            # resolution from Python datetimes and second resolution from an
            # empty column, so without it a populated frame and an empty one
            # disagree, and neither matches the documented dtype.
            frame[column] = pd.to_datetime(series, errors="coerce").astype(dtype)
        elif dtype in ("float64", "int64"):
            frame[column] = pd.to_numeric(series, errors="coerce").astype(dtype)
        else:
            frame[column] = _as_object(series)
    if len(frame):
        frame = frame.sort_values(list(sort_by), kind="stable")
    return frame.reset_index(drop=True)


def _is_missing(value: Any) -> bool:
    """Report the several ways pandas and the export spell "no value"."""
    return (
        value is None
        or value is pd.NaT
        or value is pd.NA
        or (isinstance(value, float) and value != value)
    )


def _as_object(series: pd.Series) -> pd.Series:
    """Rebuild a text column with ``None`` for every missing entry.

    Constructing a DataFrame from records turns ``None`` in a text column into
    ``NaN`` under pandas 3, which would make ``iteration`` and ``custom`` report
    a float where the export recorded nothing. Missing stays ``None`` here, and
    the column stays ``object`` rather than adopting the pandas 3 string dtype.
    """
    return pd.Series(
        [None if _is_missing(value) else value for value in series],
        index=series.index,
        dtype="object",
    )


def _to_timestamp(value: Any) -> Any:
    """Parse one cell into a ``Timestamp``, or ``NaT`` when it is not a date."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return pd.NaT
        value = text
    elif not isinstance(value, (datetime, date_type, pd.Timestamp)):
        return pd.NaT
    try:
        return pd.Timestamp(value)
    except (ValueError, TypeError, OverflowError):
        return pd.NaT


def _parse_dates(values: pd.Series) -> pd.Series:
    """Parse a date column one cell at a time, preserving mixed formats.

    Deliberately avoids ``pd.to_datetime`` on the whole column: pandas 2 infers
    a single format from the first entry and coerces every other layout in the
    column to ``NaT``, and the ``format="mixed"`` escape hatch does not exist
    before pandas 2.0. Parsing per cell behaves the same way on pandas 1.4 and
    on pandas 2.x, and a sheet is small enough that the cost does not matter.
    """
    return pd.Series(
        [_to_timestamp(value) for value in values],
        index=values.index,
        dtype="datetime64[ns]",
    )


def _load_bodyweight(path: PathLike) -> pd.DataFrame:
    """Read a weekly bodyweight CSV into ``week_of``/``bodyweight`` columns."""
    frame = pd.read_csv(path)
    frame = frame.rename(
        columns={
            header: canonical
            for header, canonical in _BODYWEIGHT_HEADER_ALIASES.items()
            if header in frame.columns and canonical not in frame.columns
        }
    )
    missing = [column for column in BODYWEIGHT_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(
            f"{path} is missing bodyweight columns: {missing}. Expected "
            f"{list(BODYWEIGHT_COLUMNS)} or {list(_BODYWEIGHT_HEADER_ALIASES)}."
        )

    frame = frame.loc[:, list(BODYWEIGHT_COLUMNS)].copy()
    frame["week_of"] = _parse_dates(frame["week_of"]).dt.normalize()
    frame["bodyweight"] = pd.to_numeric(frame["bodyweight"], errors="coerce")
    # A formula cell without a measurement evaluates to 0, which is not a
    # bodyweight; it stays missing rather than distorting joins or charts.
    frame.loc[frame["bodyweight"] <= 0, "bodyweight"] = float("nan")
    frame = frame[frame["week_of"].notna()]
    frame = frame.sort_values("week_of", kind="stable").drop_duplicates(
        "week_of", keep="last"
    )
    return _frame(frame.to_dict("records"), _BODYWEIGHT_DTYPES, ["week_of"])


__all__ = [
    "BODYWEIGHT_COLUMNS",
    "EXERCISE_COLUMNS",
    "SET_COLUMNS",
    "WORKOUT_COLUMNS",
    "TrainingDataset",
    "load_training_dataset",
]
