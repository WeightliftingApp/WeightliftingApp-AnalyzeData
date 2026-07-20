#!/usr/bin/env python3
"""Convert Weight Log.xlsx to weight.csv"""

import pandas as pd

INPUT_FILE = "/Users/chappyasel/Library/Mobile Documents/com~apple~CloudDocs/Spreadsheets/Weight Log.xlsx"
OUTPUT_FILE = "/Users/chappyasel/Desktop/Repos/WeightliftingApp-AnalyzeData/data/weight.csv"

# Read from "Agg" sheet, starting at row 24 (0-indexed: skiprows=23), columns D and E
df = pd.read_excel(
    INPUT_FILE,
    sheet_name="Agg",
    usecols="D:E",
    skiprows=23,
    header=0,
)

# Rename columns to match existing CSV format
df.columns = ["Week of", "Average"]

# Normalize workbook output. Formula cells for weeks without measurements can
# evaluate to 0, which is not a valid bodyweight and must remain missing so it
# does not distort charts, interpolation, or Wilks calculations.
df["Week of"] = pd.to_datetime(df["Week of"], errors="coerce")
df["Average"] = pd.to_numeric(df["Average"], errors="coerce")
df.loc[df["Average"] <= 0, "Average"] = pd.NA
df = df.dropna(subset=["Week of"])

# Save to CSV
df.to_csv(OUTPUT_FILE, index=False)
print(f"Converted {INPUT_FILE} -> {OUTPUT_FILE}")
print(f"Rows: {len(df)}")
latest = df.dropna(subset=["Average"]).iloc[-1]
print(f"Latest: {latest['Week of']:%Y-%m-%d} — {latest['Average']:.2f} lbs")
