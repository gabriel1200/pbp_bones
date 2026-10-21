import pandas as pd
from pathlib import Path

stale = []
for f in Path("pbp_data").glob("2001_*.csv"):
    df = pd.read_csv(f)
    if 1610612766 in df['teamId'].astype('Int64').values:
        stale.append(f.name)

print(f"{len(stale)} stale files:")
for f in stale:
    print(f)