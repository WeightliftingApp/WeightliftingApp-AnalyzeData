# Agent review — canonical training dataset

Task: add a canonical normalized training dataset module so analyses stop
repeating `.wld` traversal and normalization.

Delivered: `src/training_dataset.py`, `tests/test_training_dataset.py`,
`docs/training-dataset.md`, and README pointers. No schema class, notebook, or
script was modified.

## What the module does

`load_training_dataset(wld_path, *, bodyweight_path=None)` returns a frozen
`TrainingDataset` holding `workouts`, `exercises`, `sets`, and `bodyweight`
DataFrames with stable documented columns. `TrainingDataset.from_wld(wld)`
covers the case where a caller already has a `WLD` instance. The public surface
is six names (one function, one dataclass with one classmethod, four column
tuples) over ~350 lines of implementation, and callers never touch a nested
schema object.

## Judgment calls

- **Source numerics are `float64`, loader-computed counts are `int64`.** `reps`
  and `calories` are integers in the export, so nullable `Int64` was tempting.
  Rejected: `pd.NA` in a masked array trips up matplotlib and some numpy paths,
  and these frames are plotted directly in notebooks. `float64` also cannot
  raise on a non-integral value in someone else's export. The cost is that
  `reps` displays as `12.0`.
- **Aggregates over nothing recorded are `NaN`, not `0`.** `Workout.volume()`
  and `Exercise.volume()` in the schema return `0` when no set carries a
  volume. This module returns `NaN`, because `0` is a claim the data does not
  make. Totals still match the schema exactly on the example export (verified:
  56,165,958 either way), since real sessions do record volume.
- **`week_of` is Monday-start regardless of the export's `startWeekOnMonday`
  setting.** `data/weight.csv` is Monday-keyed (all 410 rows), and
  `build_big_three_pr_history` already assumes Monday, so a settings-dependent
  week would break the join it exists to serve. Documented rather than inferred.
- **Rows sorted oldest first.** The export stores workouts newest-first, and
  every notebook re-sorts. Sorting once here is normalization, not invention.
- **Denormalized identity columns on `exercises` and `sets`** (`date`,
  `week_of`, `display_name`, `category`, `style`). This makes the frames wider
  but removes the join from the common filter-then-group analysis, which was the
  point of the task.
- **Synthetic `exercise_id`/`set_id`.** The export gives UUIDs only to workouts.
  `"{workout_id}:{index}"` is deterministic and readable, and it makes the
  parent/child relationship testable.
- **Malformed exports raise `ValueError`.** A missing top-level section
  otherwise surfaces as a bare `KeyError('typeList')` from `schema.WLD`; the
  loader wraps it with the path and the missing key. Unparseable dates keep the
  schema's existing `ValueError`.
- **Bodyweight dates parse with `format="mixed"`.** A first draft used plain
  `pd.to_datetime`, which infers one format from the first row and silently
  coerced every differently-formatted row to `NaT` — a test caught it dropping a
  valid week. This requires pandas ≥ 2.0; the pinned environment has 2.2.3 and
  `requirements.txt` is unpinned, which was left alone (packaging is out of
  scope).

## Rejected alternatives

- **DEXA support.** Scope allowed it "only if simple and well tested". Rejected:
  `data/dexa.csv` is gitignored and absent from this worktree, so there is
  nothing to test against; its 12-column schema is wider than the two-column
  bodyweight sheet; and a parallel branch (`codex/dexa-pipeline-split`) is
  reworking that pipeline, so hardcoding its columns here invites a conflict.
  Over `pd.read_csv`, a passthrough loader would have added nothing.
- **A `lift` column mapping variants to canonical lifts** (Conventional + Sumo
  Deadlifts → `Deadlift`). Every notebook writes this mapping itself, so it is
  the most duplicated logic left. Rejected here because the mapping is an
  analysis-specific taxonomy, not a property of the export — inventing one would
  cross the "preserve source values" line. See next steps.
- **Migrating notebooks onto the module.** Explicitly out of scope for this task.
- **A `conftest.py` or pytest config to fix `PYTHONPATH`.** The existing tests
  already require `PYTHONPATH=.:src`; changing test bootstrapping is packaging
  work and out of scope. The command is now in the README.
- **`superset_count` on `workouts`.** Superset groupings are the one workout
  field not represented in the flat frames. Left out to keep the frame lean; the
  schema still exposes them.

## Edge cases covered by tests

- Export with zero workouts: all frames empty with identical columns and dtypes
  to a populated load.
- Exercise with zero sets: keeps its row with `set_count=0` and `NaN`
  aggregates, and emits no set rows.
- Sets missing optional fields: `weight`, `one_rm`, `volume`, `duration_seconds`,
  `rpe`, `rir` stay `NaN`; `custom` stays `None`; `reps` is preserved.
- Both recorded date formats (`2024-01-03 07:30` and `2024-01-06 3:04 p.m.`)
  parse to the same normalized timestamps and the same Monday `week_of`.
- Export missing a top-level section → `ValueError` naming the key; unparseable
  workout date → `ValueError` naming the date; missing file → `FileNotFoundError`.
- Bodyweight CSV: exported and canonical headers, blank/`0`/negative values kept
  as rows with `NaN`, unparseable week dropped, duplicate week keeps the last,
  wrong headers → `ValueError`.
- Example export: column order, row-count relationships across all three frames,
  id uniqueness and containment, ascending order, and volume parity with the
  nested `Workout.volume()` traversal.

## Issues and ambiguities

- The example export contains no `incline`, `rpe`, or `rir` values, so those
  columns are declared and typed but exercised only by synthetic fixtures.
- `data/weight.csv` is gitignored and not present in this worktree. Bodyweight
  parsing was verified against synthetic CSVs in tests, and additionally checked
  by hand against the real 410-row file in the main checkout (410 rows, 80
  weeks missing, all Mondays).
- Duplicate workout UUIDs would produce duplicate `exercise_id`s. The example
  export has none, and nothing in the pipeline dedupes; not handled.
- `TrainingDataset` is a frozen dataclass, but the DataFrames it holds are
  mutable. Callers should copy before mutating.

## Shortcuts

- No pytest/CI wiring, no notebook migration, no `requirements.txt` pin — all
  out of scope.
- The bodyweight loader assumes the sheet is already keyed by week; it
  normalizes the time of day but does not snap a non-Monday key to Monday,
  which would silently shift a Sunday-keyed sheet by six days.

## Commands run

```bash
# baseline, before any change: 13 tests, OK
PYTHONPATH=.:src venv/bin/python -m unittest discover -s tests

# after: 33 tests (13 existing + 20 new), OK
PYTHONPATH=.:src venv/bin/python -m unittest discover -s tests -v

# example export loads through the new interface in ~0.3s
PYTHONPATH=src venv/bin/python -c "from training_dataset import load_training_dataset; \
  print(load_training_dataset('data/example-chappy.wld'))"
# TrainingDataset(workouts=2281, exercises=10709, sets=47421, bodyweight_weeks=0)
```

The worktree has no `venv`; the main checkout's interpreter
(`/Users/chappyasel/Desktop/Repos/WeightliftingApp-AnalyzeData/venv/bin/python`,
Python 3.13.12, pandas 2.2.3) was used read-only. `pytest` is not installed
anywhere, so the suite runs under `unittest`, matching the existing tests.

## Next steps

1. Migrate one notebook (`analyze_bodyweight_strength_evals.ipynb` is the best
   candidate — it builds `set_records` and reads `weight.csv` by hand) and let
   that migration decide whether a variant→lift mapping helper belongs here.
2. If a second notebook needs the same mapping, add it as an explicit
   caller-supplied dict (`dataset.with_lifts({...})`), not a built-in taxonomy.
3. Consider DEXA support once `codex/dexa-pipeline-split` settles the CSV schema
   and a fixture file exists to test against.
