# Quick diagnostic — run on the uploaded CSV
import pandas as pd
df = pd.read_csv('OKC_2009_rs.csv', low_memory=False)
WEAVER = '201602'

# Does Weaver appear in off or def but NOT players_on anywhere?
mismatch = df[
    (df['off_players_on'].str.contains(WEAVER, na=False) | 
     df['def_players_on'].str.contains(WEAVER, na=False)) & 
    ~df['players_on'].str.contains(WEAVER, na=False)
]
print(f'Rows where Weaver in off/def but not players_on: {len(mismatch)}')

# Does players_on have Weaver but off AND def both don't?
reverse = df[
    df['players_on'].str.contains(WEAVER, na=False) & 
    ~df['off_players_on'].str.contains(WEAVER, na=False) & 
    ~df['def_players_on'].str.contains(WEAVER, na=False)
]
print(f'Rows where Weaver in players_on but neither off nor def: {len(reverse)}')