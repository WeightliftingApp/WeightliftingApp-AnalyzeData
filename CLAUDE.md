# Claude Code guide

Follow [`AGENTS.md`](AGENTS.md) first. It is the shared instruction file for
Claude Code, Codex, Hermes, and other repository agents. The architecture and
notebook conventions are documented in
[`docs/analysis-architecture.md`](docs/analysis-architecture.md).

## Project overview

This repository analyzes Weightlifting App exports, bodyweight history, and DEXA
data. It contains tested Python modules, narrative Jupyter notebooks, and command
adapters. It is no longer a notebook-only project.

## Development setup

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the project, notebook tools, and test runner
python -m pip install -e ".[dev,notebooks]"

# Run notebooks
jupyter notebook src/

# Run the complete test suite from the repository root
python -m pytest
```

## Data files

- `data/*.wld`: Weightlifting App exports in JSON format
- `data/weight.csv`: bodyweight history with `Week of` and `Average` columns
- `data/dexa.csv` and `data/dexa_regions.csv`: normalized DEXA history

Personal data is ignored. Do not force-add it or copy its values into logs.

To update weight.csv from the source spreadsheet:
```bash
source .venv/bin/activate
python scripts/convert_weight_xlsx.py
```

## Architecture

Do not put new analysis logic in this file. Follow the detailed contract in
[`docs/analysis-architecture.md`](docs/analysis-architecture.md): reusable logic
belongs in modules, notebooks explain and display it, and scripts handle
repeatable execution and file output.

Prefer the canonical dataset:

```python
from training_dataset import load_training_dataset

data = load_training_dataset("data/example-chappy.wld")
```

Its table interface and normalization rules are in
[`docs/training-dataset.md`](docs/training-dataset.md).

### Schema module (`src/schema/`)

Dataclass hierarchy for parsing `.wld` files:

- **WLD**: root container for a raw export
  - `workouts: List[Workout]`: all workout sessions
  - `user: User`: user profile and settings
  - `typeList: List[str]`: exercise type definitions

- **Workout**: one workout session
  - `exercises: List[Exercise]`: exercises performed
  - `date: datetime`, `duration: int` (seconds), `name: str`
  - `volume()`: total volume; `numSets()`: total set count

- **Exercise**: one exercise within a workout
  - `sets: List[Set]`: individual sets
  - `displayName()`: full name including the iteration
  - `volume()`: exercise volume

- **Set**: one set with optional `reps`, `weight`, `duration`, `distance`,
  `volume`, `oneRM`, `rpe`, and `rir` fields

Direct schema traversal remains available for parsing work. New analyses should
start from the canonical dataset unless the nested export structure is itself
the subject of the analysis.
