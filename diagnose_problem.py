# In a quick diagnostic script on the new CSV:

import pandas as pd
df =pd.read_csv('organized_data/regular_season/OKC_2009_rs.csv')
df['n_pl'] = df['players_on'].apply(lambda s: len([p for p in str(s).split('|') if p not in ('nan','','0')]))
missing_score = df[
    df['actionType'].isin(['2pt','3pt','freethrow']) & 
    (df['shotResult']=='Made') &
    ~df['players_on'].str.contains('201602', na=False)
]
# Is the issue poc<10 (fixable) or poc=10 wrong player (harder)?
print(missing_score['n_pl'].value_counts().sort_index())
print('poc_ok breakdown:', missing_score['poc_ok'].value_counts().to_dict())