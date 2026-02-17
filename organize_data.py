import pandas as pd
import os
import glob
from collections import defaultdict
import warnings
import requests
warnings.filterwarnings('ignore')

def load_game_dates():
    """Load game dates data from GitHub"""
    url = 'https://raw.githubusercontent.com/gabriel1200/shot_data/refs/heads/master/game_dates.csv'
    try:
        game_dates_df = pd.read_csv(url)
        print(f"Loaded game dates data: {len(game_dates_df)} rows")
        
        # Convert GAME_ID and TEAM_ID to strings for consistent matching
        game_dates_df['GAME_ID'] = game_dates_df['GAME_ID'].astype(str)
        game_dates_df['TEAM_ID'] = game_dates_df['TEAM_ID'].astype(str)
        
        return game_dates_df
    except Exception as e:
        print(f"Error loading game dates data: {e}")
        return None

def get_team_acronym_from_id(team_id):
    """Convert team ID to team acronym using the provided dictionary"""
    team_dict = {
        '1610612760': 'OKC', '1610612749': 'MIL', '1610612758': 'SAC', '1610612747': 'LAL',
        '1610612738': 'BOS', '1610612743': 'DEN', '1610612750': 'MIN', '1610612752': 'NYK',
        '1610612756': 'PHX', '1610612753': 'ORL', '1610612766': 'CHA', '1610612739': 'CLE',
        '1610612746': 'LAC', '1610612737': 'ATL', '1610612748': 'MIA', '1610612742': 'DAL',
        '1610612765': 'DET', '1610612763': 'MEM', '1610612761': 'TOR', '1610612741': 'CHI',
        '1610612754': 'IND', '1610612759': 'SAS', '1610612745': 'HOU', '1610612751': 'BKN',
        '1610612764': 'WAS', '1610612744': 'GSW', '1610612755': 'PHI', '1610612762': 'UTA',
        '1610612757': 'POR', '1610612740': 'NOP'
    }
    
    team_id_str = str(int(team_id)) if pd.notna(team_id) else None
    return team_dict.get(team_id_str, f'UNKNOWN_{team_id_str}')

def determine_game_type(game_id):
    """Determine if game is regular season (rs) or playoffs (ps) based on game ID"""
    game_id_str = str(game_id)
    if game_id_str.startswith('4'):
        return 'ps'  # Playoffs
    elif game_id_str.startswith('2'):
        return 'rs'  # Regular season
    else:
        return 'unknown'

def get_teams_in_game(df):
    """Get the two teams that participated in the game"""
    teams = df['teamId'].dropna().unique()
    # Filter out any invalid team IDs and convert to strings
    valid_teams = []
    for team in teams:
        try:
            team_str = str(int(team))
            valid_teams.append(team_str)
        except (ValueError, TypeError):
            continue
    
    return valid_teams

def merge_game_dates_data(game_df, game_dates_df):
    """Merge game dates data with the game DataFrame"""
    if game_dates_df is None:
        print("Warning: No game dates data available for merging")
        return game_df
    
    # Convert game_df columns to strings for consistent matching
    game_df['game_id_str'] = game_df['game_id'].astype(str)
    game_df['teamId_str'] = game_df['teamId'].astype(int).astype(str)
    
    # Create merge key
    game_df['merge_key'] = game_df['game_id_str'] + '_' + game_df['teamId_str']
    game_dates_df['merge_key'] = game_dates_df['GAME_ID'] + '_' + game_dates_df['TEAM_ID']
    
    # Merge the data
    merged_df = game_df.merge(
        game_dates_df[['merge_key', 'date', 'playoffs', 'team', 'opp_team']], 
        on='merge_key', 
        how='left'
    )
    
    # Clean up temporary columns
    merged_df = merged_df.drop(['merge_key', 'game_id_str', 'teamId_str'], axis=1)
    
    # Report merge statistics
    matched_rows = merged_df['date'].notna().sum()
    total_rows = len(merged_df)
    print(f"    Merged game dates: {matched_rows}/{total_rows} rows matched")
    
    return merged_df

def collect_and_organize_data():
    """Main function to collect and organize scraped PBP data"""
    
    # Load game dates data first
    game_dates_df = load_game_dates()
    
    # Create output directories
    os.makedirs('organized_data', exist_ok=True)
    os.makedirs('organized_data/regular_season', exist_ok=True)
    os.makedirs('organized_data/playoffs', exist_ok=True)
    
    # Get all CSV files from pbp_data directory
    pbp_files = glob.glob('pbp_data/*.csv')
    
    if not pbp_files:
        print("No PBP data files found in pbp_data directory!")
        return
    
    print(f"Found {len(pbp_files)} PBP data files")
    
    # Dictionary to store complete game data by team, year, and game type
    # Structure: team_games[team_acronym][year][game_type] = [list of complete game DataFrames]
    team_games = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    
    # Process each file (each file represents one complete game)
    processed_files = 0
    skipped_files = 0
    
    for file_path in pbp_files:
        try:
            # Extract year from filename (format: YYYY_GAMEID.csv)
            filename = os.path.basename(file_path)
            if '_' not in filename:
                print(f"Skipping file with unexpected format: {filename}")
                skipped_files += 1
                continue
            
            year = filename.split('_')[0]
            
            # Read the complete game CSV file
            game_df = pd.read_csv(file_path)
            
            if game_df.empty:
                print(f"Skipping empty file: {filename}")
                skipped_files += 1
                continue
            
            # Check if required columns exist
            required_columns = ['teamId', 'game_id']
            missing_columns = [col for col in required_columns if col not in game_df.columns]
            if missing_columns:
                print(f"Skipping file {filename} - missing columns: {missing_columns}")
                skipped_files += 1
                continue
            
            # Merge with game dates data
            game_df = merge_game_dates_data(game_df, game_dates_df)
            
            # Get the teams that participated in this game
            teams_in_game = get_teams_in_game(game_df)
            
            if len(teams_in_game) == 0:
                print(f"No valid team IDs found in {filename}")
                skipped_files += 1
                continue
            
            # Determine game type from game_id
            game_ids = game_df['game_id'].dropna().unique()
            if len(game_ids) == 0:
                print(f"No valid game IDs found in {filename}")
                skipped_files += 1
                continue
            
            # Use first game_id to determine game type (should be consistent within file)
            game_type = determine_game_type(game_ids[0])
            
            if game_type == 'unknown':
                print(f"Unknown game type for {filename} (game_id: {game_ids[0]})")
                skipped_files += 1
                continue
            
            # Add this complete game to each participating team's collection
            for team_id in teams_in_game:
                team_acronym = get_team_acronym_from_id(team_id)
                
                # Add the complete game DataFrame (includes both teams' actions)
                team_games[team_acronym][year][game_type].append(game_df.copy())
            
            processed_files += 1
            
            if processed_files % 100 == 0:
                print(f"Processed {processed_files} files...")
                
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
            skipped_files += 1
            continue
    
    print(f"\nProcessed {processed_files} files, skipped {skipped_files} files")
    
    # Combine and save data for each team/year/game_type combination
    total_files_created = 0
    
    for team_acronym in team_games:
        for year in team_games[team_acronym]:
            for game_type in team_games[team_acronym][year]:
                # Combine all complete games for this team/year/game_type
                combined_games_df = pd.concat(team_games[team_acronym][year][game_type], ignore_index=True)
                
                # Sort by game_id and actionNumber for consistent ordering
                combined_games_df = combined_games_df.sort_values(['date','period','actionNumber'])
                
                # Create filename
                game_type_folder = 'regular_season' if game_type == 'rs' else 'playoffs'
                filename = f"organized_data/{game_type_folder}/{team_acronym}_{year}_{game_type}.csv"
                filename2 = f"organized_data/{game_type_folder}/{team_acronym}_{year}_{game_type}.parquet"
                
                # Save to CSV
                combined_games_df.to_csv(filename, index=False)
                combined_games_df.to_parquet(filename2,index=False)
                # Count unique games for this team
                unique_games = combined_games_df['game_id'].nunique()
                
                # Count games with date information
                games_with_dates = combined_games_df.groupby('game_id')['date'].first().notna().sum()
                
                total_files_created += 1
                print(f"Created: {filename} ({len(combined_games_df)} rows, {unique_games} games, {games_with_dates} games with dates)")
    
    print(f"\nData organization complete!")
    print(f"Total files created: {total_files_created}")
    
    # Print summary statistics
    print("\nSummary by team:")
    for team_acronym in sorted(team_games.keys()):
        years = sorted(team_games[team_acronym].keys())
        rs_years = []
        ps_years = []
        
        for year in years:
            if 'rs' in team_games[team_acronym][year]:
                rs_games = len(team_games[team_acronym][year]['rs'])
                rs_years.append(f"{year}({rs_games})")
            if 'ps' in team_games[team_acronym][year]:
                ps_games = len(team_games[team_acronym][year]['ps'])
                ps_years.append(f"{year}({ps_games})")
        
        print(f"  {team_acronym}: RS: {rs_years}, PS: {ps_years}")

def verify_organized_data():
    """Verify the organized data files"""
    print("\nVerifying organized data files...")
    
    rs_files = glob.glob('organized_data/regular_season/*.csv')
    ps_files = glob.glob('organized_data/playoffs/*.csv')
    
    print(f"Regular season files: {len(rs_files)}")
    print(f"Playoff files: {len(ps_files)}")
    
    # Sample a few files to verify structure
    sample_files = (rs_files + ps_files)[:5]
    
    for file_path in sample_files:
        try:
            df = pd.read_csv(file_path)
            filename = os.path.basename(file_path)
            
            # Get team info
            teams_in_data = df['teamId'].dropna().unique()
            team_acronyms = [get_team_acronym_from_id(tid) for tid in teams_in_data]
            unique_games = df['game_id'].nunique()
            
            # Check for new columns
            has_date = 'date' in df.columns
            has_playoffs = 'playoffs' in df.columns
            has_team = 'team' in df.columns
            has_opp_team = 'opp_team' in df.columns
            
            # Count rows with date information
            rows_with_dates = df['date'].notna().sum() if has_date else 0
            
            print(f"  {filename}: {len(df)} rows, {unique_games} games, teams: {team_acronyms}")
            print(f"    New columns - date: {has_date}({rows_with_dates}), playoffs: {has_playoffs}, team: {has_team}, opp_team: {has_opp_team}")
            
            # Check game type consistency
            game_ids = df['game_id'].unique()
            game_types = [determine_game_type(gid) for gid in game_ids]
            unique_game_types = set(game_types)
            
            if len(unique_game_types) > 1:
                print(f"    WARNING: Mixed game types found: {unique_game_types}")
            
            # Verify both teams' actions are present
            if len(teams_in_data) < 2:
                print(f"    WARNING: Expected 2 teams, found {len(teams_in_data)}")
            
            # Show sample of new data
            if has_date and rows_with_dates > 0:
                sample_row = df[df['date'].notna()].iloc[0]
                print(f"    Sample: date={sample_row.get('date', 'N/A')}, team={sample_row.get('team', 'N/A')}, opp_team={sample_row.get('opp_team', 'N/A')}")
            
        except Exception as e:
            print(f"    ERROR reading {file_path}: {e}")

if __name__ == "__main__":
    print("Starting NBA PBP data collection and organization...")
    collect_and_organize_data()
    verify_organized_data()
    print("\nProcess complete!")