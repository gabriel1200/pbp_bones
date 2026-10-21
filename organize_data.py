"""
organize_data.py
=================
Combines per-game CSVs from pbp_data/ (produced by async_scrape.py) into
season-level files, one per team/year/game-type, matching the format
build_season_files.py produces for the pre-2020 archive.

CHANGE FROM THE PRIOR VERSION: this now bakes in poc_ok, the 44
precomputed text-matching flags, and a sorted players_on directly --
reusing the same tested functions enrich_cdn_season_files.py already
has, rather than writing raw, unenriched files and requiring a separate
enrichment pass afterward. Confirmed directly this was a real gap: the
prior version's own verify_organized_data() checked for date/playoffs/
team/opp_team but never checked for poc_ok or any _flag_ column, because
it never computed them -- and copy.sh copies this script's output
straight into web_app/data/pbp/, the same live directory
enrich_cdn_season_files.py operates on, with no enrichment step in
between. This makes the two-step "organize, then separately remember to
enrich" pattern unnecessary going forward: this script now IS the
canonical way new post-2020 data reaches its final format in one pass.
enrich_cdn_season_files.py remains useful only as a backfill tool for
files that were already written before this change.

Usage:
    python organize_data.py
"""

import pandas as pd
import os
import glob
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

from enrich_cdn_season_files import compute_poc_ok, sort_players_on
from precompute_text_flags import precompute_text_flags

# The CDN source this pipeline is built for only exists from the 2020-21
# season onward (filename year convention is season-end-year, so 2020-21
# -> 2021). Pre-2021 games are already handled by the separate legacy
# pipeline (legacy_pipeline.py / build_season_files.py), which has
# rotation-reconciliation machinery this script was never built to need
# or run. Confirmed directly: this directory, inherited from an older
# working setup, has pre-2021 files mixed in alongside the real CDN-era
# ones -- without this filter they'd get silently processed through the
# wrong pipeline entirely, not just included as harmless extras.
MIN_YEAR = 2021


def load_game_dates():
    """Load game dates data from GitHub"""
    url = 'https://raw.githubusercontent.com/gabriel1200/shot_data/refs/heads/master/game_dates.csv'
    try:
        game_dates_df = pd.read_csv(url)
        print(f"Loaded game dates data: {len(game_dates_df)} rows")
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
        return 'ps'
    elif game_id_str.startswith('2'):
        return 'rs'
    else:
        return 'unknown'


def get_teams_in_game(df):
    """Get the two teams that participated in the game"""
    teams = df['teamId'].dropna().unique()
    valid_teams = []
    for team in teams:
        try:
            valid_teams.append(str(int(team)))
        except (ValueError, TypeError):
            continue
    return valid_teams


def merge_game_dates_data(game_df, game_dates_df):
    """Merge game dates data with the game DataFrame"""
    if game_dates_df is None:
        print("Warning: No game dates data available for merging")
        return game_df

    game_df['game_id_str'] = game_df['game_id'].astype(str)
    game_df['teamId_str'] = game_df['teamId'].astype(int).astype(str)
    game_df['merge_key'] = game_df['game_id_str'] + '_' + game_df['teamId_str']
    game_dates_df['merge_key'] = game_dates_df['GAME_ID'] + '_' + game_dates_df['TEAM_ID']

    merged_df = game_df.merge(
        game_dates_df[['merge_key', 'date', 'playoffs', 'team', 'opp_team']],
        on='merge_key',
        how='left'
    )
    merged_df = merged_df.drop(['merge_key', 'game_id_str', 'teamId_str'], axis=1)

    matched_rows = merged_df['date'].notna().sum()
    total_rows = len(merged_df)
    print(f"    Merged game dates: {matched_rows}/{total_rows} rows matched")
    return merged_df


def collect_and_organize_data():
    """Main function to collect, organize, and enrich scraped PBP data"""
    game_dates_df = load_game_dates()

    os.makedirs('organized_data', exist_ok=True)
    os.makedirs('organized_data/regular_season', exist_ok=True)
    os.makedirs('organized_data/playoffs', exist_ok=True)

    pbp_files_all = glob.glob('pbp_data/*.csv')
    if not pbp_files_all:
        print("No PBP data files found in pbp_data directory!")
        return

    print(f"Found {len(pbp_files_all)} PBP data files total")

    # Filter by filename year BEFORE the main loop, not during it -- so the
    # "files to process" count printed below is immediately, visibly
    # correct, rather than only showing up in the final summary after a
    # long run. Confirmed directly this mattered: printing the raw glob
    # count first (with filtering only reflected much later) made a
    # correctly-working filter look broken, since there was no visible
    # sign anything had happened yet.
    pbp_files = []
    pre_cdn_era_skipped = 0
    for file_path in pbp_files_all:
        filename = os.path.basename(file_path)
        if '_' not in filename:
            continue
        try:
            year = int(filename.split('_')[0])
        except ValueError:
            continue
        if year < MIN_YEAR:
            pre_cdn_era_skipped += 1
        else:
            pbp_files.append(file_path)

    print(f"Excluded {pre_cdn_era_skipped} pre-{MIN_YEAR} file(s) -- not part of this pipeline")
    print(f"{len(pbp_files)} file(s) remain to process")

    if not pbp_files:
        print(f"No post-{MIN_YEAR} PBP data files found -- nothing to do.")
        return

    team_games = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    processed_files = 0
    skipped_files = 0

    for file_path in pbp_files:
        try:
            filename = os.path.basename(file_path)
            if '_' not in filename:
                print(f"Skipping file with unexpected format: {filename}")
                skipped_files += 1
                continue

            year = filename.split('_')[0]
            game_df = pd.read_csv(file_path)

            if game_df.empty:
                print(f"Skipping empty file: {filename}")
                skipped_files += 1
                continue

            required_columns = ['teamId', 'game_id']
            missing_columns = [col for col in required_columns if col not in game_df.columns]
            if missing_columns:
                print(f"Skipping file {filename} - missing columns: {missing_columns}")
                skipped_files += 1
                continue

            game_df = merge_game_dates_data(game_df, game_dates_df)

            teams_in_game = get_teams_in_game(game_df)
            if len(teams_in_game) == 0:
                print(f"No valid team IDs found in {filename}")
                skipped_files += 1
                continue

            game_ids = game_df['game_id'].dropna().unique()
            if len(game_ids) == 0:
                print(f"No valid game IDs found in {filename}")
                skipped_files += 1
                continue

            game_type = determine_game_type(game_ids[0])
            if game_type == 'unknown':
                print(f"Unknown game type for {filename} (game_id: {game_ids[0]})")
                skipped_files += 1
                continue

            for team_id in teams_in_game:
                team_acronym = get_team_acronym_from_id(team_id)
                team_games[team_acronym][year][game_type].append(game_df.copy())

            processed_files += 1
            if processed_files % 100 == 0:
                print(f"Processed {processed_files} files...")

        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
            skipped_files += 1
            continue

    print(f"\nProcessed {processed_files} files, skipped {skipped_files} files "
          f"({pre_cdn_era_skipped} of those were pre-{MIN_YEAR}, not part of this pipeline)")

    total_files_created = 0

    for team_acronym in team_games:
        for year in team_games[team_acronym]:
            for game_type in team_games[team_acronym][year]:
                combined_games_df = pd.concat(team_games[team_acronym][year][game_type], ignore_index=True)
                combined_games_df = combined_games_df.sort_values(['date', 'period', 'actionNumber'])

                # --- Enrichment, baked in here rather than as a separate
                # later step (see module docstring for why) ---
                combined_games_df['poc_ok'] = compute_poc_ok(combined_games_df)
                combined_games_df = sort_players_on(combined_games_df)
                combined_games_df = precompute_text_flags(combined_games_df)

                game_type_folder = 'regular_season' if game_type == 'rs' else 'playoffs'
                filename = f"organized_data/{game_type_folder}/{team_acronym}_{year}_{game_type}.csv"
                filename2 = f"organized_data/{game_type_folder}/{team_acronym}_{year}_{game_type}.parquet"

                combined_games_df.to_csv(filename, index=False)
                combined_games_df.to_parquet(filename2, index=False)

                unique_games = combined_games_df['game_id'].nunique()
                games_with_dates = combined_games_df.groupby('game_id')['date'].first().notna().sum()
                non_sub = combined_games_df[combined_games_df['actionType'] != 'substitution']
                flagged = (~non_sub['poc_ok'].astype(bool)).sum()

                total_files_created += 1
                print(f"Created: {filename} ({len(combined_games_df)} rows, {unique_games} games, "
                      f"{games_with_dates} games with dates, {flagged} flagged rows)")

    print(f"\nData organization complete!")
    print(f"Total files created: {total_files_created}")

    print("\nSummary by team:")
    for team_acronym in sorted(team_games.keys()):
        years = sorted(team_games[team_acronym].keys())
        rs_years, ps_years = [], []
        for year in years:
            if 'rs' in team_games[team_acronym][year]:
                rs_years.append(f"{year}({len(team_games[team_acronym][year]['rs'])})")
            if 'ps' in team_games[team_acronym][year]:
                ps_years.append(f"{year}({len(team_games[team_acronym][year]['ps'])})")
        print(f"  {team_acronym}: RS: {rs_years}, PS: {ps_years}")


def verify_organized_data():
    """Verify the organized data files, including the enrichment columns"""
    print("\nVerifying organized data files...")

    rs_files = glob.glob('organized_data/regular_season/*.csv')
    ps_files = glob.glob('organized_data/playoffs/*.csv')
    print(f"Regular season files: {len(rs_files)}")
    print(f"Playoff files: {len(ps_files)}")

    sample_files = (rs_files + ps_files)[:5]
    for file_path in sample_files:
        try:
            df = pd.read_csv(file_path)
            filename = os.path.basename(file_path)

            teams_in_data = df['teamId'].dropna().unique()
            team_acronyms = [get_team_acronym_from_id(tid) for tid in teams_in_data]
            unique_games = df['game_id'].nunique()

            has_date = 'date' in df.columns
            has_playoffs = 'playoffs' in df.columns
            has_team = 'team' in df.columns
            has_opp_team = 'opp_team' in df.columns
            has_poc_ok = 'poc_ok' in df.columns
            n_flags = sum(1 for c in df.columns if c.startswith('_flag_'))

            rows_with_dates = df['date'].notna().sum() if has_date else 0

            print(f"  {filename}: {len(df)} rows, {unique_games} games, teams: {team_acronyms}")
            print(f"    date: {has_date}({rows_with_dates}), playoffs: {has_playoffs}, "
                  f"team: {has_team}, opp_team: {has_opp_team}, poc_ok: {has_poc_ok}, "
                  f"flag columns: {n_flags}/44")

            game_ids = df['game_id'].unique()
            game_types = [determine_game_type(gid) for gid in game_ids]
            if len(set(game_types)) > 1:
                print(f"    WARNING: Mixed game types found: {set(game_types)}")
            if len(teams_in_data) < 2:
                print(f"    WARNING: Expected 2 teams, found {len(teams_in_data)}")

        except Exception as e:
            print(f"    ERROR reading {file_path}: {e}")


if __name__ == "__main__":
    print("Starting NBA PBP data collection and organization...")
    collect_and_organize_data()
    verify_organized_data()
    print("\nProcess complete!")