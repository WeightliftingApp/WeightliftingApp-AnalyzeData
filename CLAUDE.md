# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Analysis scripts for data exported from [Weightlifting App](https://apps.apple.com/us/app/weightlifting-app/id1266077653). The project consists of Jupyter notebooks that analyze workout data stored in `.wld` files (JSON format).

## Development Setup

```bash
# Create/activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run notebooks
jupyter notebook src/
```

## Data Files

- `data/*.wld` - Workout data exports from Weightlifting App (JSON format)
- `data/weight.csv` - Body weight tracking data with columns: `Week of` (date), `Average` (weight in lbs)

To update weight.csv from the source spreadsheet:
```bash
source venv/bin/activate && python scripts/convert_weight_xlsx.py
```

## Architecture

### Schema Module (`src/schema/`)

Dataclass hierarchy for parsing `.wld` files:

- **WLD** - Root container. Load with `WLD(file_path="../data/example-chappy.wld")`
  - `workouts: List[Workout]` - All workout sessions
  - `user: User` - User profile and settings
  - `typeList: List[str]` - Exercise type definitions

- **Workout** - Single workout session
  - `exercises: List[Exercise]` - Exercises performed
  - `date: datetime`, `duration: int` (seconds), `name: str`
  - `volume()` - Total workout volume, `numSets()` - Total set count

- **Exercise** - Single exercise within a workout
  - `sets: List[Set]` - Individual sets
  - `displayName()` - Full name including iteration (e.g., "Incline Dumbbell Bench Press")
  - `volume()` - Exercise volume

- **Set** - Individual set with optional fields: `reps`, `weight`, `duration`, `distance`, `volume`, `oneRM`, `rpe`, `rir`

### Notebook Pattern

Notebooks in `src/` follow this pattern:
```python
from schema import WLD
wld = WLD(file_path="../data/example-chappy.wld")

# Access data
for workout in wld.workouts:
    for exercise in workout.exercises:
        for set_data in exercise.sets:
            # Analyze set_data.weight, set_data.reps, set_data.oneRM, etc.
```
