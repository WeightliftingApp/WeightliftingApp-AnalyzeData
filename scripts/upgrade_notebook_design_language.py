#!/usr/bin/env python3
"""Apply the reviewed v2 design-language migration to priority notebooks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def source(cell: dict) -> str:
    value = cell["source"]
    return "".join(value) if isinstance(value, list) else value


def set_source(cell: dict, value: str) -> None:
    cell["source"] = value.splitlines(keepends=True)


def output_text(output: dict) -> str:
    value = output.get("text", "")
    return "".join(value) if isinstance(value, list) else value


def replace_once(text: str, old: str, new: str, *, context: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count == 1:
        return text.replace(old, new, 1)
    raise RuntimeError(f"{context}: expected one migration anchor, found {count}")


def collapse_duplicate(text: str, block: str) -> str:
    """Collapse consecutive copies left by an interrupted early migration."""
    while block + block in text:
        text = text.replace(block + block, block)
    return text


def replace_block(
    text: str,
    start: str,
    end: str,
    replacement: str,
    *,
    sentinel: str,
    context: str,
) -> str:
    if sentinel in text:
        return text
    start_index = text.find(start)
    end_index = text.find(end, start_index)
    if start_index < 0 or end_index < 0:
        raise RuntimeError(f"{context}: block anchors were not found")
    end_index += len(end)
    return text[:start_index] + replacement + text[end_index:]


def migrate_big_three(notebook: dict) -> None:
    cell = notebook["cells"][3]
    text = source(cell)
    text = replace_once(
        text,
        "    PALETTE,\n",
        "    PALETTE,\n    ChartArchetype,\n",
        context="big-three imports",
    )
    text = replace_once(
        text,
        "    chart_canvas,\n",
        "    chart_canvas,\n    label_line_ends,\n",
        context="big-three direct-label import",
    )
    text = replace_once(
        text,
        "big_three_frame = notebook_frame((10, 6))",
        "big_three_frame = notebook_frame(\n    (10, 6), archetype=ChartArchetype.COMPARISON\n)",
        context="big-three frame",
    )
    text = replace_once(
        text,
        "series_colors = dict(zip(exercises, CATEGORICAL_COLORS))",
        '''series_colors = dict(zip(exercises, CATEGORICAL_COLORS))
short_exercise_labels = {
    "Flat Barbell Bench Press": "BENCH PRESS",
    "Back Squats": "BACK SQUAT",
    "Deadlifts (Conventional + Sumo)": "DEADLIFT",
}''',
        context="big-three short labels",
    )
    text = replace_once(
        text,
        "with chart_canvas(big_three_frame) as (fig, ax):\n    markers = [\"o\", \"s\", \"^\"]",
        "with chart_canvas(big_three_frame) as (fig, ax):\n    markers = [\"o\", \"s\", \"^\"]\n    progression_lines = []",
        context="big-three line inventory",
    )
    text = replace_once(
        text,
        "    progression_lines = []",
        "    progression_lines = []\n    progression_labels = []",
        context="big-three label inventory",
    )
    text = replace_once(
        text,
        "            ax.plot(\n                df[\"date\"],\n                df[\"weight\"],\n                marker=marker,\n                color=series_colors[exercise],\n                label=exercise,\n            )",
        "            line, = ax.plot(\n                df[\"date\"],\n                df[\"weight\"],\n                marker=marker,\n                color=series_colors[exercise],\n                label=exercise,\n            )\n            progression_lines.append(line)",
        context="big-three plotted lines",
    )
    text = replace_once(
        text,
        "            progression_lines.append(line)",
        "            progression_lines.append(line)\n            progression_labels.append(short_exercise_labels[exercise])",
        context="big-three plotted labels",
    )
    if 'style_legend(ax, loc="lower right")' not in text:
        if "labels=progression_labels" not in text:
            text = replace_once(
                text,
                "    style_axes(ax, NOTEBOOK_AXES)\n    style_legend(ax)",
                "    style_axes(ax, NOTEBOOK_AXES)\n    ax.margins(x=0.10)\n    label_line_ends(ax, progression_lines, min_gap_points=14)",
                context="big-three direct labels",
            )
        if "y_offsets_points" not in text:
            text = replace_once(
                text,
                "    style_axes(ax, NOTEBOOK_AXES)\n    ax.margins(x=0.10)\n    label_line_ends(ax, progression_lines, min_gap_points=14)",
                "    style_axes(ax, NOTEBOOK_AXES)\n    ax.margins(x=0.10)\n    label_line_ends(\n        ax, progression_lines, labels=progression_labels, min_gap_points=17\n    )",
                context="big-three concise direct labels",
            )
        text = replace_once(
            text,
            "    style_axes(ax, NOTEBOOK_AXES)\n    ax.margins(x=0.10)\n    label_line_ends(\n        ax, progression_lines, labels=progression_labels, min_gap_points=17\n    )",
            "    style_axes(ax, NOTEBOOK_AXES)\n    ax.margins(x=0.10)\n    label_line_ends(\n        ax,\n        progression_lines,\n        labels=progression_labels,\n        min_gap_points=17,\n        y_offsets_points=(0, 16, -10),\n    )",
            context="big-three label offsets",
        )
        text = replace_once(
            text,
            "    style_axes(ax, NOTEBOOK_AXES)\n    ax.margins(x=0.10)\n    label_line_ends(\n        ax,\n        progression_lines,\n        labels=progression_labels,\n        min_gap_points=17,\n        y_offsets_points=(0, 16, -10),\n    )",
            "    style_axes(ax, NOTEBOOK_AXES)\n    style_legend(ax, loc=\"lower right\")",
            context="big-three dense-label fallback",
        )
    text = replace_once(
        text,
        '        "Big Three Strength Progression (1RMe)",',
        '        "BIG THREE PR FRONTIERS KEEP MOVING UP",',
        context="big-three title",
    )
    text = collapse_duplicate(text, "    ChartArchetype,\n")
    text = collapse_duplicate(text, "    progression_lines = []\n")
    set_source(cell, text)

    cell = notebook["cells"][4]
    text = source(cell)
    text = replace_once(
        text,
        "with chart_canvas(big_three_frame) as (fig, ax):\n    markers = [\"o\", \"s\", \"^\"]",
        "with chart_canvas(big_three_frame) as (fig, ax):\n    markers = [\"o\", \"s\", \"^\"]\n    projection_lines = []\n    projection_labels = []",
        context="big-three projection inventory",
    )
    old_projection = '''                ax.plot(
                    future_dates,
                    projected_weights,
                    "--",
                    color=line_color,
                    label=(
                        f"{exercise} (Recent rate: {recent_rate:+.0f} lbs/yr, "
                        f"1-year: {projected_weight:.0f} lbs)"
                    ),
                )'''
    initial_projection = '''                projection_line, = ax.plot(
                    future_dates,
                    projected_weights,
                    "--",
                    color=line_color,
                    label=exercise,
                )
                projection_lines.append(projection_line)
                projection_labels.append(
                    f"{exercise}: {recent_rate:+.0f} LB/YR  →  {projected_weight:.0f} LB"
                )'''
    new_projection = '''                projection_line, = ax.plot(
                    future_dates,
                    projected_weights,
                    "--",
                    color=line_color,
                    label=exercise,
                )
                projection_lines.append(projection_line)
                projection_labels.append(
                    f"{short_exercise_labels[exercise]}: {recent_rate:+.0f} LB/YR"
                    f"  →  {projected_weight:.0f} LB"
                )'''
    if new_projection not in text:
        text = replace_once(
            text,
            old_projection,
            initial_projection,
            context="big-three projections",
        )
    text = replace_once(
        text,
        initial_projection,
        new_projection,
        context="big-three concise projection labels",
    )
    text = replace_once(
        text,
        "    style_axes(ax, NOTEBOOK_AXES)\n    style_legend(ax)\n    fig.autofmt_xdate()",
        "    style_axes(ax, NOTEBOOK_AXES)\n    ax.margins(x=0.12)\n    label_line_ends(\n        ax, projection_lines, labels=projection_labels, min_gap_points=16\n    )\n    fig.autofmt_xdate()",
        context="big-three projection labels",
    )
    text = replace_once(
        text,
        '        "Big Three Historical Trends and One-Year Projections",',
        '        "RECENT BIG THREE RATES, PROJECTED ONE YEAR",',
        context="big-three projection title",
    )
    text = collapse_duplicate(
        text, "    projection_lines = []\n    projection_labels = []\n"
    )
    set_source(cell, text)


def migrate_pr_szn(notebook: dict) -> None:
    cell = notebook["cells"][5]
    text = source(cell)
    text = text.replace(
        "MONTHLY PR COUNTS SHOW REPEATED SEASONAL PEAKS",
        "MONTHLY PR COUNTS SHOW REPEATED ANNUAL PEAKS",
    )
    text = replace_once(
        text,
        "    PALETTE,\n",
        "    PALETTE,\n    AnnotationKind,\n    ChartArchetype,\n",
        context="PR imports",
    )
    text = replace_once(
        text,
        "    add_header,\n",
        "    add_header,\n    annotate_point,\n",
        context="PR annotation import",
    )
    text = replace_once(
        text,
        "frame = notebook_frame((15, 6))",
        "frame = notebook_frame((15, 6), archetype=ChartArchetype.COMPARISON)",
        context="PR monthly frame",
    )
    text = replace_once(
        text,
        '        fig, frame, "PR SZN!!",\n        "Tracking PRs over my lifting career\\nShowing monthly PR counts with yearly peak annotations",',
        '        fig, frame, "MONTHLY PR COUNTS SHOW REPEATED ANNUAL PEAKS",\n        "1RMe and volume records since 2018, with July-to-June peak annotations",',
        context="PR monthly title",
    )
    text = collapse_duplicate(text, "    AnnotationKind,\n    ChartArchetype,\n")
    text = collapse_duplicate(text, "    annotate_point,\n")
    set_source(cell, text)

    for index, archetype in ((7, "HERO"), (8, "DIAGNOSTIC"), (9, "DIAGNOSTIC")):
        cell = notebook["cells"][index]
        text = source(cell)
        text = replace_once(
            text,
            "frame = notebook_frame((10, 6))",
            f"frame = notebook_frame((10, 6), archetype=ChartArchetype.{archetype})",
            context=f"PR cell {index} frame",
        )
        set_source(cell, text)

    cell = notebook["cells"][7]
    text = source(cell)
    text = replace_once(
        text,
        'add_header(fig, frame, "Total One Rep Max Progress", "", ())',
        'add_header(\n        fig,\n        frame,\n        f"AGGREGATE 1RM FRONTIER REACHED {total_weights[-1]:,.0f} LB",\n        "Sum of current exercise-level estimated 1RM records",\n        (f"{len(total_weights):,} FRONTIER UPDATES",),\n    )',
        context="PR aggregate title",
    )
    text = replace_once(
        text,
        "    style_axes(ax, NOTEBOOK_AXES)\n    add_footer(",
        "    style_axes(ax, NOTEBOOK_AXES)\n    annotate_point(\n        ax, dates[-1], total_weights[-1], f\"{total_weights[-1]:,.0f} LB\",\n        kind=AnnotationKind.LATEST, xytext=(-8, 10), ha=\"right\",\n    )\n    add_footer(",
        context="PR latest aggregate annotation",
    )
    set_source(cell, text)

    cell = notebook["cells"][8]
    text = source(cell)
    text = replace_once(
        text,
        '        fig, frame, "Total One Rep Max Progress with Asymptotic Trendline",\n        f"(Current rate: {current_rate:.1f} lbs/year, Projected max: {popt[0]:.1f} lbs)",',
        '        fig, frame, f"MODEL PROJECTS {target_weight:,.0f} LB BY {target_date:%b %Y}",\n        f"Asymptotic fit to aggregate 1RM records; current slope {current_rate:.1f} lb/year",',
        context="PR all-record model title",
    )
    text = replace_once(
        text,
        "    # Add target point\n    ax.plot(\n        target_date,\n        target_weight,\n        'o',\n        color=PALETTE.advance,\n        markersize=8,\n        label=f'{target_date:%b %Y} projection: {target_weight:.1f} lbs',\n    )",
        "    # Add and directly label the target point.\n    annotate_point(\n        ax, target_date, target_weight, f\"{target_weight:,.0f} LB\",\n        kind=AnnotationKind.ESTIMATE, xytext=(-8, 10), ha=\"right\",\n    )",
        context="PR all-record target annotation",
    )
    set_source(cell, text)

    cell = notebook["cells"][9]
    text = source(cell)
    text = replace_once(
        text,
        '        fig, frame, "Total One Rep Max Progress with Asymptotic Trendline",\n        f"(Current rate: {current_rate:.1f} lbs/year, Projected max: {popt[0]:.1f} lbs)",',
        '        fig, frame, f"JULY-SNAPSHOT MODEL PROJECTS {target_weight:,.0f} LB",\n        f"Next July projection from annual checkpoints; current slope {current_rate:.1f} lb/year",',
        context="PR July model title",
    )
    set_source(cell, text)


WILKS_STACKED = '''# Separate bodyweight, lift strength, and Wilks onto aligned panels.
frame = notebook_frame((15, 9), archetype=ChartArchetype.DIAGNOSTIC)
bodyweight_color, bench_color, squat_color = CATEGORICAL_COLORS[:3]
wilks_color = PALETTE.frontier
with stacked_canvas(frame, (1, 1, 1), hspace=0.13) as (
    fig, (weight_ax, lift_ax, wilks_ax)
):
    weight_ax.plot(
        df_merged["Date"],
        df_merged["Average_Interpolated"],
        "-",
        color=bodyweight_color,
    )
    weight_ax.scatter(
        df_clean["Date"], df_clean["Average"], s=20, color=bodyweight_color
    )
    weight_ax.set_ylabel("BODYWEIGHT (LB)")
    weight_ax.set_title("BODYWEIGHT", fontsize=10, loc="left", family="monospace")

    if not plot_bench_df.empty:
        lift_ax.scatter(
            plot_bench_df["date"],
            plot_bench_df["weight"],
            color=bench_color,
            marker="o",
            alpha=0.72,
            s=30,
            label="BENCH 1RM",
        )
    if not plot_squat_df.empty:
        lift_ax.scatter(
            plot_squat_df["date"],
            plot_squat_df["weight"],
            color=squat_color,
            marker="s",
            alpha=0.72,
            s=30,
            label="SQUAT 1RM",
        )
    lift_ax.set_ylabel("ESTIMATED 1RM (LB)")
    lift_ax.set_title("STRENGTH", fontsize=10, loc="left", family="monospace")
    lift_ax.yaxis.set_major_formatter(FormatStrFormatter("%.0f"))
    if lift_ax.collections:
        style_legend(lift_ax, loc="upper left", ncol=2)

    wilks_ax.plot(
        df_merged["Date"],
        df_merged["Wilks_Multiplier"],
        "-",
        color=wilks_color,
        linewidth=2,
    )
    wilks_ax.set_ylim(0.9, 1.1)
    wilks_ax.set_ylabel("WILKS MULTIPLIER")
    wilks_ax.set_xlabel("DATE")
    wilks_ax.set_title("210 LB-BASE MULTIPLIER", fontsize=10, loc="left", family="monospace")
    wilks_ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    wilks_ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    wilks_ax.tick_params(axis="x", rotation=45)

    for panel in (weight_ax, lift_ax, wilks_ax):
        style_axes(panel, NOTEBOOK_AXES)
    add_header(
        fig,
        frame,
        "HOW BODYWEIGHT CHANGES THE WILKS LIFT MULTIPLIER",
        "Aligned panels preserve time while giving each measure an honest scale",
        (),
    )
    add_footer(
        fig,
        frame,
        "WILKS = 2020 MEN'S FORMULA  /  BASE = 210 LB",
        "PANELS SHARE TIME, NOT UNITS",
        right_weight="normal",
    )
    plt.show()
'''


def migrate_wilks(notebook: dict) -> None:
    cell = notebook["cells"][0]
    text = source(cell)
    text = replace_once(
        text,
        "    PALETTE,\n",
        "    PALETTE,\n    ChartArchetype,\n",
        context="Wilks archetype import",
    )
    text = replace_once(
        text,
        "frame = notebook_frame((15, 6))",
        "frame = notebook_frame((15, 6), archetype=ChartArchetype.HERO)",
        context="Wilks bodyweight frame",
    )
    set_source(cell, text)

    cell = notebook["cells"][1]
    text = replace_once(
        source(cell),
        "frame = notebook_frame((15, 6))",
        "frame = notebook_frame((15, 6), archetype=ChartArchetype.COMPARISON)",
        context="Wilks strength frame",
    )
    set_source(cell, text)

    cell = notebook["cells"][2]
    text = replace_block(
        source(cell),
        "# Create the plot with three y-axes\n",
        "    plt.show()",
        WILKS_STACKED,
        sentinel="PANELS SHARE TIME, NOT UNITS",
        context="Wilks stacked redesign",
    )
    set_source(cell, text)

    cell = notebook["cells"][3]
    text = replace_once(
        source(cell),
        "frame = notebook_frame((15, 6))",
        "frame = notebook_frame((15, 6), archetype=ChartArchetype.DIAGNOSTIC)",
        context="Wilks adjusted frame",
    )
    set_source(cell, text)

    cell = notebook["cells"][4]
    text = replace_once(
        source(cell),
        "frame = notebook_frame((12, 8))",
        "frame = notebook_frame((12, 8), archetype=ChartArchetype.COMPARISON)",
        context="Wilks returns frame",
    )
    set_source(cell, text)


WORKOUT_STACKED = '''# Separate the three measures into aligned panels with honest scales.
frame = notebook_frame((15, 9), archetype=ChartArchetype.COMPARISON)
with stacked_canvas(frame, (1, 1, 1), hspace=0.13) as (
    fig, (weight_ax, volume_ax, sets_ax)
):
    weight_color = CATEGORICAL_COLORS[0]
    volume_color = CATEGORICAL_COLORS[1]
    sets_color = CATEGORICAL_COLORS[2]

    weight_ax.plot(
        df_merged["Date"],
        df_merged["Average_Interpolated"],
        "-",
        color=weight_color,
        linewidth=1.8,
    )
    weight_ax.scatter(
        df_clean["Date"], df_clean["Average"], s=18, color=weight_color
    )
    weight_ax.set_ylabel("BODYWEIGHT (LB)")
    weight_ax.set_title("BODYWEIGHT", fontsize=10, loc="left", family="monospace")

    volume_ax.scatter(
        workout_df["Date"],
        workout_df["VolumePerHour"],
        color=volume_color,
        alpha=0.10,
        s=15,
    )
    volume_ax.plot(
        rolling_volume_per_hour.index,
        rolling_volume_per_hour.values,
        color=volume_color,
        linewidth=2,
    )
    volume_ax.set_ylim(12_000, 50_000)
    volume_ax.set_ylabel("VOLUME / HOUR")
    volume_ax.set_title("VOLUME DENSITY", fontsize=10, loc="left", family="monospace")

    sets_ax.scatter(
        workout_df["Date"],
        workout_df["SetsPerHour"],
        color=sets_color,
        alpha=0.10,
        s=15,
    )
    sets_ax.plot(
        rolling_sets_per_hour.index,
        rolling_sets_per_hour.values,
        color=sets_color,
        linewidth=2,
    )
    sets_ax.set_ylim(15, 30)
    sets_ax.set_ylabel("SETS / HOUR")
    sets_ax.set_xlabel("DATE")
    sets_ax.set_title("SET DENSITY", fontsize=10, loc="left", family="monospace")
    sets_ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    sets_ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    sets_ax.tick_params(axis="x", rotation=45)

    for panel in (weight_ax, volume_ax, sets_ax):
        style_axes(panel, NOTEBOOK_AXES)

    latest_volume_density = rolling_volume_per_hour.dropna().iloc[-1]
    latest_set_density = rolling_sets_per_hour.dropna().iloc[-1]
    add_header(
        fig,
        frame,
        "BODYWEIGHT AND TRAINING DENSITY, ON HONEST SCALES",
        (
            f"Latest 30-day density: {latest_volume_density:,.0f} volume/hour and "
            f"{latest_set_density:.1f} sets/hour"
        ),
        (
            f"{len(workout_df):,} WORKOUTS",
            f"{workout_df['Date'].min():%b %Y} TO {workout_df['Date'].max():%b %Y}",
        ),
    )
    add_footer(
        fig,
        frame,
        "LINES = 30-DAY SUM / 30-DAY HOURS",
        "FAINT POINTS = INDIVIDUAL WORKOUTS",
        right_weight="normal",
    )
    plt.show()
'''


def migrate_workout_intensity(notebook: dict) -> None:
    cell = notebook["cells"][2]
    text = source(cell)
    text = replace_once(
        text,
        "    PALETTE,\n",
        "    PALETTE,\n    ChartArchetype,\n",
        context="workout archetype import",
    )
    text = replace_once(
        text,
        "    notebook_frame,\n",
        "    notebook_frame,\n    stacked_canvas,\n",
        context="workout stacked import",
    )
    text = replace_once(
        text,
        "frame = notebook_frame((15, 6))",
        "frame = notebook_frame((15, 6), archetype=ChartArchetype.HERO)",
        context="workout duration frame",
    )
    text = replace_once(
        text,
        '        "30-Day Rolling Average Workout Duration (Since Oct 2018)",\n        "Time-based rolling mean of recorded workout duration",',
        '        f"LATEST 30-DAY WORKOUTS AVERAGED {rolling_avg.dropna().iloc[-1]:.0f} MINUTES",\n        "Time-based rolling mean of recorded workout duration since October 2018",',
        context="workout duration title",
    )
    set_source(cell, text)

    cell = notebook["cells"][3]
    text = replace_block(
        source(cell),
        "# Create the plot with three y-axes\n",
        "    plt.show()",
        WORKOUT_STACKED,
        sentinel="BODYWEIGHT AND TRAINING DENSITY, ON HONEST SCALES",
        context="workout stacked redesign",
    )
    set_source(cell, text)


def migrate_users(notebook: dict) -> None:
    cell = notebook["cells"][4]
    text = source(cell)
    text = replace_once(
        text,
        "    PALETTE,\n",
        "    PALETTE,\n    AnnotationKind,\n    ChartArchetype,\n",
        context="users imports",
    )
    text = replace_once(
        text,
        "    add_header,\n",
        "    add_header,\n    annotate_reference_line,\n",
        context="users reference import",
    )
    text = replace_once(
        text,
        "frame = notebook_frame((12, 6))",
        "frame = notebook_frame((12, 6), archetype=ChartArchetype.HERO)",
        context="users hero frame",
    )
    start = "    for i in range(len(counts)):\n"
    end = "    ax.axvline(\n        percentile_999,\n        color=p999_color,\n        linestyle=\"--\",\n        label=f\"99.9th %ile: {percentile_999:.1f} lbs\",\n    )\n"
    replacement = '''    references = (
        (mean_1rm, f"MEAN  {mean_1rm:.0f} LB", 0.94),
        (percentile_90, f"90TH  {percentile_90:.0f} LB", 0.79),
        (percentile_99, f"99TH  {percentile_99:.0f} LB", 0.64),
        (percentile_999, f"99.9TH  {percentile_999:.0f} LB", 0.49),
    )
    for value, label, label_y in references:
        annotate_reference_line(
            ax, value, label, kind=AnnotationKind.REFERENCE, y=label_y
        )
'''
    text = replace_block(
        text,
        start,
        end,
        replacement,
        sentinel="99.9TH  {percentile_999:.0f} LB",
        context="users percentile labels",
    )
    text = replace_once(
        text,
        '        "Distribution of Bench Press 1RMs Across All Users",\n        "Estimated one-rep maxima from every recorded bench press exercise",',
        '        f"TOP 1% OF RECORDED BENCH 1RMS STARTS NEAR {percentile_99:.0f} LB",\n        "All-user estimated one-rep-max distribution with directly labeled thresholds",',
        context="users answer-first title",
    )
    text = replace_once(
        text,
        "    style_axes(ax, NOTEBOOK_AXES)\n    style_legend(ax)",
        "    style_axes(ax, NOTEBOOK_AXES)",
        context="users legend removal",
    )
    text = replace_once(
        text,
        '        "50 BINS  /  RANGE 0 TO 500 LB  /  BAR LABELS = COUNTS",\n        "DASHES = MEAN AND UPPER PERCENTILES",',
        '        "50 BINS  /  RANGE 0 TO 500 LB",\n        "REFERENCE LINES = MEAN AND UPPER PERCENTILES",',
        context="users footer",
    )
    set_source(cell, text)

    # Tqdm emits hundreds of carriage-return frames under nbconvert. Keep the
    # final loaded-file summary while dropping progress-only stream records.
    load_cell = notebook["cells"][2]
    load_cell["outputs"] = [
        output
        for output in load_cell.get("outputs", [])
        if "Loading WLD files:" not in output_text(output)
    ]


MIGRATIONS = {
    "analyze_big_three.ipynb": migrate_big_three,
    "analyze_pr_szn.ipynb": migrate_pr_szn,
    "analyze_wilks.ipynb": migrate_wilks,
    "analyze_workout_intensity.ipynb": migrate_workout_intensity,
    "analyze_users.ipynb": migrate_users,
}


def migrate(root: Path, *, write: bool) -> list[Path]:
    changed = []
    for filename, migration in MIGRATIONS.items():
        path = root / filename
        notebook = json.loads(path.read_text())
        before = json.dumps(notebook, ensure_ascii=False, indent=1) + "\n"
        migration(notebook)
        after = json.dumps(notebook, ensure_ascii=False, indent=1) + "\n"
        if before == after:
            continue
        changed.append(path)
        if write:
            path.write_text(after)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook-dir", type=Path, default=Path("src"))
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when any priority notebook still needs the migration",
    )
    args = parser.parse_args()
    changed = migrate(args.notebook_dir, write=not args.check)
    if args.check and changed:
        for path in changed:
            print(path)
        raise SystemExit(1)
    for path in changed:
        print(path)


if __name__ == "__main__":
    main()
