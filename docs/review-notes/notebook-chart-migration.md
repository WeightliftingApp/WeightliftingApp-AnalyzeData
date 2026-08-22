# Notebook chart migration review

## Coverage

All 23 chart-producing cells in the repository's 10 chart notebooks now use the shared chart frame and theme. `analyze_workout_streaks.ipynb` contains no chart output, so it needed no migration.

The ignored comparison archive contains 27 original images and 26 current images. Every original is paired. `analyze_users.ipynb` previously retained two versions of the same histogram in separate cell outputs; both originals map to the one current histogram. This is the only count difference.

## Visual review

The overview and all paired sheets were regenerated from the executed notebooks on 2026-08-22. The current charts preserve the original data series, annotations, reference lines, legends, and axis meanings while adopting the warm paper background, stronger hierarchy, shared blue accent, quieter grid, and compact metadata treatment.

No missing charts, clipped labels, or empty axes were found. The four bodyweight strength charts written to `outputs/` during execution were restored because this pass changes notebook output only.

## Judgment calls and compatibility work

- Existing chart-specific colors were retained where they encode exercises, series, or categories. The shared theme controls structure and neutral colors without erasing useful distinctions.
- Figure dimensions were adjusted when the shared title and metadata frame needed more room. The comparison report records those size changes.
- `analyze_weight_distribution.ipynb` includes a narrow compatibility shim for JoyPy 0.2.6 with pandas 3. JoyPy expects a list where pandas 3 exposes a generator. The shim changes iteration only, not the plotted data.
- Notebook execution reads the ignored local datasets. No personal data files or temporary links are committed.

## Review artifacts

- `.artifacts/chart-comparisons/notebooks/overview.png` is the quickest scan of all pairs.
- `.artifacts/chart-comparisons/notebooks/gallery.md` links each full-size pair.
- `.artifacts/chart-comparisons/notebooks/comparison-report.json` records dimensions, hashes, renderer versions, and pairing status.
- `.artifacts/chart-baselines/2026-08-22-notebooks-pre-shared-style/` contains the untouched originals.

## Reproduction

After executing the notebooks with the local datasets available:

```bash
.venv/bin/jupyter nbconvert --to markdown \
  --output-dir .artifacts/chart-comparisons/notebooks/after \
  src/*.ipynb
PYTHONPATH=src:. .venv/bin/python scripts/compare_notebook_charts.py
PYTHONPATH=src:. .venv/bin/python -m pytest -q
```

The comparison command must report `all_images_paired: true`, `baseline_count: 27`, `after_count: 26`, and `paired_count: 27`.

## Remaining risks

- Matplotlib, pandas, or JoyPy upgrades can change raster layout even when chart semantics remain intact. Rebuild the gallery after dependency changes.
- Dense legends and date labels remain sensitive to narrower render targets. The committed notebook outputs are the reviewed dimensions.
- The comparison script checks inventory and image metadata. Human review is still required for semantic changes that produce a valid image.
