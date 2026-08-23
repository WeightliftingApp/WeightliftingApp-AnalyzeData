# %% [markdown]
# # Full-history training style, muscle volume, frequency, and press progression
#
# **Question:** Does the current split/program fit the observed training response,
# or should muscle-group frequency and volume change?
#
# ## Measurement contract
#
# - Source: live read-only BenchTracker/Postgres corpus, not the slightly stale local `.wld` export.
# - Grain: one source set. A **recorded set** has positive reps. The source does not identify warm-ups,
#   failure proximity, or reliably populated RPE/RIR, so this analysis does **not** call these “hard sets.”
# - Direct volume: sets logged under the app's exercise category.
# - Estimated stimulus-equivalent sets: 1.0 for a primary group plus 0.5 for common compound secondaries.
#   This is an auditable planning heuristic, not physiology measured in a lab.
# - Frequency: distinct workout sessions touching a category, not workout names.
# - Press progression: like-for-like session-best estimated 1RM; variants are not mixed.
# - “Current” = rolling 12 weeks ending at the latest recorded workout; compared with the preceding 12 weeks.

# %%
from pathlib import Path
import io
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

REPO = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd().parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from training_program_analysis import (
    add_press_family,
    estimate_muscle_stimulus,
    prepare_set_records,
    summarize_category_window,
)
from chart_style import (
    CATEGORICAL_COLORS,
    NOTEBOOK_AXES,
    PALETTE,
    add_footer,
    add_header,
    chart_canvas,
    notebook_frame,
    style_axes,
    style_legend,
)

OUTPUTS = REPO / "outputs"
OUTPUTS.mkdir(exist_ok=True)
Q_SH = Path.home() / ".agents/skills/weightlifting/scripts/q.sh"

# %%
QUERY = r"""
SELECT
  w.id AS workout_id,
  w.uuid AS workout_uuid,
  w.date,
  w.name AS workout_name,
  w.duration_seconds,
  e.id AS exercise_id,
  e.exercise_order,
  e.name,
  e.category,
  e.style,
  COALESCE(e.iteration, '') AS iteration,
  s.id AS set_id,
  s.set_order,
  s.reps,
  s.weight,
  s.volume,
  s.one_rm
FROM wl_workouts w
JOIN wl_exercises e ON e.workout_id = w.id
JOIN wl_sets s ON s.exercise_id = e.id
ORDER BY w.date, w.id, e.exercise_order, s.set_order;
"""
proc = subprocess.run([str(Q_SH), QUERY], check=True, capture_output=True, text=True)
csv_lines = [line for line in proc.stdout.splitlines() if line.strip() and line.strip() != "SET"]
raw = pd.read_csv(io.StringIO("\n".join(csv_lines)))
sets = add_press_family(prepare_set_records(raw))
recorded = sets[sets["is_recorded_set"] & sets["date"].notna()].copy()

latest = recorded["date"].max()
first = recorded["date"].min()
current_start = latest - pd.Timedelta(days=12 * 7 - 1)
prior_end = current_start - pd.Timedelta(days=1)
prior_start = prior_end - pd.Timedelta(days=12 * 7 - 1)

coverage = pd.DataFrame({
    "metric": ["First workout", "Latest workout", "Workouts", "Training days", "Exercise instances", "All sets", "Positive-rep recorded sets"],
    "value": [first.date(), latest.date(), raw["workout_id"].nunique(), recorded["date"].nunique(),
              raw["exercise_id"].nunique(), len(raw), len(recorded)],
})
coverage

# %% [markdown]
# ## 1. Training style over time
#
# Annual counts reveal the macro style; rolling windows reveal the actual current program.
# Workout IDs—not names or dates—are used as session identifiers.

# %%
annual = (
    recorded.assign(year=recorded["date"].dt.year)
    .groupby("year")
    .agg(workouts=("workout_id", "nunique"), training_days=("date", "nunique"),
         recorded_sets=("set_id", "nunique"), tonnage=("volume", "sum"))
    .reset_index()
)
annual["sets_per_workout"] = annual["recorded_sets"] / annual["workouts"]
annual

# %%
def window_summary(frame, start, end, label):
    window = frame[frame["date"].between(start, end)]
    workouts = window["workout_id"].nunique()
    days = window["date"].nunique()
    durations = window[["workout_id", "duration_seconds"]].drop_duplicates()["duration_seconds"] / 60
    return {
        "period": label, "start": start.date(), "end": end.date(), "workouts": workouts,
        "workouts_per_week": workouts / 12, "training_days_per_week": days / 12,
        "recorded_sets_per_week": len(window) / 12,
        "sets_per_workout": len(window) / workouts if workouts else np.nan,
        "median_duration_min": durations.median(),
    }

period_summary = pd.DataFrame([
    window_summary(recorded, prior_start, prior_end, "Prior 12 weeks"),
    window_summary(recorded, current_start, latest, "Current 12 weeks"),
])
period_summary

# %%
current_categories = summarize_category_window(
    recorded, start=current_start, end=latest, window_weeks=12
).assign(period="Current 12 weeks")
prior_categories = summarize_category_window(
    recorded, start=prior_start, end=prior_end, window_weeks=12
).assign(period="Prior 12 weeks")
category_compare = pd.concat([prior_categories, current_categories], ignore_index=True)
category_compare.to_csv(OUTPUTS / "training-category-current-vs-prior.csv", index=False)
category_compare

# %%
frame = notebook_frame((16, 9))
with chart_canvas(frame) as (fig, seed_ax):
    fig.delaxes(seed_ax)
    axes = fig.subplots(2, 2)
    fig.subplots_adjust(wspace=0.32, hspace=0.35)
    for ax in axes.flat:
        ax.set_facecolor(PALETTE.panel)

    add_header(
        fig,
        frame,
        "Training Style and Direct Category Volume",
        "Annual workload and current-versus-prior 12-week category patterns",
        (),
    )
    axes[0, 0].plot(
        annual["year"], annual["workouts"], marker="o", lw=2.5,
        color=CATEGORICAL_COLORS[0],
    )
    axes[0, 0].set(
        title=f"Workouts per year ({latest.year} through {latest:%b %d})",
        xlabel="",
        ylabel="Sessions",
    )
    axes[0, 1].plot(
        annual["year"], annual["sets_per_workout"], marker="o", lw=2.5,
        color=CATEGORICAL_COLORS[1],
    )
    axes[0, 1].set(
        title=f"Recorded sets per workout ({latest.year} partial)",
        xlabel="",
        ylabel="Sets/session",
    )
    sns.barplot(
        data=category_compare, y="category", x="sets_per_week", hue="period",
        ax=axes[1, 0], palette=[PALETTE.checkpoint, PALETTE.frontier],
    )
    axes[1, 0].set(
        title="Direct recorded sets / week", xlabel="Sets/week", ylabel=""
    )
    sns.barplot(
        data=category_compare, y="category", x="sessions_per_week", hue="period",
        ax=axes[1, 1], palette=[PALETTE.checkpoint, PALETTE.positive],
    )
    axes[1, 1].set(
        title="Distinct sessions touching category / week",
        xlabel="Sessions/week",
        ylabel="",
    )
    for ax in axes.flat:
        style_axes(ax, NOTEBOOK_AXES)
    for ax in axes[1]:
        style_legend(ax, loc="lower right")
    add_footer(
        fig,
        frame,
        f"LIVE HISTORY: {first.date()} TO {latest.date()}",
        "RECORDED SET = POSITIVE REPS",
    )
    fig.savefig(
        OUTPUTS / "training-style-and-volume.png",
        dpi=180,
        facecolor=fig.get_facecolor(),
    )
    plt.show()

# %% [markdown]
# ## 2. Estimated muscle stimulus and frequency
#
# This supplements—never replaces—the direct-category table. Compound coefficients are
# intentionally simple and visible in `training_program_analysis.py`.

# %%
def expand_stimulus(frame):
    rows = []
    for row in frame.itertuples(index=False):
        for muscle, coefficient in estimate_muscle_stimulus(row.name, row.iteration, row.category).items():
            rows.append({"set_id": row.set_id, "workout_id": row.workout_id, "date": row.date,
                         "week_of": row.week_of, "muscle": muscle, "stimulus_sets": coefficient})
    return pd.DataFrame(rows)

current = recorded[recorded["date"].between(current_start, latest)].copy()
stimulus = expand_stimulus(current)
stimulus_summary = (
    stimulus.groupby("muscle")
    .agg(stimulus_sets=("stimulus_sets", "sum"), sessions=("workout_id", "nunique"))
    .assign(stimulus_sets_per_week=lambda x: x["stimulus_sets"] / 12,
            sessions_per_week=lambda x: x["sessions"] / 12)
    .sort_values("stimulus_sets_per_week", ascending=False).reset_index()
)
stimulus_summary.to_csv(OUTPUTS / "estimated-muscle-stimulus-current-12w.csv", index=False)
stimulus_summary

# %%
frequency_start = latest - pd.Timedelta(days=26 * 7 - 1)
category_days = (
    recorded[recorded["date"].between(frequency_start, latest)]
    [["category", "date", "workout_id"]].drop_duplicates().sort_values(["category", "date"])
)
gap_rows = []
for category, group in category_days.groupby("category"):
    days = pd.Series(sorted(group["date"].unique()))
    gaps = days.diff().dt.days.dropna()
    gap_rows.append({"category": category, "sessions": group["workout_id"].nunique(),
                     "sessions_per_week": group["workout_id"].nunique() / 26,
                     "median_days_between_hits": gaps.median(), "p90_days_between_hits": gaps.quantile(.9),
                     "longest_gap_days": gaps.max()})
frequency = pd.DataFrame(gap_rows).sort_values("sessions_per_week", ascending=False)
frequency.to_csv(OUTPUTS / "category-frequency-current-26w.csv", index=False)
frequency

# %%
recent26 = recorded[recorded["date"].between(frequency_start, latest)].copy()
weekly_heat = recent26.groupby(["week_of", "category"])["set_id"].nunique().unstack(fill_value=0).sort_index()
frame = notebook_frame((18, 9))
with chart_canvas(frame) as (fig, seed_ax):
    fig.delaxes(seed_ax)
    axes = fig.subplots(1, 2, gridspec_kw={"width_ratios": [1, 1.7]})
    fig.subplots_adjust(wspace=0.48)
    for ax in axes:
        ax.set_facecolor(PALETTE.panel)

    add_header(
        fig,
        frame,
        "Current Muscle-Group Stimulus and Frequency",
        "Estimated stimulus over 12 weeks and direct category volume over 26 weeks",
        (),
    )
    ordered_stimulus = stimulus_summary.sort_values("stimulus_sets_per_week")
    axes[0].barh(
        ordered_stimulus["muscle"],
        ordered_stimulus["stimulus_sets_per_week"],
        color=PALETTE.frontier,
    )
    axes[0].set(
        title="Estimated stimulus-equivalent sets / week\n(current 12 weeks)",
        xlabel="Estimated sets/week",
        ylabel="",
    )
    sns.heatmap(
        weekly_heat.T,
        cmap=sns.light_palette(PALETTE.frontier, as_cmap=True),
        ax=axes[1],
        cbar_kws={"label": "Direct recorded sets"},
    )
    axes[1].set(
        title="Direct category volume by week (latest 26 weeks)",
        xlabel="Week",
        ylabel="",
    )
    axes[1].tick_params(axis="y", labelsize=12, pad=4)
    labels = [
        date.strftime("%b %d") if index % 4 == 0 else ""
        for index, date in enumerate(weekly_heat.index)
    ]
    axes[1].set_xticks(np.arange(len(labels)) + 0.5)
    axes[1].set_xticklabels(labels, rotation=45, ha="right")
    for ax in axes:
        style_axes(ax, NOTEBOOK_AXES)
    add_footer(
        fig,
        frame,
        "SECONDARY COMPOUND WORK = 0.5 SET",
        "SOURCE LACKS WARM-UP AND PROXIMITY-TO-FAILURE FLAGS",
    )
    fig.savefig(
        OUTPUTS / "muscle-stimulus-and-frequency.png",
        dpi=180,
        facecolor=fig.get_facecolor(),
    )
    plt.show()

# %% [markdown]
# ## 3. What the current split actually looks like
#
# Generic workout names cannot identify a split. Each recent workout is instead described
# by categories touched and its dominant category by recorded-set count.

# %%
session_category = current.groupby(["workout_id", "date", "category"])["set_id"].nunique().rename("sets").reset_index()
session_wide = session_category.pivot_table(index=["workout_id", "date"], columns="category", values="sets", fill_value=0).reset_index()
category_columns = [c for c in session_wide.columns if c not in ("workout_id", "date")]
session_wide["total_sets"] = session_wide[category_columns].sum(axis=1)
session_wide["dominant_category"] = session_wide[category_columns].idxmax(axis=1)
session_wide["categories_touched"] = (session_wide[category_columns] > 0).sum(axis=1)
archetypes = (
    session_wide.groupby("dominant_category")
    .agg(workouts=("workout_id", "nunique"), median_sets=("total_sets", "median"), median_categories=("categories_touched", "median"))
    .assign(workouts_per_week=lambda x: x["workouts"] / 12).sort_values("workouts", ascending=False)
)
archetypes

# %%
recent_sequence = session_wide.sort_values(["date", "workout_id"], ascending=False).head(40)
recent_sequence[["date", "workout_id", "dominant_category", "total_sets", "categories_touched"] + category_columns]

# %% [markdown]
# ## 4. Press progression
#
# Each dot is a session-best estimated 1RM. The thick line is a trailing 180-day maximum,
# robust to ordinary variation while still exposing long plateaus or regressions.

# %%
press = recorded[recorded["press_family"].isin(["Flat barbell bench", "Barbell overhead press"]) & recorded["one_rm"].gt(0)].copy()
session_press = (
    press.groupby(["press_family", "workout_id", "date"], as_index=False)
    .agg(best_e1rm=("one_rm", "max"), sets=("set_id", "nunique")).sort_values("date")
)
press_yearly = (
    session_press.assign(year=session_press["date"].dt.year)
    .groupby(["press_family", "year"], as_index=False)
    .agg(year_best_e1rm=("best_e1rm", "max"), sessions=("workout_id", "nunique"))
)
press_yearly.to_csv(OUTPUTS / "press-yearly-progression.csv", index=False)
press_yearly

# %%
frame = notebook_frame((16, 9))
with chart_canvas(frame) as (fig, seed_ax):
    fig.delaxes(seed_ax)
    axes = fig.subplots(2, 1, sharex=True)
    fig.subplots_adjust(hspace=0.16)
    colors = {
        "Flat barbell bench": CATEGORICAL_COLORS[1],
        "Barbell overhead press": CATEGORICAL_COLORS[0],
    }
    add_header(
        fig,
        frame,
        "Like-for-Like Press Progression",
        "Session-best estimated 1RM with a trailing 180-day maximum",
        (),
    )
    for ax, family in zip(
        axes, ["Flat barbell bench", "Barbell overhead press"]
    ):
        family_data = session_press[
            session_press["press_family"] == family
        ].sort_values("date")
        ax.scatter(
            family_data["date"], family_data["best_e1rm"], s=18, alpha=0.22,
            color=colors[family], label="Session best e1RM",
        )
        rolling = (
            family_data.set_index("date")["best_e1rm"]
            .rolling("180D", min_periods=1)
            .max()
        )
        ax.plot(
            rolling.index, rolling, lw=3, color=colors[family],
            label="Trailing 180-day max",
        )
        best = family_data.loc[family_data["best_e1rm"].idxmax()]
        ax.scatter(
            [best["date"]], [best["best_e1rm"]], s=90,
            color=PALETTE.ink, zorder=5,
        )
        ax.annotate(
            f"Lifetime max {best['best_e1rm']:.0f} lb\n{best['date']:%Y-%m-%d}",
            (best["date"], best["best_e1rm"]),
            xytext=(8, 8),
            textcoords="offset points",
            fontsize=10,
            color=PALETTE.ink,
        )
        ax.set(title=family, ylabel="Estimated 1RM (lb)")
        style_axes(ax, NOTEBOOK_AXES)
        style_legend(ax, loc="lower right")
    axes[-1].set_xlabel("Date")
    add_footer(
        fig,
        frame,
        f"{len(session_press):,} PRESS SESSIONS  ·  VARIANTS KEPT SEPARATE",
        f"{first.date()} TO {latest.date()}",
    )
    fig.savefig(
        OUTPUTS / "press-progression-full-history.png",
        dpi=180,
        facecolor=fig.get_facecolor(),
    )
    plt.show()

# %%
def press_period_snapshot(frame, family, start, end, label):
    window = frame[(frame["press_family"] == family) & frame["date"].between(start, end)]
    return {"press_family": family, "period": label, "sessions": window["workout_id"].nunique(),
            "sessions_per_week": window["workout_id"].nunique() / 12, "best_e1rm": window["best_e1rm"].max(),
            "median_top5_e1rm": window.nlargest(min(5, len(window)), "best_e1rm")["best_e1rm"].median() if len(window) else np.nan}

press_recent_compare = pd.DataFrame([
    press_period_snapshot(session_press, family, start, end, label)
    for family in ["Flat barbell bench", "Barbell overhead press"]
    for start, end, label in [(prior_start, prior_end, "Prior 12 weeks"), (current_start, latest, "Current 12 weeks")]
])
press_recent_compare.to_csv(OUTPUTS / "press-current-vs-prior.csv", index=False)
press_recent_compare

# %% [markdown]
# ## 5. Exercise concentration and audit tables

# %%
exercise_current = (
    current.groupby(["name", "iteration", "category"], as_index=False)
    .agg(sets=("set_id", "nunique"), sessions=("workout_id", "nunique"), latest=("date", "max"))
    .assign(sets_per_week=lambda x: x["sets"] / 12).sort_values("sets", ascending=False)
)
exercise_current.to_csv(OUTPUTS / "exercise-volume-current-12w.csv", index=False)
exercise_current.head(40)

# %%
summary_tables = {
    "coverage": coverage, "annual": annual, "period_summary": period_summary,
    "category_compare": category_compare, "stimulus_summary": stimulus_summary,
    "frequency": frequency, "archetypes": archetypes.reset_index(),
    "recent_sequence": recent_sequence, "press_recent_compare": press_recent_compare,
    "press_yearly": press_yearly, "top_exercises": exercise_current.head(40),
}
for summary_name, table in summary_tables.items():
    table.to_csv(OUTPUTS / f"program-analysis-{summary_name}.csv", index=False)
print(f"Wrote {len(summary_tables)} audit tables and 3 chart files to {OUTPUTS}")

# %% [markdown]
# ## 6. Recommendation
#
# The recommendation is maintained in the companion report after reviewing these executed
# tables and rendered charts. This keeps the judgment layer explicit rather than burying it
# inside plotting code.
