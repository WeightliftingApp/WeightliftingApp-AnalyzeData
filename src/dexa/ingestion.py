"""Read DEXA source datasets without modifying them."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

TOTAL_COLUMNS = {
    "date",
    "weight_lb",
    "lean_soft_tissue_lb",
    "fat_mass_lb",
    "bone_mineral_content_lb",
    "body_fat_pct",
    "fat_free_mass_lb",
    "ffmi",
    "normalized_ffmi",
    "bmi",
    "height_in",
}
REGION_COLUMNS = {
    "date",
    "region",
    "fat_mass_lb",
    "lean_soft_tissue_lb",
    "bone_mineral_content_lb",
    "body_fat_pct",
}


def _read_csv(path: Path, required_columns: set[str]) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"])
    missing = required_columns.difference(frame.columns)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"{path} is missing required columns: {missing_list}")
    return frame


def load_totals(path: Path) -> pd.DataFrame:
    """Load total-body scans in chronological order."""
    return _read_csv(path, TOTAL_COLUMNS).sort_values("date").reset_index(drop=True)


def load_regions(path: Path) -> pd.DataFrame:
    """Load regional scans without changing their source order."""
    return _read_csv(path, REGION_COLUMNS)


def load_dexa_data(
    totals_path: Path, regions_path: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the two report inputs."""
    return load_totals(totals_path), load_regions(regions_path)
