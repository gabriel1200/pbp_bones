import pandas as pd

url = "https://www.basketball-reference.com/players/l/leonaka01/gamelog/2026/"

tables = pd.read_html(url)

# Get correct table
for table in tables:
    if 'MP' in table.columns:
        df = table
        break

# Remove repeated header rows
df = df[df['MP'] != 'MP']

# Function to convert MP → decimal minutes
def mp_to_decimal(mp):
    try:
        if isinstance(mp, str) and ':' in mp:
            m, s = mp.split(':')
            return round(int(m) + int(s) / 60, 2)
    except:
        pass
    return None  # for Inactive / blanks

# Apply conversion
df['MP_decimal'] = df['MP'].apply(mp_to_decimal)

# Fill blanks nicely for display
df['MP_decimal_display'] = df['MP_decimal'].apply(
    lambda x: f"{x:.2f}" if pd.notna(x) else ""
)

# Select useful columns
output = df[['Date', 'Opp', 'MP', 'MP_decimal_display']]

# Print row by row
for _, row in output.iterrows():
    print(f"{row['Date']} vs {row['Opp']} | {row['MP']} | {row['MP_decimal_display']}")