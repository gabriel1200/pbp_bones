import pandas as pd
df = pd.read_parquet("organized_data/regular_season/NOP_2001_rs.parquet")
# Force proper display instead of scientific notation
df['teamId'] = df['teamId'].astype('Int64')
print(df.groupby('game_id')['teamId'].unique().head(10))