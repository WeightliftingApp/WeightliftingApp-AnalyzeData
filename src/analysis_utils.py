from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Union

import pandas as pd


DateLike = Union[date, datetime]


@dataclass(frozen=True)
class WorkoutStreak:
    start: date
    end: date
    calendar_days: int
    workout_days: int
    workouts: int


@dataclass(frozen=True)
class WorkoutGap:
    start: date
    end: date
    calendar_days_apart: int
    rest_days: int


def _as_date(value: DateLike) -> date:
    return value.date() if isinstance(value, datetime) else value


def calculate_workout_streaks(
    workout_dates: Iterable[DateLike], max_days_between_workouts: int = 1
) -> tuple[list[WorkoutStreak], list[WorkoutGap]]:
    """Group workouts into calendar-based streaks.

    ``max_days_between_workouts=1`` requires training every calendar day.
    ``max_days_between_workouts=2`` permits one rest day between workouts.
    Multiple workouts on one day count as one workout day but remain included in
    the workout total.
    """
    if max_days_between_workouts < 1:
        raise ValueError("max_days_between_workouts must be at least 1")

    workout_counts = Counter(_as_date(value) for value in workout_dates)
    training_days = sorted(workout_counts)
    if not training_days:
        return [], []

    streaks: list[WorkoutStreak] = []
    gaps: list[WorkoutGap] = []
    streak_start = training_days[0]

    def append_streak(streak_end: date) -> None:
        included_days = [
            day for day in training_days if streak_start <= day <= streak_end
        ]
        streaks.append(
            WorkoutStreak(
                start=streak_start,
                end=streak_end,
                calendar_days=(streak_end - streak_start).days + 1,
                workout_days=len(included_days),
                workouts=sum(workout_counts[day] for day in included_days),
            )
        )

    for previous_day, current_day in zip(training_days, training_days[1:]):
        days_apart = (current_day - previous_day).days
        if days_apart > max_days_between_workouts:
            append_streak(previous_day)
            gaps.append(
                WorkoutGap(
                    start=previous_day,
                    end=current_day,
                    calendar_days_apart=days_apart,
                    rest_days=days_apart - 1,
                )
            )
            streak_start = current_day

    append_streak(training_days[-1])
    return streaks, gaps


BIG_THREE_LIFTS = ("Bench", "Squat", "Deadlift")
PR_HISTORY_COLUMNS = (
    "date",
    "series",
    "one_rm",
    "bodyweight",
    "variant",
    "trigger",
    "is_baseline",
)


def mark_pareto_frontier(
    attempts: pd.DataFrame,
    bodyweight_column: str = "bodyweight",
    strength_column: str = "one_rm",
) -> pd.DataFrame:
    """Mark attempts on the lighter-and-stronger Pareto frontier.

    A point is dominated when another attempt was performed at an equal or
    lighter bodyweight with equal or greater strength, with at least one strict
    advantage. Equal duplicate attempts at the same coordinate are all marked.
    Invalid measurements remain in the returned frame with ``is_pareto=False``.
    """
    required = {bodyweight_column, strength_column}
    if not required.issubset(attempts.columns):
        missing = sorted(required - set(attempts.columns))
        raise ValueError(f"attempts is missing columns: {missing}")

    result = attempts.copy()
    result["is_pareto"] = False
    valid = result[
        result[bodyweight_column].notna()
        & result[strength_column].notna()
        & (result[bodyweight_column] > 0)
        & (result[strength_column] > 0)
    ]
    if valid.empty:
        return result

    strongest_by_bodyweight = (
        valid.groupby(bodyweight_column, as_index=False)[strength_column]
        .max()
        .sort_values(bodyweight_column)
    )
    previous_best = strongest_by_bodyweight[strength_column].cummax().shift(
        fill_value=float("-inf")
    )
    frontier_pairs = strongest_by_bodyweight[
        strongest_by_bodyweight[strength_column] > previous_best
    ]
    frontier_coordinates = set(
        frontier_pairs[[bodyweight_column, strength_column]].itertuples(
            index=False, name=None
        )
    )
    result.loc[:, "is_pareto"] = [
        (bodyweight, strength) in frontier_coordinates
        if pd.notna(bodyweight) and pd.notna(strength)
        else False
        for bodyweight, strength in zip(
            result[bodyweight_column], result[strength_column]
        )
    ]
    return result


def build_big_three_pr_history(
    set_records: pd.DataFrame, weekly_weights: pd.DataFrame
) -> pd.DataFrame:
    """Build Bench, Squat, Deadlift, and combined 1RMe PR histories.

    ``set_records`` must contain ``date``, ``lift``, ``one_rm``, and ``variant``.
    Conventional and sumo deadlifts should both use ``lift='Deadlift'``; the
    running maximum then represents whichever style was stronger at the time.

    ``weekly_weights`` must contain ``week_of`` (Monday) and ``bodyweight``.
    Output begins at the first valid weight week. Earlier lifting records seed
    the baseline, while later records are emitted only when they establish a
    true all-time PR. Missing bodyweight weeks remain missing.
    """
    record_columns = {"date", "lift", "one_rm", "variant"}
    weight_columns = {"week_of", "bodyweight"}
    if not record_columns.issubset(set_records.columns):
        missing = sorted(record_columns - set(set_records.columns))
        raise ValueError(f"set_records is missing columns: {missing}")
    if not weight_columns.issubset(weekly_weights.columns):
        missing = sorted(weight_columns - set(weekly_weights.columns))
        raise ValueError(f"weekly_weights is missing columns: {missing}")

    records = set_records.loc[:, list(record_columns)].copy()
    records["date"] = pd.to_datetime(records["date"], errors="coerce").dt.normalize()
    records["one_rm"] = pd.to_numeric(records["one_rm"], errors="coerce")
    records = records[
        records["lift"].isin(BIG_THREE_LIFTS)
        & records["date"].notna()
        & records["one_rm"].notna()
        & (records["one_rm"] > 0)
    ].copy()

    weights = weekly_weights.loc[:, ["week_of", "bodyweight"]].copy()
    weights["week_of"] = pd.to_datetime(weights["week_of"], errors="coerce").dt.normalize()
    weights["bodyweight"] = pd.to_numeric(weights["bodyweight"], errors="coerce")
    weights = weights[
        weights["week_of"].notna()
        & weights["bodyweight"].notna()
        & (weights["bodyweight"] > 0)
    ].drop_duplicates("week_of", keep="last")

    if records.empty or weights.empty:
        return pd.DataFrame(columns=PR_HISTORY_COLUMNS)

    first_weight_week = weights["week_of"].min()
    weight_by_week = weights.set_index("week_of")["bodyweight"]

    # One candidate per lift/day. Sorting one_rm descending ensures the chosen
    # variant is the style that produced the strongest estimate that day.
    daily = (
        records.sort_values(["lift", "date", "one_rm"], ascending=[True, True, False])
        .drop_duplicates(["lift", "date"], keep="first")
        .sort_values(["lift", "date"])
    )

    rows: list[dict[str, object]] = []
    lift_events: dict[str, pd.DataFrame] = {}

    for lift in BIG_THREE_LIFTS:
        lift_daily = daily[daily["lift"] == lift].copy()
        if lift_daily.empty:
            continue
        lift_daily["previous_best"] = lift_daily["one_rm"].cummax().shift(fill_value=0)
        prs = lift_daily[lift_daily["one_rm"] > lift_daily["previous_best"]].copy()
        baseline_candidates = prs[prs["date"] <= first_weight_week]
        if baseline_candidates.empty:
            continue

        baseline = baseline_candidates.tail(1).copy()
        baseline.loc[:, "date"] = first_weight_week
        after_start = prs[prs["date"] > first_weight_week].copy()
        events = pd.concat([baseline, after_start], ignore_index=True)
        events["is_baseline"] = [True] + [False] * len(after_start)
        lift_events[lift] = events

        for _, event in events.iterrows():
            event_date = pd.Timestamp(event["date"])
            week_of = event_date - pd.Timedelta(days=event_date.weekday())
            rows.append(
                {
                    "date": event_date,
                    "series": lift,
                    "one_rm": float(event["one_rm"]),
                    "bodyweight": weight_by_week.get(week_of, float("nan")),
                    "variant": event["variant"],
                    "trigger": "Baseline" if bool(event["is_baseline"]) else lift,
                    "is_baseline": bool(event["is_baseline"]),
                }
            )

    if all(lift in lift_events for lift in BIG_THREE_LIFTS):
        event_dates = sorted(
            {first_weight_week}
            | {
                pd.Timestamp(event_date)
                for events in lift_events.values()
                for event_date in events.loc[~events["is_baseline"], "date"]
            }
        )
        current = {
            lift: float(events.iloc[0]["one_rm"])
            for lift, events in lift_events.items()
        }
        events_by_date = {
            lift: events.set_index("date") for lift, events in lift_events.items()
        }

        for event_date in event_dates:
            triggers = []
            for lift in BIG_THREE_LIFTS:
                indexed = events_by_date[lift]
                if event_date in indexed.index and event_date != first_weight_week:
                    event = indexed.loc[event_date]
                    if isinstance(event, pd.DataFrame):
                        event = event.iloc[-1]
                    current[lift] = float(event["one_rm"])
                    triggers.append(lift)
            week_of = event_date - pd.Timedelta(days=event_date.weekday())
            rows.append(
                {
                    "date": event_date,
                    "series": "Combined",
                    "one_rm": sum(current.values()),
                    "bodyweight": weight_by_week.get(week_of, float("nan")),
                    "variant": None,
                    "trigger": "Baseline" if event_date == first_weight_week else " + ".join(triggers),
                    "is_baseline": event_date == first_weight_week,
                }
            )

    return (
        pd.DataFrame(rows, columns=PR_HISTORY_COLUMNS)
        .sort_values(["series", "date"])
        .reset_index(drop=True)
    )
