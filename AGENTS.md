# Agent guide

Read this file before changing the repository. Detailed analysis structure lives
in [`docs/analysis-architecture.md`](docs/analysis-architecture.md), and chart
rules live in [`docs/chart-style.md`](docs/chart-style.md).

## Repository contract

- Put reusable calculations, normalization, models, summaries, and chart
  construction in importable modules under `src/`.
- Treat notebooks as narrative adapters. They should state the question and
  assumptions, call tested modules, and display selected results.
- Treat files under `scripts/` as operational adapters. They may parse
  arguments, load data, call modules, save output, and set an exit status.
- Never maintain the same analysis independently in a notebook and a Python
  script. Extract shared behavior into a module, then call it from both.
- Prefer the canonical training dataset from `training_dataset.py` over walking
  the nested WLD schema in each analysis.
- Keep reusable chart behavior in `chart_style.py`. Follow `docs/chart-style.md`
  for titles, annotations, colors, output sizes, and visual comparison.
- Add calculation tests at the module interface. Use smoke or structural tests
  for notebook and script adapters rather than duplicating numerical tests.

## Generated files and personal data

- `data/` is private and ignored except for explicitly tracked example data.
- `outputs/` contains reproducible run output derived from personal data and is
  ignored by default. Do not force-add it without an explicit review decision.
- `.artifacts/` contains temporary chart comparisons, notebook renders, and
  visual-QA evidence. It is ignored and may be regenerated.
- A durable artifact that belongs in Git should go in a purpose-named location,
  include its provenance, and be added deliberately.
- Do not commit secrets, local credential files, database dumps, or personal
  exports.

## Notebook discipline

- Exploration may begin in a notebook. Once logic needs a test, is reused, or
  becomes a trusted result, move it into a module.
- Do not import one notebook from another.
- Avoid unrelated kernel metadata churn. Do not commit a Python-version-only
  notebook change.
- Keep committed output only when it helps a reader understand a durable
  analysis. Put bulk renders and before/after comparisons in `.artifacts/`.
- When changing a chart, preserve a baseline render and compare it using the
  workflow in `docs/chart-style.md`.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,notebooks]"
python -m pytest
```

Run commands from the repository root. Keep source changes and generated output
separate when reviewing or committing work.

## Local credentials

Recurring credentials are cached locally so Superset/Codex sessions do not
trigger repeated 1Password CLI authorization prompts.

- Reverse Contact: `~/.config/reverse-contact/credentials.json` with `username`
  and `password` fields.
- Load cached values directly into process or shell variables. Never print,
  display, log, or paste the values into chat or tool output.
- Do not invoke `op` for Reverse Contact unless the cache is missing or the
  credential has been rotated. Refresh it with
  `~/.hermes/scripts/refresh_reverse_contact_secrets.py`.

## Writing standard

- Apply the `unslop` skill to every user-facing response and prose artifact,
  including status updates, plans, documentation, PR descriptions, and commit
  messages. Read `~/.agents/skills/unslop/SKILL.md` once at the start of each
  session, then self-audit final prose against it before sending.
- Preserve exact code, commands, quotations, required templates, and technical
  meaning. Do not announce the unslop pass unless the user asks.
