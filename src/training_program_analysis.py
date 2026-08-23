from __future__ import annotations

from typing import Mapping

import pandas as pd


NUMERIC_COLUMNS = ("reps", "weight", "volume", "one_rm")


def _normalize_text(value: object) -> str:
    """Normalize nullable CSV text fields, including pandas NaN values."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower()


def prepare_set_records(records: pd.DataFrame) -> pd.DataFrame:
    """Normalize live lifting set records without inventing missing values.

    A recorded set is any row with positive reps. The source does not reliably
    identify warm-ups or proximity to failure, so this deliberately does not
    call them "hard sets" or filter them by load.
    """
    result = records.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce").dt.normalize()
    for column in NUMERIC_COLUMNS:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    result["week_of"] = result["date"] - pd.to_timedelta(
        result["date"].dt.weekday, unit="D"
    )
    result["is_recorded_set"] = result["reps"].fillna(0).gt(0)
    return result


def summarize_category_window(
    records: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    window_weeks: float,
) -> pd.DataFrame:
    """Summarize direct category volume in an inclusive date window."""
    if window_weeks <= 0:
        raise ValueError("window_weeks must be positive")
    window = records[
        records["date"].between(pd.Timestamp(start), pd.Timestamp(end), inclusive="both")
        & records["is_recorded_set"]
        & records["category"].notna()
    ].copy()
    if window.empty:
        return pd.DataFrame(
            columns=[
                "category",
                "direct_sets",
                "sessions",
                "sets_per_week",
                "sessions_per_week",
                "tonnage_per_week",
            ]
        )

    summary = (
        window.groupby("category", as_index=False)
        .agg(
            direct_sets=("is_recorded_set", "sum"),
            sessions=("workout_id", "nunique"),
            tonnage=("volume", "sum"),
        )
        .sort_values("direct_sets", ascending=False)
    )
    summary["sets_per_week"] = summary["direct_sets"] / window_weeks
    summary["sessions_per_week"] = summary["sessions"] / window_weeks
    summary["tonnage_per_week"] = summary["tonnage"] / window_weeks
    return summary.drop(columns="tonnage").reset_index(drop=True)


def estimate_muscle_stimulus(
    name: str | None, iteration: str | None, category: str | None
) -> Mapping[str, float]:
    """Estimate stimulus-equivalent sets using transparent fixed coefficients.

    Primary work receives 1.0 set. Common compound secondaries receive 0.5.
    This is a planning heuristic, not a physiological measurement.
    """
    name_text = _normalize_text(name)
    variant_text = _normalize_text(iteration)
    category_text = "" if category is None or pd.isna(category) else str(category).strip()
    combined = f"{name_text} {variant_text}"

    if category_text == "Legs":
        if "calf" in combined:
            return {"Calves": 1.0}
        if "hip abduction" in combined or "hip abductions" in combined:
            if "inner" in combined:
                return {"Adductors": 1.0}
            return {"Glutes": 1.0}
        if any(token in combined for token in ("leg curl", "deadlift", "romanian", "stiff leg")):
            if "deadlift" in combined:
                return {"Hamstrings": 1.0, "Glutes": 0.5, "Back": 0.5}
            return {"Hamstrings": 1.0}
        if "leg extension" in combined:
            return {"Quads": 1.0}
        if any(token in combined for token in ("squat", "leg press", "lunge", "split squat", "step-up")):
            return {"Quads": 1.0, "Glutes": 0.5}
        if any(token in combined for token in ("hip thrust", "glute", "kickback")):
            return {"Glutes": 1.0}
        return {"Legs (unspecified)": 1.0}

    if not category_text:
        return {}

    stimulus: dict[str, float] = {category_text: 1.0}
    is_chest_press = category_text == "Chest" and any(
        token in combined for token in ("press", "bench")
    )
    is_shoulder_press = category_text == "Shoulders" and "press" in combined
    is_arm_assisted_pull = category_text == "Back" and any(
        token in combined
        for token in ("row", "pulldown", "pull-down", "pull-up", "pullup", "chin-up", "chinup")
    )

    if is_chest_press:
        stimulus["Triceps"] = stimulus.get("Triceps", 0.0) + 0.5
        stimulus["Shoulders"] = stimulus.get("Shoulders", 0.0) + 0.5
    if is_shoulder_press:
        stimulus["Triceps"] = stimulus.get("Triceps", 0.0) + 0.5
    if is_arm_assisted_pull:
        stimulus["Biceps"] = stimulus.get("Biceps", 0.0) + 0.5
    return stimulus


def _press_family(name: str | None, iteration: str | None) -> str | None:
    name_text = _normalize_text(name)
    variant_text = _normalize_text(iteration)

    if "close-grip bench" in name_text or "close grip bench" in name_text:
        return "Close-grip bench"
    if "barbell bench press" in name_text:
        if "incline" in variant_text:
            return "Incline barbell bench"
        if "flat" in variant_text or not variant_text:
            return "Flat barbell bench"
        return "Other barbell bench"
    if name_text == "overhead press" and "barbell" in variant_text:
        return "Barbell overhead press"
    if "military press" in name_text and "barbell" in variant_text:
        return "Barbell overhead press"
    if any(token in name_text for token in ("overhead press", "arnold press", "military press", "landmine press", "pin press")):
        return "Other overhead press"
    return None


def add_press_family(records: pd.DataFrame) -> pd.DataFrame:
    """Add a conservative press family suitable for like-for-like trends."""
    result = records.copy()
    result["press_family"] = pd.Series(
        [
        _press_family(name, iteration)
        for name, iteration in zip(result["name"], result["iteration"])
        ],
        index=result.index,
        dtype=object,
    )
    return result
