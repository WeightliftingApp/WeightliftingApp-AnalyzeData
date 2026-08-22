# Chart design language v2 review ledger

This ledger records implementation decisions and review findings for the second design-language pass. Update it as work progresses. Generated comparisons and personal inputs remain ignored.

## Scope

- Define hero, comparison, and diagnostic chart archetypes.
- Add shared formatting, annotation, direct-label, and uncertainty primitives.
- Add structural lint checks and deterministic golden examples.
- Upgrade the highest-impact notebook charts: big-three progression, PR timing, Wilks diagnostics, workout intensity, and the all-user bench distribution.
- Preserve calculations, observations, units, and source data.

## Baseline

The 26 notebook images produced after the first shared-style migration were copied unchanged to `.artifacts/chart-baselines/2026-08-22-pre-design-language-v2/`. This baseline is ignored and will be paired with the v2 render before review.

## Initial audit

### What already works

- The paper and panel colors, editorial title, monospace metadata, restrained grid, and semantic highlights are coherent.
- The DEXA topography, Pareto frontier, bulk forecast, and muscle-gain estimate already read as complete analytical cards.
- The comparison tooling preserves image inventory and exposes renderer drift.

### Problems to address

- One frame treatment is carrying hero findings, ordinary comparisons, and dense diagnostics.
- Several notebook titles and subtitles lack a consistent hierarchy, even when their descriptive wording should remain.
- Dense multi-series charts rely on legends even when endpoint labels would be easier to follow.
- The workout-intensity chart uses three y axes, which makes scale association unnecessarily difficult.
- Percentile and uncertainty conventions are chart-specific instead of shared.
- The style module has no structural linting for missing units, default colors, excessive date ticks, clipped figure text, or footer collisions.

## Decisions and judgment calls

- Keep chart-specific calculations in their notebooks and generators. Shared code may own visual grammar but may not infer domain meaning.
- Extend `notebook_frame` with an explicit archetype while preserving its current comparison behavior as the default.
- Keep titles descriptive and close to the established notebook voice. Put findings in annotations and explanatory context in subtitles or footers.
- Use direct labels for a small number of lines. Keep legends when labels would collide or when marks do not have meaningful endpoints.
- Replace the three-axis workout-intensity view with aligned stacked panels because all measures share time but not units.
- Keep categorical colors where categories are the subject. Use neutral context plus one accent when the chart has a single intended finding.
- Lint objective structure only. The linter will not pretend to judge whether a title is insightful or whether a semantic color choice is scientifically correct.
- Increase the Wilks and workout-intensity cards from 15 by 6 inches to 15 by 9 inches. Three aligned panels need vertical space; preserving the old height would make each scale harder to read.
- Keep the existing lower-right legend on the lifetime big-three chart. Direct endpoint labels competed with the chart's July-value annotations during full-size review. The one-year projection chart has open right-side space and keeps direct labels.
- Describe the PR pattern as repeated annual peaks, not seasonal peaks. The chart marks one peak in each July-to-June window, but the peak month moves enough that a seasonal claim is not supported.
- Use the shared `REFERENCE` tag for the histogram's mean and upper-percentile thresholds. They share one semantic role and are distinguished by direct text rather than decorative colors.
- Apply the shared `LATEST`, `REFERENCE`, `ESTIMATE`, and interval primitives to the DEXA muscle-gain card so the strongest existing analysis also exercises the new language.
- The first v2 pass made several titles into headline conclusions. User review found that tone too prescriptive, so the titles were restored to descriptive names without reverting the layouts, annotations, uncertainty treatment, or stacked panels.

## Shortcuts

- The migration script targets exact reviewed notebook cells instead of trying to infer a chart's archetype or rewrite prose automatically. This is intentionally narrow and idempotent.
- Only five priority notebook groups received bespoke narrative changes. The remaining notebook charts retain the v1 shared frame and are visible in the v2 gallery as unchanged controls.
- Structural lint runs on deterministic reference cards and focused tests. Existing published cards are not all forced through identical lint settings because multi-panel cards legitimately omit repeated x labels and some diagnostic axes are unitless.

## Issues and ambiguities

- Notebook charts depend on ignored personal datasets. Final visual validation requires executing against those local inputs without committing or linking them.
- Some historical notebook outputs were rendered under different Matplotlib versions. Comparisons must distinguish renderer drift from design changes.
- "Highest-impact" is interpreted as the five chart groups named in the design audit. Other notebooks will inherit the new primitives but will not all receive bespoke narrative rewrites in this pass unless a shared migration applies safely.
- The first direct-label attempt on the lifetime big-three chart collided with existing July annotations. Visual review rejected it even though the helper's endpoint-label collision check passed; that check cannot reason about unrelated annotations.
- The first golden hero and comparison titles collided with metadata or exceeded the canvas. The new linter caught both before the examples were accepted.
- Several embedded PNG dimensions changed by a few pixels because Matplotlib crops notebook output around new text extents. The two stacked redesigns intentionally changed height by roughly 50 percent. The v2 report records every before and after dimension.
- The all-user archive remains the slowest validation input. Its notebook executed successfully but took several minutes.
- Headless execution stored 766 transient tqdm frames while loading the all-user archive. The migration removes only those progress frames and retains the final loaded-file summary, chart, and analysis output.

## Validation log

- Preserved 26 v1 notebook PNGs before implementation.
- Rendered and linted deterministic hero, comparison, and diagnostic cards at 1400 by 840 pixels.
- Focused design-system tests passed after the primitive implementation.
- Executed all five changed notebooks against the local ignored data. They produced 14 images and no notebook error outputs.
- Built the v1-to-v2 gallery with 26 baselines, 26 current images, 26 pairs, no missing images, and no additions. Twelve images changed; the other fourteen serve as unchanged controls.
- Reviewed the complete overview and the big-three, PR, user-distribution, Wilks, workout-intensity, golden-example, and DEXA images at full size.
- Regenerated the DEXA muscle-gain report and chart from the nine local scans after adopting the shared annotation and interval primitives. The estimate remains 1.4 lb unrounded with a model-based 95% interval of -2.8 to +6.1 lb.
- After title-tone review, restored descriptive titles across the five priority notebook groups and three golden cards, re-executed all five notebooks, and rebuilt the complete 26-pair comparison gallery.
- Final repository suite: 237 tests and 46 subtests passed in the integration environment.

## Next steps

1. Decide whether the two remaining multi-axis Wilks cards should also become stacked panels. They align original and adjusted lift values closely enough that the current twin axes remain defensible.
2. Consider a separate pass on the PR heatmap, bodyweight ridgeline, and dense workout scatter charts. They were unchanged controls in this pass.
3. Add an accessibility review with grayscale and common color-vision simulations if these charts will be published outside the notebooks.
4. Rebuild the gallery after Matplotlib, pandas, or JoyPy upgrades.
5. If the design direction is accepted, extend archetype declarations and descriptive title hierarchy to the unchanged controls in a separate reviewable pass.
