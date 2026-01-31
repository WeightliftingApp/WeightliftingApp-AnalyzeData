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

# Save to CSV
df.to_csv(OUTPUT_FILE, index=False)
print(f"Converted {INPUT_FILE} -> {OUTPUT_FILE}")
print(f"Rows: {len(df)}")
