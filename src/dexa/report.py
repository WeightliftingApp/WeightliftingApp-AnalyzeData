"""Pure Markdown rendering for DEXA analysis results."""

from __future__ import annotations

from .calculations import DexaAnalysis


def render_markdown(
    analysis: DexaAnalysis,
    lean_mass_chart_filename: str = "dexa-lean-mass-vs-bodyweight.png",
) -> str:
    """Render the report without reading or writing files."""
    latest = analysis.latest
    previous = analysis.previous
    delta = analysis.delta

    reg_lines = []
    for region in analysis.latest_regions.index:
        old = analysis.prior_regions.loc[region]
        new = analysis.latest_regions.loc[region]
        reg_lines.append(
            f"| {region} | {old.fat_mass_lb:.1f} → {new.fat_mass_lb:.1f} "
            f"({new.fat_mass_lb-old.fat_mass_lb:+.1f}) | "
            f"{old.lean_soft_tissue_lb:.1f} → {new.lean_soft_tissue_lb:.1f} "
            f"({new.lean_soft_tissue_lb-old.lean_soft_tissue_lb:+.1f}) | "
            f"{new.body_fat_pct:.1f}% |"
        )

    latest_date = latest["date"].date().isoformat()
    previous_date = previous["date"].date().isoformat()
    return f"""# DEXA analysis — {latest_date}

## Bottom line

This was an excellent six-week cut: **{analysis.total_loss:.1f} lb down**, including **{analysis.fat_loss:.1f} lb of fat** and **{analysis.lean_loss:.1f} lb of measured lean tissue**. About **{analysis.fat_share:.0%} of the scale loss came from fat**. Body fat fell from **{previous.body_fat_pct:.1f}% to {latest.body_fat_pct:.1f}%** ({latest.body_fat_pct-previous.body_fat_pct:+.1f} percentage points), while normalized FFMI remained **{latest.normalized_ffmi:.2f}**.

## Lean mass vs. bodyweight

![DEXA lean mass versus bodyweight]({lean_mass_chart_filename})

Each label shows measured lean tissue minus the full-history trend at that bodyweight. The dated arrows connect scans in order. The background lines model body fat in 1-point steps while holding bone mass at the latest measured value of **{latest.bone_mineral_content_lb:.1f} lb**.

## Versus {previous_date}

| Metric | Previous | Current | Change |
|---|---:|---:|---:|
| Total mass | {previous.weight_lb:.1f} lb | {latest.weight_lb:.1f} lb | {delta.weight_lb:+.1f} lb |
| Fat mass | {previous.fat_mass_lb:.1f} lb | {latest.fat_mass_lb:.1f} lb | {delta.fat_mass_lb:+.1f} lb |
| Lean tissue | {previous.lean_soft_tissue_lb:.1f} lb | {latest.lean_soft_tissue_lb:.1f} lb | {delta.lean_soft_tissue_lb:+.1f} lb |
| Bone mineral content | {previous.bone_mineral_content_lb:.1f} lb | {latest.bone_mineral_content_lb:.1f} lb | {delta.bone_mineral_content_lb:+.1f} lb |
| Body fat | {previous.body_fat_pct:.1f}% | {latest.body_fat_pct:.1f}% | {delta.body_fat_pct:+.1f} pp |
| FFMI | {previous.ffmi:.2f} | {latest.ffmi:.2f} | {delta.ffmi:+.2f} |

## Regional changes

| Region | Fat mass | Lean tissue | Current fat % |
|---|---:|---:|---:|
{chr(10).join(reg_lines)}

## Standards comparison

- **Body fat:** BodySpec places men aged 20–29 below 16% in the lowest-body-fat quintile. GE Lunar reference data put 20–29-year-old men at 14.0% around the leanest 20% and 11.0% around the leanest 10%; **13.1% is approximately the leanest 10–20% of peers**.
- **FFMI:** **25.31 raw / 25.13 height-normalized** is exceptionally muscular. The popular “FFMI 25 natural limit” is a heuristic, not a medical cutoff; this result says “very advanced muscularity,” not “proof of anything.”
- **BMI:** 29.13 technically reads “overweight” and nearly “obese,” but is clearly misleading here because measured body fat is only 13.1%.
- **Fat distribution:** A/G improved **0.65 → 0.59** and remains safely below BodySpec’s <1.0 target. It is still somewhat more android-weighted than the 0.47 mean reported for 20–29-year-old men, but the direction is good.
- **VAT:** **0.47 lb (213 g; 13.65 in³ / ~224 cm³)** is far below the proposed **1,000 g** cardiometabolic-risk cutoff for men under 40 and below the ~542 g mean in healthy men aged 20–30. However, the jump from 0.03 lb is internally odd while all other abdominal-fat measures improved; treat the prior reading or the delta as an algorithm/segmentation anomaly until another scan confirms it.
- **Bone:** Total BMD **1.616 g/cm²**, T-score **4.1**, Z-score **4.1** is extraordinarily high. The small drop from 1.649/4.4 over six weeks is not biologically meaningful and is almost certainly measurement variation. BodySpec explicitly says this whole-body estimate is not a diagnostic bone-density exam.
- **Symmetry:** Arms are exactly balanced at **13.9 lb lean per side**. Legs differ by only **0.4 lb lean** (right 28.8, left 28.4), well under BodySpec’s >2 lb concern threshold.

## Honest read

### Highlights

1. **The cut worked.** Losing 6.6 lb of fat in six weeks while retaining 177.4 lb of lean tissue is a strong outcome.
2. **Central fat moved in the right direction.** Trunk fat fell 4.0 lb, android fat fell 0.6 lb, and A/G improved.
3. **You remain unusually muscular.** Current fat-free mass (186.6 lb) is only 1.8 lb below your all-time DEXA high despite being 8.4 lb lighter than six weeks ago.
4. **No meaningful limb imbalance.** Symmetry is excellent.

### Lowlights / watch items

1. **The 1.9 lb lean-tissue loss is real on the printout.** It is not alarming, and some is likely glycogen/water, but it is not zero. Arms account for 1.1 lb of it, making upper-body retention the main thing to watch.
2. **VAT is the weird number.** The absolute level is healthy; the 0.03 → 0.47 lb change conflicts with the rest of the scan and should not be interpreted as a true 16× visceral-fat gain without replication.
3. **You are lean, not stage lean.** 13.1% is excellent general/athletic condition, but a bodybuilding stage target would still require materially more fat loss.
4. **Do not chase the bone-score decimal.** 4.4 → 4.1 is noise over this interval, not declining bone health.

## Practical next move

If the goal is maintenance, stop pressing the deficit and stabilize around **213–216 lb** while restoring training performance and glycogen. If the goal is a serious bodybuilding cut, the scan implies roughly **7–11 additional lb of fat loss** to reach about **10%–8% DEXA body fat**, assuming lean mass holds. Either way, prioritize upper-body training performance, protein, sleep, and repeat the next scan under matched hydration/food/training conditions.

## Sources and caveats

- BodySpec report dated 2026-08-21; report states DXA body-composition accuracy of approximately ±0.5% and provides its own age/sex body-fat bands.
- Imboden et al., *Reference standards for body fat measures using GE dual energy x-ray absorptiometry in Caucasian adults* (PLOS One, 2017): https://pmc.ncbi.nlm.nih.gov/articles/PMC5384668/
- Miazgowski et al., *Visceral fat reference values… aged 20–30 years* (PLOS One, 2017): https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0180614
- Rothney et al./related age- and sex-specific DXA VAT risk work: proposed VAT cutoff of 1,000 g for men under 40: https://www.nature.com/articles/s41366-021-00743-3
- Cross-scan lean-tissue changes include water and glycogen, not just contractile muscle. Device/software, positioning, food, hydration, caffeine, and recent training can affect results.
"""
