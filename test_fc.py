"""
test_sc_fix.py
==============
Validates the second-chance qualifier fix on already-converted game CSVs,
without requiring a full reconversion.

Usage
-----
# Run the built-in game registry:
    python test_sc_fix.py

# Verbose mode (prints patched rows + SC possession breakdown per game):
    python test_sc_fix.py --verbose

# First-time baseline for a new game (no expectations needed yet):
    python test_sc_fix.py path/to/YEAR_GAMEID.csv

# Add new games to GAME_REGISTRY below with their expected post-fix numbers.

Notes on expected values
------------------------
The engine counts ALL second-chance possessions regardless of outcome
(0-pt possessions included). Reference sites like PBPStats appear to only
count SC possessions that contain a scoring play, so their UI numbers will
be lower. Set expected values by running the patched engine once, recording
its output, and pasting those numbers in as the regression baseline.
"""

import sys
import os
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENGINE_PATH = "."   # directory containing pbp_stats_engine.py

# Registry of test games.
# Keys are CSV filenames (basename only — script looks next to itself first,
# then falls back to a cwd-relative path). Values are dicts with:
#
#   team_ids : {abbr: team_id}  for every team in the game
#   select   : team abbreviation to run the engine as
#   before   : {'poss': int, 'pts': int}  expected values WITHOUT the fix
#   after    : {'poss': int, 'pts': int}  expected values WITH the fix
#
# To add a new game:
#   1. Drop its CSV alongside this script (or use a full path as the key).
#   2. Fill in team_ids and select.
#   3. Leave before/after as None on first run — the script prints actuals
#      so you can paste them in as the permanent baseline.

GAME_REGISTRY = {
    "2006_20500016.csv": {
        "team_ids": {
            "LAL": 1610612747,
            "DEN": 1610612743,
        },
        "select": "LAL",
        "before": {"poss": 6,  "pts": 5},
        "after":  {"poss": 12, "pts": 13},
    },
    # ── Add more games here ──────────────────────────────────────────────────
    # "2007_20600123.csv": {
    #     "team_ids": {"BOS": 1610612738, "LAL": 1610612747},
    #     "select": "BOS",
    #     "before": None,   # fill in after first run
    #     "after":  None,
    # },
}

# ---------------------------------------------------------------------------
# Core patch function — mirrors the corrected step 12b in legacy_pipeline.py
# ---------------------------------------------------------------------------

def patch_second_chance_qualifiers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Re-derives '2ndchance' qualifiers from scratch on an already-converted
    game DataFrame, replacing the broken shift(1) logic in legacy_pipeline.py.

    The old logic only tagged shots immediately preceded by an OREB, missing
    every case where a foul, substitution, or timeout separated the rebound
    from the next shot — which is the common pattern for player OREBs.

    This version walks rows in chronological order and maintains a per-team
    SC flag that:
      - Activates on any live offensive rebound (team or player).
      - Tags only that same team's subsequent shots/FTs as '2ndchance'.
      - Resets on: any FG attempt, any made FT, any turnover, any defensive
        rebound, an opposing-team shot while the flag is live, or a period
        boundary.

    Edge cases handled:
      - Rebound after a made FG: guarded by last_shot_result != 'Made' so
        dead-ball administrative records are never treated as live OREBs.
      - Made FT resets the flag; missed FTs continue via OREB if live.
      - If the opposing team shoots while our SC flag is live the ball changed
        hands and the SC opportunity is dead.
    """
    df = df.copy()

    # Sort to match engine row order
    df = df.sort_values(
        ["game_id", "period", "clock_display", "actionNumber"],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)

    action      = df["actionType"].astype(str)
    desc        = df["description"].fillna("").astype(str).str.lower()
    team        = df["teamId"]
    period      = df["period"]
    qualifier   = df["qualifier"].astype(str)
    shot_result = df["shotResult"].fillna("").astype(str)

    is_shot_att = action.isin(["2pt", "3pt"])
    is_ft       = action == "freethrow"
    is_any_shot = is_shot_att | is_ft

    last_shot_team   = team.where(is_any_shot).ffill()
    last_shot_result = shot_result.where(is_any_shot).ffill()

    is_rebound  = action == "rebound"
    is_turnover = action == "turnover"
    is_team_reb = qualifier.str.contains("team", na=False)

    is_oreb = (
        is_rebound
        & (last_shot_result != "Made")
        & (
            desc.str.contains("offensive", na=False)    # team OREB
            | (~is_team_reb & (team == last_shot_team)) # player OREB
        )
    )
    is_dreb = is_rebound & ~is_oreb

    in_sc      = False
    sc_team_id = None
    sc_rows    = []

    for i in range(len(df)):
        # Period boundary resets possession state
        if i > 0 and period.iloc[i] != period.iloc[i - 1]:
            in_sc = False; sc_team_id = None

        if is_oreb.iloc[i]:
            in_sc = True; sc_team_id = team.iloc[i]

        # Opposing-team shot kills the SC opportunity
        if in_sc and (is_shot_att.iloc[i] or is_ft.iloc[i]) and team.iloc[i] != sc_team_id:
            in_sc = False; sc_team_id = None

        # Tag only the SC team's own shots
        if in_sc and team.iloc[i] == sc_team_id and (is_shot_att.iloc[i] or is_ft.iloc[i]):
            sc_rows.append(df.index[i])

        # Possession-ending events reset the flag
        if is_shot_att.iloc[i] or is_turnover.iloc[i] or is_dreb.iloc[i]:
            in_sc = False; sc_team_id = None

        if is_ft.iloc[i] and shot_result.iloc[i] == "Made":
            in_sc = False; sc_team_id = None

    def _add_sc(q: str) -> str:
        if "2ndchance" in q:
            return q
        if q.strip() in ("[]", ""):
            return "['2ndchance']"
        return q.rstrip("]") + ", '2ndchance']"

    df.loc[sc_rows, "qualifier"] = df.loc[sc_rows, "qualifier"].apply(_add_sc)
    return df


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def build_team_col(df: pd.DataFrame, team_ids: dict) -> pd.DataFrame:
    """Add a 'team' abbreviation column from teamId using the provided map."""
    inv = {v: k for k, v in team_ids.items()}
    df = df.copy()
    df["team"] = df["teamId"].apply(lambda x: inv.get(round(x), "UNK"))
    return df


def run_game(
    csv_path: str,
    team_ids: dict,
    select: str,
    expected_before: dict | None,
    expected_after: dict | None,
    verbose: bool = False,
) -> bool:
    """
    Run before/after SC test for one game CSV.
    Returns True if all expectations are met (or if expectations are None).
    """
    sys.path.insert(0, ENGINE_PATH)
    from pbp_stats_engine import compute_aggregated_pipeline_stats

    df = pd.read_csv(csv_path)
    df = build_team_col(df, team_ids)
    df["InLineupFilter"] = True

    label = os.path.basename(csv_path)
    pad   = "=" * 60
    print(f"\n{pad}")
    print(f"  {label}  |  select={select}")
    print(pad)

    # ── BEFORE ────────────────────────────────────────────────────────────────
    r_before, _, _ = compute_aggregated_pipeline_stats(
        df.copy(), select, _return_enriched_df=True
    )
    b_poss = r_before.get("SecondChanceOffPoss")
    b_pts  = r_before.get("SecondChancePoints")

    before_ok = True
    if expected_before is None:
        print(f"  BEFORE  poss={b_poss}  pts={b_pts}  (no expectation set)")
    else:
        ep, et  = expected_before["poss"], expected_before["pts"]
        pok, tok = b_poss == ep, b_pts == et
        before_ok = pok and tok
        print(
            f"  BEFORE  poss={b_poss} (exp {ep}) {'✅' if pok else '❌'}  "
            f"pts={b_pts} (exp {et}) {'✅' if tok else '❌'}  "
            f"{'✅' if before_ok else '❌'}"
        )

    # ── PATCH ─────────────────────────────────────────────────────────────────
    df_patched = patch_second_chance_qualifiers(df)

    changed = df_patched[
        df_patched["qualifier"] != df["qualifier"].reindex(df_patched.index)
    ]
    print(f"  Rows patched: {len(changed)}")

    if verbose and not changed.empty:
        print("\n  Changed rows:")
        print(
            changed[["period", "clock_display", "actionType",
                      "description", "team", "shotResult"]]
            .to_string()
        )

    # ── AFTER ─────────────────────────────────────────────────────────────────
    r_after, _, enriched = compute_aggregated_pipeline_stats(
        df_patched.copy(), select, _return_enriched_df=True
    )
    a_poss = r_after.get("SecondChanceOffPoss")
    a_pts  = r_after.get("SecondChancePoints")

    after_ok = True
    if expected_after is None:
        print(
            f"  AFTER   poss={a_poss}  pts={a_pts}  "
            f"(no expectation set — paste these in as your 'after' baseline)"
        )
    else:
        ep, et   = expected_after["poss"], expected_after["pts"]
        pok, tok = a_poss == ep, a_pts == et
        after_ok = pok and tok
        print(
            f"  AFTER   poss={a_poss} (exp {ep}) {'✅' if pok else '❌'}  "
            f"pts={a_pts} (exp {et}) {'✅' if tok else '❌'}  "
            f"{'✅' if after_ok else '❌'}"
        )

    # ── VERBOSE SC BREAKDOWN ──────────────────────────────────────────────────
    if verbose:
        sc_ids = enriched[enriched["IsSecondChance"] == True]["GlobalPossID"].unique()
        print(f"\n  SC possession breakdown ({select} offense, {len(sc_ids)} poss total):")
        for pid in sorted(sc_ids):
            rows  = enriched[enriched["GlobalPossID"] == pid]
            s_pts = int(rows[rows["team"] == select]["EventPoints"].sum())
            o_pts = int(rows[rows["team"] != select]["EventPoints"].sum())
            print(f"\n  Poss {pid}  {select}:{s_pts}pts  opp:{o_pts}pts")
            print(
                rows[["period", "clock_display", "actionType",
                       "description", "team", "shotResult",
                       "EventPoints", "qualifier"]]
                .to_string()
            )

    return before_ok and after_ok


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    # Single-file mode: python test_sc_fix.py path/to/file.csv [--verbose]
    non_flag_args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if non_flag_args:
        csv_arg = non_flag_args[0]
        if not os.path.exists(csv_arg):
            print(f"File not found: {csv_arg}")
            sys.exit(1)

        # Auto-detect team IDs from the CSV so you don't need a registry entry
        df_probe = pd.read_csv(csv_arg)
        raw_ids  = sorted(
            int(t) for t in df_probe["teamId"].dropna().unique()
            if int(t) > 1_000_000
        )
        team_ids = {f"T{i+1}": tid for i, tid in enumerate(raw_ids)}
        select   = list(team_ids.keys())[0]
        print(f"Auto-detected teams: {team_ids}")
        print(f"Running as select='{select}' — add a GAME_REGISTRY entry for full control.\n")
        run_game(
            csv_arg, team_ids, select,
            expected_before=None, expected_after=None,
            verbose=True,
        )
        sys.exit(0)

    # Registry mode: run all registered games
    results = []
    for csv_name, cfg in GAME_REGISTRY.items():
        script_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path   = os.path.join(script_dir, csv_name)
        if not os.path.exists(csv_path):
            csv_path = csv_name
        if not os.path.exists(csv_path):
            print(f"\n⚠️  CSV not found, skipping: {csv_name}")
            results.append((csv_name, False))
            continue

        ok = run_game(
            csv_path,
            team_ids        = cfg["team_ids"],
            select          = cfg["select"],
            expected_before = cfg.get("before"),
            expected_after  = cfg.get("after"),
            verbose         = verbose,
        )
        results.append((csv_name, ok))

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in results if ok)
    print(f"  {passed}/{len(results)} games passed")
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'}  {name}")
    print("=" * 60)