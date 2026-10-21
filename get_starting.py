from nba_api.stats.endpoints import boxscoreadvancedv2
from nba_api.stats.library.http import NBAStatsHTTP

# Override headers globally
NBAStatsHTTP().headers.update({
    "Host": "stats.nba.com",
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com"
})

game_id = "0021700807"

boxscore = boxscoreadvancedv2.BoxScoreAdvancedV2(game_id=game_id)
player_df, team_df = boxscore.get_data_frames()