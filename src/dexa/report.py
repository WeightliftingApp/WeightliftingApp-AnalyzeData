"""Pure, data-only Markdown rendering for DEXA analysis results."""

from __future__ import annotations

from .calculations import DexaAnalysis


def _regional_table(analysis: DexaAnalysis) -> str:
    lines = []
    for region in analysis.latest_regions.index:
        old = analysis.prior_regions.loc[region]
        new = analysis.latest_regions.loc[region]
        lines.append(
            f"| {region} | {old.fat_mass_lb:.1f} → {new.fat_mass_lb:.1f} "
            f"({new.fat_mass_lb-old.fat_mass_lb:+.1f}) | "
            f"{old.lean_soft_tissue_lb:.1f} → {new.lean_soft_tissue_lb:.1f} "
            f"({new.lean_soft_tissue_lb-old.lean_soft_tissue_lb:+.1f}) | "
            f"{new.body_fat_pct:.1f}% |"
        )
    return "\n".join(lines)


def _interval_label(analysis: DexaAnalysis) -> str:
    days = (analysis.latest["date"] - analysis.previous["date"]).days
    if days > 0 and days % 7 == 0:
        weeks = days // 7
        unit = "week" if weeks == 1 else "weeks"
        return f"{weeks} {unit}"
    unit = "day" if days == 1 else "days"
    return f"{days} {unit}"


def _change_sentence(label: str, previous: float, latest: float, suffix: str) -> str:
    change = latest - previous
    if change > 0:
        direction = "rose"
    elif change < 0:
        direction = "fell"
    else:
        return f"{label} was unchanged at {latest:.1f}{suffix}."
    return f"{label} {direction} {abs(change):.1f}{suffix} to {latest:.1f}{suffix}."


def render_markdown(
    analysis: DexaAnalysis,
    lean_mass_chart_filename: str = "dexa-lean-mass-vs-bodyweight.png",
) -> str:
    """Render only facts available in the analysis CSVs."""
    latest = analysis.latest
    previous = analysis.previous
    delta = analysis.delta
    latest_date = latest["date"].date().isoformat()
    previous_date = previous["date"].date().isoformat()
    interval = _interval_label(analysis)
    change_summary = " ".join(
        [
            _change_sentence(
                "Total mass", previous.weight_lb, latest.weight_lb, " lb"
            ),
            _change_sentence(
                "Fat mass", previous.fat_mass_lb, latest.fat_mass_lb, " lb"
            ),
            _change_sentence(
                "Lean tissue",
                previous.lean_soft_tissue_lb,
                latest.lean_soft_tissue_lb,
                " lb",
            ),
        ]
    )

    return f"""# DEXA analysis - {latest_date}

## Bottom line

Over {interval}, {change_summary} Body fat changed from **{previous.body_fat_pct:.1f}% to {latest.body_fat_pct:.1f}%** ({delta.body_fat_pct:+.1f} percentage points). Normalized FFMI changed from **{previous.normalized_ffmi:.2f} to {latest.normalized_ffmi:.2f}**.

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
{_regional_table(analysis)}

## Available standards data

- **Body fat:** The current CSV value is **{latest.body_fat_pct:.1f}%**, compared with {previous.body_fat_pct:.1f}% on the previous scan.
- **FFMI:** The current values are **{latest.ffmi:.2f} raw / {latest.normalized_ffmi:.2f} height-normalized**.
- **BMI:** The current value is **{latest.bmi:.2f}**. BMI does not distinguish fat mass from lean mass.

## Supplemental interpretation unavailable

The input CSVs do not contain VAT, total BMD, A/G ratio, side-specific limb measurements, demographic context, or goals. Claims and recommendations based on those fields are omitted.

## Caveat

Cross-scan lean-tissue changes include water and glycogen, not just contractile muscle. Device/software, positioning, food, hydration, caffeine, and recent training can affect results.
"""
