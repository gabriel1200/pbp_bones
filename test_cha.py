import pandas as pd
df = pd.read_csv("pbp_data/2001_20000004.csv")  # any 2001 game
print(df['teamId'].unique())