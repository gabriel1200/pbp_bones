import pandas as pd
df=pd.read_csv('organized_data/regular_season/WAS_2026_rs.csv')
df=df[~df.actionType.isin(['substition','timeout','steal','block','rebound'])]
print(df)