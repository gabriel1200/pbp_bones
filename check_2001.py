"""
Run this from your project root to diagnose the CHA/30-team issue.
"""
from pathlib import Path

PARQUET_DIRS = [
    Path("organized_data/regular_season"),
    Path("organized_data/playoffs"),
    Path("data"),
]

for d in PARQUET_DIRS:
    if not d.exists():
        print(f"DIR NOT FOUND: {d}")
        continue
    files_2001 = sorted(d.glob("*_2001_rs.parquet"))
    print(f"\n{d}/ — {len(files_2001)} files matching *_2001_rs.parquet:")
    for f in files_2001:
        print(f"  {f.name}")

import pandas as pd
df = pd.read_parquet("organized_data/regular_season/CHA_2001_rs.parquet")
print(df[['game_id', 'team', 'opp_team']].drop_duplicates('game_id').head(10))
print(df['teamId'].value_counts())