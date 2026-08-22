# Canonical training dataset

`src/training_dataset.py` turns a Weightlifting App `.wld` export into three flat
pandas DataFrames — one row per workout, per exercise instance, and per set — so
an analysis can filter and group instead of walking the nested
`WLD -> Workout -> Exercise -> Set` object graph and re-deriving display names,
calendar weeks, and per-exercise bests.

```python
from training_dataset import load_training_dataset

data = load_training_dataset(
    "../data/example-chappy.wld", bodyweight_path="../data/weight.csv"
)
bench = data.sets[data.sets["display_name"] == "Flat Barbell Bench Press"]
weekly_best = bench.groupby("week_of")["one_rm"].max()
```

The schema classes in `src/schema/` are unchanged and still work; this module is
a layer on top of them. `TrainingDataset.from_wld(wld)` normalizes an already
loaded `WLD` instance, which is useful when a notebook loads several exports.

## Interface

| Name | Purpose |
| --- | --- |
| `load_training_dataset(wld_path, *, bodyweight_path=None)` | Load an export (and optionally a weekly bodyweight CSV) into a `TrainingDataset`. |
| `TrainingDataset` | Frozen container of the `workouts`, `exercises`, `sets`, and `bodyweight` frames plus `source_path`. |
| `TrainingDataset.from_wld(wld, *, bodyweight_path=None, source_path=None)` | Normalize an already-loaded `WLD`. |
| `WORKOUT_COLUMNS`, `EXERCISE_COLUMNS`, `SET_COLUMNS`, `BODYWEIGHT_COLUMNS` | The stable column order of each frame. |

## Normalization rules

- **Nothing is invented.** Every numeric column is a source value or an
  aggregate of source values. A field the app never recorded stays `NaN`
  (`None` for text), and an aggregate over nothing recorded is `NaN`, not `0`.
- **Dates.** `date` is the workout's start timestamp, parsed from either format
  the export uses (`2024-01-03 07:30` and `2024-01-06 3:04 p.m.`). Exercise and
  set rows carry their workout's `date`.
- **Weeks.** `week_of` is the Monday at midnight that starts the row's week,
  matching how `data/weight.csv` is keyed, so training rows join to bodyweight
  rows on `week_of`. It ignores the export's `startWeekOnMonday` setting.
- **Identifiers.** `workout_id` is the export's workout UUID. `exercise_id` is
  `"{workout_id}:{exercise_index}"` and `set_id` is `"{exercise_id}:{set_index}"`,
  where the indexes are positions within the source record. Each frame also
  carries denormalized identity columns, so most analyses need no join.
- **Ordering.** Rows are sorted oldest first — workouts by `(date, workout_id)`,
  exercises and sets by their position inside the workout — and the index is a
  plain `RangeIndex`.
- **Types.** Source numerics are `float64` so missing entries stay `NaN` and
  plot without masked-array handling; counts computed here, which are never
  missing, are `int64`. Columns and dtypes are identical whether the export has
  2,281 workouts or none.

## `workouts` — one row per session

| Column | Type | Meaning |
| --- | --- | --- |
| `workout_id` | object | Workout UUID from the export. |
| `date` | datetime64[ns] | Session start timestamp. |
| `week_of` | datetime64[ns] | Monday that starts the session's week. |
| `name` | object | Session name, e.g. `Morning Workout`. |
| `duration_seconds` | float64 | Recorded session duration in seconds. |
| `exercise_count` | int64 | Exercise instances in the session. |
| `set_count` | int64 | Sets across all of the session's exercises. |
| `volume` | float64 | Sum of recorded set volumes; `NaN` if none were recorded. |

## `exercises` — one row per exercise instance

| Column | Type | Meaning |
| --- | --- | --- |
| `exercise_id` | object | `"{workout_id}:{exercise_index}"`. |
| `workout_id` | object | Owning workout. |
| `exercise_index` | int64 | Position within the workout, starting at 0. |
| `date`, `week_of` | datetime64[ns] | Copied from the workout. |
| `name` | object | Exercise name without the iteration. |
| `iteration` | object | Variant recorded by the app, or `None`. |
| `display_name` | object | `"{iteration} {name}"`, or `name` alone. |
| `category` | object | App category, e.g. `Chest`. |
| `style` | object | App style, e.g. `reps_weight`. |
| `set_count` | int64 | Sets recorded for this instance; `0` keeps the row. |
| `volume` | float64 | Sum of recorded set volumes; `NaN` if none. |
| `best_one_rm` | float64 | Highest recorded estimated 1RM; `NaN` if none. |

## `sets` — one row per set

Identity columns `set_id`, `exercise_id`, `workout_id`, `exercise_index`,
`set_index`, `date`, `week_of`, `name`, `iteration`, `display_name`, `category`,
and `style` carry the same meanings as above.

| Column | Type | Meaning |
| --- | --- | --- |
| `reps` | float64 | Recorded repetitions. |
| `weight` | float64 | Recorded weight, in the export's units. |
| `one_rm` | float64 | Estimated 1RM recorded by the app (`oneRM`). |
| `volume` | float64 | Set volume recorded by the app. |
| `duration_seconds` | float64 | Recorded set duration. |
| `distance` | float64 | Recorded distance. |
| `incline` | float64 | Recorded incline. |
| `calories` | float64 | Recorded calories. |
| `rpe`, `rir` | float64 | Recorded effort ratings. |
| `custom` | object | Free-text set value, or `None`. |

## `bodyweight` — one row per week

Loaded only when `bodyweight_path` is given; otherwise the frame is empty with
these columns. It accepts the `Week of`/`Average` headers written by
`scripts/convert_weight_xlsx.py` as well as the canonical headers below.

| Column | Type | Meaning |
| --- | --- | --- |
| `week_of` | datetime64[ns] | Week key from the sheet, normalized to midnight. |
| `bodyweight` | float64 | Average bodyweight for the week; `NaN` when the week has no usable measurement. |

Rows are sorted by `week_of`; a row whose week cannot be parsed is dropped, and
if a week repeats the last row wins. A value of `0` or below is treated as
missing rather than as a measurement, because empty formula cells in the source
spreadsheet evaluate to `0`.

## Errors

- Missing file → `FileNotFoundError`.
- File that is not a usable export (bad JSON, or a missing top-level section) →
  `ValueError` naming the problem.
- Workout date the schema cannot parse → `ValueError` naming the date.
- Bodyweight CSV without usable headers → `ValueError` listing what was expected.

## Tests

```bash
PYTHONPATH=.:src python -m unittest discover -s tests
```
