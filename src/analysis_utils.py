from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Union


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
