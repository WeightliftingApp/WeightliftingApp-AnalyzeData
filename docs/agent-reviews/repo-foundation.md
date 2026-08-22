# Repository foundation review

## Result

The repository now uses `pyproject.toml` for build metadata, dependencies, editable installs, and pytest discovery. The editable install preserves `analysis_utils` and `schema` as top-level imports. Package discovery also covers the incoming `dexa` package, and the module list includes the incoming `training_dataset` and `training_program_analysis` modules. CI runs the tracked tests on Python 3.10 through 3.14.

No notebook files, chart code, DEXA behavior, or schema behavior changed.

## Judgment calls and ambiguities

- Python 3.10 is the minimum because the existing modules use `X | None` unions and built-in generic types. CI covers every minor release from 3.10 through the locally tested 3.14.
- `pandas`, `openpyxl`, `numpy`, and `matplotlib` are base dependencies because installed Python modules import them at runtime. This includes the incoming DEXA package. Jupyter, SciPy, and the remaining notebook tools are in the `notebooks` extra so CI does not install the full interactive stack.
- `tqdm` was added to the notebook dependency group even though it was absent from the old requirements file. A tracked notebook imports it directly.
- `pytest` is the sole development dependency. The tests use `unittest`, but pytest discovers them without requiring `tests/__init__.py` and gives one root-level verification command.
- The conversion scripts remain repository scripts rather than installed commands. `scripts.convert_dexa_xlsx` works during root-level test runs because the repository root is on the test runner's import path. If these scripts need to run from arbitrary directories, they should get package modules and console-script entry points in a separate change.
- The version remains `0.1.0` in static metadata. No release or publishing process exists, so adding dynamic version tooling would create machinery with no current user.
- `training_dataset` and `training_program_analysis` are declared before their source files arrive in this worktree. Setuptools permits the editable install, and the declarations make the integrated tree install both modules without another packaging change.

## Rejected alternatives

- Adding `PYTHONPATH=src`, a `conftest.py` path mutation, or pytest's `pythonpath` option would hide the missing package metadata. The editable install now provides the imports directly.
- Keeping `requirements.txt` beside matching `pyproject.toml` entries would create two dependency lists that could drift. All dependency groups now live in `pyproject.toml`.
- Exact transitive pins were not added. This repository has no lockfile or release reproducibility requirement, and broad direct dependencies allow Python-version-appropriate wheels to resolve.
- CI does not execute notebooks. Notebook execution can be slow, can rewrite output JSON, and may depend on personal data that is absent from the repository.

## Shortcuts and known issues

- Validation used Python 3.14.5 locally. The other supported versions are covered by the CI matrix rather than separate local interpreters.
- The baseline `python3 -m unittest discover -v` command reported zero tests because the test directory is not an importable package. The documented `python -m pytest` command collects all 13 tracked tests.
- The CI actions use current major release tags rather than commit SHAs. Pinning action SHAs would tighten supply-chain controls, but it would also require a maintenance process for updates.

## Commands run

```text
python3 -m unittest discover -v
# Baseline: 0 tests discovered.

python3 -m venv .venv
# Passed.

.venv/bin/python -m pip install -e '.[dev]'
# Passed; editable package and test dependencies installed.

.venv/bin/python -m pip install -e '.[notebooks]'
# Passed; notebook dependency group installed on Python 3.14.5.

.venv/bin/python -c 'import joypy, jupyter, matplotlib, numpy, scipy, seaborn, tqdm; print("notebook dependencies import successfully")'
# Passed.

.venv/bin/python -m pip wheel --no-deps --wheel-dir /tmp/repo-foundation-wheel-a5219cfc .
# Passed; built weightlifting_app_analysis-0.1.0-py3-none-any.whl.

.venv/bin/python -m pytest -q
# Passed: 13 tests.

cd /tmp && <workspace>/.venv/bin/python -c 'from analysis_utils import calculate_workout_streaks; from schema import WLD; print(calculate_workout_streaks.__name__, WLD.__name__)'
# Passed from outside the repository: calculate_workout_streaks WLD.

.venv/bin/python -m pip check
# Passed: no broken requirements.

git diff --check
# Passed.
```

## Potential edge cases

- Future Python releases are allowed by `requires-python = ">=3.10"` but are not in the matrix until they are stable and dependency wheels are available.
- Notebook imports are not covered by a smoke test. A stale or missing notebook-only dependency could escape the unit suite.
- The editable install exposes source edits immediately. A future publishing workflow should also build and test a wheel to catch missing package data.

## Recommended next steps

1. Add a non-mutating notebook smoke test if notebook dependency drift becomes a recurring problem.
2. Package the spreadsheet converters behind console-script entry points if users need to invoke them outside a repository checkout.
3. Add a lock or constraints workflow only if reproducible notebook environments become more important than broad compatibility.
