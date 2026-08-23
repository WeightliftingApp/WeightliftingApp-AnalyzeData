# Analysis architecture

This repository supports two ways to consume the same analysis: a person can
read and explore a notebook, or a repeatable command can generate results. The
calculation should not depend on which adapter called it.

```text
source adapter
      |
      v
tested analysis module
      |
      +-------------------+
      |                   |
      v                   v
notebook adapter      script adapter
explain and display   save and automate
```

## Responsibilities

### Modules under `src/`

Modules are the source of truth for reusable behavior. Put these here:

- parsing and normalization;
- calculations and statistical models;
- summary-table construction;
- chart functions that return figures;
- report data structures and orchestration that can run without a notebook.

A useful module has a small interface that hides enough implementation to pay
for itself across notebooks, scripts, and tests. Prefer functions that accept
data or explicit dependencies and return results. Do not hide database calls,
home-directory paths, or file writes inside calculation functions.

`src/dexa/` is the clearest current example. Its ingestion, calculations,
charts, pipelines, and reports can be called by small scripts. The canonical
training dataset in `src/training_dataset.py` gives analyses a shared normalized
view of workout, exercise, set, and bodyweight data.

### Notebooks under `src/`

Notebooks own the human reading experience:

- the question being answered;
- measurement definitions and assumptions;
- interactive exploration;
- the order in which evidence appears;
- selected tables, charts, and conclusions.

Notebook cells should call modules for stable calculations. A notebook may hold
short exploratory code while the question is still changing. Extract that code
once it needs a test, is reused, or becomes part of a trusted result.

Committed notebook output is a deliberate publishing choice, not a cache. Keep
it when a reader benefits from seeing the result without rerunning private data.
Avoid unrelated kernel metadata changes and large debugging output.

### Scripts under `scripts/`

Scripts own repeatable execution:

- command-line arguments and validation;
- selection of a data-source adapter;
- local paths and environment integration;
- calls into analysis modules;
- saving files and choosing exit status.

Scripts should be thin. If a calculation is only testable by running a command
or reading a generated file, move it into a module that returns the result.

## Source-adapter seams

Training data currently comes from more than one source, including WLD exports,
CSV files, and live database queries. That variation justifies a source-adapter
seam. Each adapter should produce the documented canonical tables or another
explicit input interface. The analysis should not know which source produced
them.

Do not place live query commands inside calculation modules. A notebook or
script may select the adapter, but normalized data should cross the seam.

See [`training-dataset.md`](training-dataset.md) for the current canonical table
interface.

## Figures and file output

Chart functions should return a Matplotlib `Figure` or operate on an explicit
axis. The calling notebook or script decides whether to display or save it.
Shared titles, annotation patterns, colors, and formatters belong in
`src/chart_style.py` and are documented in [`chart-style.md`](chart-style.md).

Generated-file policy:

- `outputs/` is ignored run output derived from local or personal data;
- `.artifacts/` is ignored visual-QA evidence and temporary comparison output;
- durable tracked artifacts require an explicit decision and provenance.

The repository contains a few older tracked images in `outputs/`. They are
historical exceptions, not the default for new files.

## Testing

Test through the same module interface used by notebooks and scripts:

- calculation tests cover domain and statistical behavior;
- chart tests cover semantics and shared-style rules;
- script tests cover argument handling and a small end-to-end path;
- notebook tests cover structure, imports, and execution where practical.

Do not repeat the same numerical assertions at every adapter. One strong module
test plus small adapter checks gives better failure messages and less upkeep.

## How an analysis graduates

1. Explore the question in a notebook.
2. Extract stable or test-worthy behavior into an importable module.
3. Leave the notebook as the narrative adapter over that module.
4. Add a script only when headless regeneration or automation has value.

There must be one source of truth. A percent-format `.py` export beside a
notebook is acceptable as a generated file, but it should not be hand-maintained
or committed as a second implementation.

## Current follow-up

`src/analyze_training_program.py` and
`src/analyze_training_program.ipynb` currently duplicate nearly all executable
analysis code. Refactor them by moving orchestration and chart construction into
modules, moving the command adapter to `scripts/`, and leaving the notebook as
the explanatory caller. Apply the same pattern to older notebooks when their
analysis changes; do not rewrite every notebook solely for structural purity.
