# Agent review: canonical training dataset

Task: add a canonical normalized training dataset module so analyses stop
repeating `.wld` traversal and normalization.

Delivered: `src/training_dataset.py`, `tests/test_training_dataset.py`,
`docs/training-dataset.md`, and a README pointer. No schema class, notebook, or
script was modified.

## What the module does

`load_training_dataset(wld_path, *, bodyweight_path=None)` returns a frozen
`TrainingDataset` holding `workouts`, `exercises`, `sets`, and `bodyweight`
DataFrames with stable documented columns. `TrainingDataset.from_wld(wld)`
covers the case where a caller already has a `WLD` instance. The public surface
is six names (one function, one dataclass with one classmethod, four column
tuples) over roughly 500 lines of implementation, and callers never touch a
nested schema object.

## Review follow-up

A review of the first commit raised four items. All four are fixed in the second
commit on this branch.

### 1. pandas 2 only date parsing

Finding: the bodyweight loader called
`pd.to_datetime(..., format="mixed")`, which does not exist before pandas 2.0,
while `requirements.txt` is unpinned. The branch either had to pin pandas or
stop depending on the new API.

Fix: dropped the API rather than the pandas 1.4 support, since pinning belongs
to the packaging branch and would couple the two. `_parse_dates` now parses one
cell at a time through `pd.Timestamp`, which behaves identically on pandas 1.4
and 2.x and still preserves mixed formats inside a column. A weekly sheet is a
few hundred rows, so per cell parsing costs nothing measurable.

Tests: `test_each_row_is_parsed_on_its_own_terms` feeds three different layouts
(`2024-01-01 06:00:00`, `2024-01-08`, `1/15/2024`) in one column and asserts all
three parse, which is the exact case pandas 2 format inference breaks. Because
pandas 1.4 cannot be installed in this environment,
`test_date_parsing_avoids_apis_that_pandas_1_4_lacks` parses the module with
`ast` and asserts no `to_datetime` call passes `format` or
`infer_datetime_format`. That is a guard on the constraint, not a substitute for
running the suite on pandas 1.4.

### 2. Unvalidated workout UUIDs

Finding: `exercise_id` and `set_id` are built as `"{workout_id}:{index}"`, so a
missing or repeated workout uuid silently produced colliding identifiers. The
first round noted the risk and did not handle it.

Fix: `_validate_workout_ids` runs at the top of `TrainingDataset.from_wld`,
before any row is built, so both the loader and the `from_wld` entry point are
covered. A missing, non string, or blank uuid and a repeated uuid each raise a
`ValueError` naming the workout index, its recorded time, and, for duplicates,
both offending positions and the repeated uuid.

Tests: missing uuid, whitespace only uuid, duplicate uuid naming both workouts,
and a `from_wld` case proving the check is not confined to the file loader.

### 3. Malformed structure surfaced as raw TypeError

Finding: a null or list top level, a null section, and a null `sets` list each
reached the caller as a bare `TypeError` from inside a schema list
comprehension, for example `'NoneType' object is not iterable`, with nothing
identifying the file or the record.

Fix: `load_training_dataset` now reads and parses the JSON itself, runs
`_validate_payload` over the structure, and then constructs `WLD(**payload)`.
The validator checks the top level type, the four required sections, the shape
of `settings`, `user`, `typeList`, and `workouts`, and every workout, exercise,
and set record, raising a `ValueError` that names the position, for example
`workout 0 exercise 2 set 1 must be an object, found null`. A defensive
`except (KeyError, TypeError, AttributeError)` around the schema construction
converts anything the validator does not anticipate into a `ValueError` naming
the file rather than a raw schema error. Invalid JSON is wrapped the same way.

Tests: eleven cases in `MalformedExportTest` covering null and list top levels,
a null section, `workouts` that is not a list, `settings` that is not an object,
a `typeList` without its `list` entry, a null workout entry, a null `exercises`
list, a null `sets` list, a null set entry, and a file that is not JSON. Each
was confirmed non vacuous by checking what the raw schema does with the same
payload: all seven structural cases raise `KeyError` or `TypeError` without the
validator.

### 4. README collided with the repository foundation branch

Finding: the first commit added a `## Tests` section telling readers to
`source venv/bin/activate` and run `unittest`. The `codex/repo-foundation`
branch adds `## Setup` and `## Development` sections that use `.venv`, an
editable install, and `python -m pytest`, so this branch was overwriting
instructions it does not own.

Fix: removed the README `## Tests` section. The README now carries only the
usage pointer to the module and to `docs/training-dataset.md`. The test command
moved into `docs/training-dataset.md`, phrased as what the module's tests need
(`src` on the path when there is no editable install) rather than as the
repository's test policy. `git merge-tree` against `codex/repo-foundation`
reports no conflict.

## Review follow-up: pandas 3

A combined integration run on a fresh install with pandas 3.0.5 failed three of
this module's tests. All three were the module's own dtype and null contract
drifting with the pandas version, not test noise, and all three are fixed.

Reproduced locally in a throwaway venv with pandas 3.0.5 and numpy 2.5.2 on
Python 3.14, which showed the same three failures before the fix.

### 1. Text columns reported `NaN` where the export recorded nothing

`exercises.iteration` came back as `nan` instead of `None`. Building a DataFrame
from records under pandas 3 infers the new string dtype for a text column and
turns `None` into `NaN` on the way in, so an exercise with no iteration
reported a float. `_as_object` now rebuilds every text column with `None` for
each missing entry and pins the column to `object`, which keeps the documented
`None` semantics and keeps the dtype off the pandas 3 string dtype.

### 2. Date dtypes differed between populated and empty frames

Populated frames carried `datetime64[us]`, inferred from Python datetimes, while
empty frames carried `datetime64[s]`, inferred from an empty column. Neither
matched the documented `datetime64[ns]`. `_frame` now casts every date column
with `.astype("datetime64[ns]")` after parsing, which is a no-op on pandas 2 and
normalizes both cases on pandas 3.

### 3. Empty bodyweight `week_of` was `datetime64[s]`

Same root cause as item 2, reached through the no bodyweight path, and fixed by
the same cast.

### Regression coverage

`DtypeContractTest` asserts the dtype names literally, for populated and empty
frames separately, across all four frames. The previous check compared an empty
frame's dtypes against a populated one, which only proves the two agree: under
pandas 3 they drifted together and the comparison still would have passed for
the bodyweight case and failed uninformatively for the rest. The new tests also
assert that every text column holds only `str` or `None`, never a float.

Confirmed non vacuous by running the new tests against a copy of the pre-fix
module under pandas 3: three of the five fail, one per defect above.

## Judgment calls

- **Source numerics are `float64`, loader computed counts are `int64`.** `reps`
  and `calories` are integers in the export, so nullable `Int64` was tempting.
  Rejected: `pd.NA` in a masked array trips up matplotlib and some numpy paths,
  and these frames are plotted directly in notebooks. `float64` also cannot
  raise on a non integral value in someone else's export. The cost is that
  `reps` displays as `12.0`.
- **Aggregates over nothing recorded are `NaN`, not `0`.** `Workout.volume()`
  and `Exercise.volume()` in the schema return `0` when no set carries a
  volume. This module returns `NaN`, because `0` is a claim the data does not
  make. Totals still match the schema exactly on the example export (verified:
  56,165,958 either way), since real sessions do record volume.
- **`week_of` is Monday start regardless of the export's `startWeekOnMonday`
  setting.** `data/weight.csv` is Monday keyed (all 410 rows), and
  `build_big_three_pr_history` already assumes Monday, so a settings dependent
  week would break the join it exists to serve. Documented rather than inferred.
- **Rows sorted oldest first.** The export stores workouts newest first, and
  every notebook re-sorts. Sorting once here is normalization, not invention.
- **Denormalized identity columns on `exercises` and `sets`** (`date`,
  `week_of`, `display_name`, `category`, `style`). This makes the frames wider
  but removes the join from the common filter then group analysis, which was the
  point of the task.
- **Synthetic `exercise_id`/`set_id`.** The export gives UUIDs only to workouts.
  `"{workout_id}:{index}"` is deterministic and readable, and it makes the
  parent and child relationship testable. It is also why review item 2 matters.
- **Dtypes are pinned rather than inherited from pandas.** The alternative was
  to document whatever pandas infers, which would make the column contract vary
  by installed version. Pinning costs one cast per date column and one rebuild
  per text column on load, which is not measurable next to parsing the export.
- **Text columns stay `object` instead of adopting the pandas 3 string dtype.**
  The string dtype would be a better fit for these columns, but switching would
  change what callers get depending on the pandas version, which is the problem
  this fix exists to remove. Revisit when the repository requires pandas 3.
- **The loader reads the JSON instead of delegating to `WLD(file_path=...)`.**
  Validating the payload requires seeing it. The file is still parsed once and
  the schema still builds every object, so this is a change of entry point, not
  of behavior.

## Rejected alternatives

- **Pinning `pandas>=2` in `requirements.txt` or `pyproject.toml`.** Packaging
  is owned by `codex/repo-foundation`, and the review preferred compatibility
  over a pin. Making the parsing version independent removed the need entirely.
- **DEXA support.** Scope allowed it only if simple and well tested. Rejected:
  `data/dexa.csv` is gitignored and absent from this worktree, so there is
  nothing to test against; its 12 column schema is wider than the two column
  bodyweight sheet; and a parallel branch (`codex/dexa-pipeline-split`) is
  reworking that pipeline, so hardcoding its columns here invites a conflict.
  Over `pd.read_csv`, a passthrough loader would have added nothing.
- **A `lift` column mapping variants to canonical lifts** (Conventional and Sumo
  Deadlifts to `Deadlift`). Every notebook writes this mapping itself, so it is
  the most duplicated logic left. Rejected here because the mapping is an
  analysis specific taxonomy, not a property of the export, so building one in
  would cross the "preserve source values" line. See next steps.
- **Migrating notebooks onto the module.** Explicitly out of scope.
- **A `conftest.py` or pytest config to fix `PYTHONPATH`.** The existing tests
  already require `PYTHONPATH=.:src`; changing test bootstrapping is packaging
  work owned by another branch.
- **Skipping a workout with a duplicate uuid instead of failing.** Silently
  dropping training data is worse than refusing to load it, and the caller
  cannot notice the loss.
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
- Workout uuids: missing, blank, and duplicated, through both entry points.
- Malformed structure: null and list top levels, null and wrongly shaped
  sections, null workout, `exercises`, `sets`, and set records, and a file that
  is not JSON.
- Unparseable workout date raises `ValueError` naming the date; missing file
  raises `FileNotFoundError`.
- Dtype contract: date columns are `datetime64[ns]` and text columns are
  `object` in populated and in empty frames, asserted by name rather than by
  comparing frames; missing text values are `None` and never `NaN`.
- Bodyweight CSV: exported and canonical headers, three different date layouts
  in one column, blank, `0`, and negative values kept as rows with `NaN`,
  unparseable week dropped, duplicate week keeps the last, wrong headers raise
  `ValueError`.
- Example export: column order, row count relationships across all three frames,
  id uniqueness and containment, ascending order, and volume parity with the
  nested `Workout.volume()` traversal.

## Issues and ambiguities

- pandas 1.4 compatibility is argued, not executed. No pandas 1.4 interpreter is
  available here, so the `ast` guard and per cell parsing are the evidence. The
  suite now runs on pandas 2.2.3 and 3.0.5, so the untested end is the floor,
  not the ceiling. A CI matrix would settle it.
- The pandas 3 run used a throwaway venv built for this fix, not the repository's
  own environment, which still has pandas 2.2.3. The packaging branch owns which
  versions CI exercises.
- The example export contains no `incline`, `rpe`, or `rir` values, so those
  columns are declared and typed but exercised only by synthetic fixtures.
- `data/weight.csv` is gitignored and not present in this worktree. Bodyweight
  parsing was verified against synthetic CSVs in tests, and additionally checked
  by hand against the real 410 row file in the main checkout (410 rows, 80 weeks
  missing, all Mondays).
- Validation now raises where the first commit would have loaded. An export with
  duplicate workout uuids that previously produced colliding ids will now fail
  to load. That is the intent, but it is a behavior change for any such file.
- `TrainingDataset` is a frozen dataclass, but the DataFrames it holds are
  mutable. Callers should copy before mutating.

## Shortcuts

- No pytest or CI wiring, no notebook migration, no dependency pin. All are
  owned by the packaging branch or later tasks.
- The bodyweight loader assumes the sheet is already keyed by week. It
  normalizes the time of day but does not snap a non Monday key to Monday,
  which would silently shift a Sunday keyed sheet by six days.
- `_validate_payload` checks structure, not field types inside a record. A
  workout whose `duration` is a string still loads and lands as `NaN`.

## Commands run

```bash
# baseline, before any change: 13 tests, OK
PYTHONPATH=.:src venv/bin/python -m unittest discover -s tests

# first commit: 33 tests (13 existing + 20 new), OK
# after the first review round: 50 tests, OK
# after the pandas 3 fixes: 55 tests (13 existing + 42 new), OK on pandas 2.2.3
PYTHONPATH=.:src venv/bin/python -m unittest discover -s tests -v

# same 55 tests on a throwaway venv with pandas 3.0.5, numpy 2.5.2, Python 3.14:
# 3 failures before the fix, all 55 passing after
PYTHONPATH=.:src <scratch>/pandas3/bin/python -m unittest discover -s tests

# confirmed the new dtype tests fail against a copy of the pre-fix module
PYTHONPATH=<scratch>/broken:.:src <scratch>/pandas3/bin/python -m unittest \
  tests.test_training_dataset.DtypeContractTest

# example export loads through the new interface in about 0.3s
PYTHONPATH=src venv/bin/python -c "from training_dataset import load_training_dataset; \
  print(load_training_dataset('data/example-chappy.wld'))"
# TrainingDataset(workouts=2281, exercises=10709, sets=47421, bodyweight_weeks=0)

# confirmed the malformed payload tests are not vacuous by checking what the
# raw schema does with the same payloads (KeyError or TypeError in every case)

# confirmed the README no longer collides with the packaging branch
git merge-tree --write-tree codex/canonical-dataset codex/repo-foundation
```

The worktree had no environment of its own, so the main checkout's interpreter
(Python 3.13.12, pandas 2.2.3) was used read only. `pytest` was not installed
anywhere at the time, so the commands above run under `unittest`.

The packaging branch has since landed. Today the documented setup is
`python3 -m venv .venv` plus `python -m pip install -e ".[dev]"`, and the suite
runs with `python -m pytest`. The `venv/bin/python` commands above are the
record of what was run then, not instructions to follow now.

## Next steps

1. Migrate one notebook (`analyze_bodyweight_strength_evals.ipynb` is the best
   candidate, since it builds `set_records` and reads `weight.csv` by hand) and
   let that migration decide whether a variant to lift mapping helper belongs
   here.
2. If a second notebook needs the same mapping, add it as an explicit caller
   supplied dict (`dataset.with_lifts({...})`), not a built in taxonomy.
3. Once `codex/repo-foundation` lands, run this suite under `python -m pytest`
   and, if CI runs a matrix, include pandas 1.4 and pandas 3 so both ends of the
   supported range are executed rather than asserted.
4. Consider DEXA support once `codex/dexa-pipeline-split` settles the CSV schema
   and a fixture file exists to test against.
