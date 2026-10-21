"""
precompute_text_flags.py
===========================
Precomputes every leaf-level .str.contains() result used across
compute_aggregated_pipeline_stats, calculate_lineup_stats, and
_compute_xfg_stats in pbp_stats_engine.py, as boolean columns on the raw
PBP DataFrame -- so the expensive regex/substring matching happens
exactly ONCE PER GAME, rather than once per function call (and these
functions are called at least once per team, sometimes more).

Confirmed via direct inspection that every one of these flags depends
only on a row's own description/qualifier/actionType text (or the
previous row's, via a simple shift) -- NONE depend on select_team_abbr,
so a single precomputed set is valid for every team's stats computation
of the same game.

Each consuming function is expected to use `_flag(df, name, compute_fn)`
at every call site that currently does `df['col'].str.contains(...)`
directly -- this returns the precomputed column if present, or falls
back to computing it fresh via compute_fn() if not (so every function
still works standalone, unenriched, with byte-identical results either
way -- only the SPEED differs, never the output).

Usage (called ONCE per game, before any per-team stats calls):
    df = precompute_text_flags(raw_pbp_df)
    stats_team_a = compute_aggregated_pipeline_stats(df, 'GSW')
    stats_team_b = compute_aggregated_pipeline_stats(df, 'OKC')
    # both calls reuse the same precomputed flags -- zero redundant
    # string matching across the two calls.
"""

import pandas as pd


def _parse_qualifier(qual_series):
    """Return a lowercase string version of the qualifier for substring
    matching. Identical, byte-for-byte, to pbp_stats_engine.py's own
    _parse_qualifier -- inlined here directly rather than imported, since
    build_season_files.py and pbp_stats_engine.py routinely live in
    different directories in practice (confirmed directly: build_season_
    files.py in ~/basketball/databall-pbp/, pbp_stats_engine.py in
    ~/basketball/web_app/utils/ -- siblings, neither on the other's
    Python import path by default). Importing across that gap would
    require the caller to configure sys.path correctly for their own
    specific directory layout every time; inlining this one trivial,
    three-line function removes that fragile dependency entirely. If
    pbp_stats_engine.py's own version of this function ever changes,
    update this copy to match.
    """
    return qual_series.fillna('').astype(str).str.lower()


def _flag(df, name, compute_fn):
    """Returns df[name] if it already exists (precomputed), otherwise
    computes it fresh via compute_fn() -- guarantees identical output
    either way, only the speed differs."""
    if name in df.columns:
        return df[name]
    return compute_fn()


def precompute_text_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a copy of df with every leaf-level text-matching flag
    used downstream added as a boolean column. Safe to call multiple
    times (idempotent) or skip entirely (every consumer falls back to
    inline computation via _flag() when a column is absent).

    CRITICAL: compute_aggregated_pipeline_stats does NOT use the raw
    description/qualifier text directly -- it first lowercases qualifier
    (via _parse_qualifier) and lowercases + rewrites description (two
    regex substitutions: 's.foul' -> 'shooting foul', 'off.foul' ->
    'offensive foul') before any .str.contains() check ever runs.
    Precomputing flags against the RAW text without this same
    preprocessing would silently produce wrong flags (confirmed directly:
    the raw-text version of the sub-out check matched zero rows, where
    the correctly-preprocessed version matches the expected ~100). This
    function replicates that exact preprocessing first, using the local
    _parse_qualifier defined at the top of this module (a direct,
    intentional inline copy of the engine's own version -- see that
    function's docstring for why it isn't imported instead).
    """
    df = df.copy()

    qual = _parse_qualifier(df['qualifier'])
    desc = df['description'].fillna('').astype(str).str.lower()
    desc = desc.str.replace(r'\bs\.foul\b', 'shooting foul', regex=True)
    desc = desc.str.replace(r'\boff\.foul\b', 'offensive foul', regex=True)

    # --- from _classify_rebounds ---
    df['_flag_qual_deadball'] = qual.str.contains('deadball', na=False, regex=False)
    df['_flag_qual_team'] = qual.str.contains('team', na=False, regex=False)
    df['_flag_desc_offensive'] = desc.str.contains('offensive', na=False, regex=False)
    df['_flag_desc_defensive'] = desc.str.contains('defensive', na=False, regex=False)
    _prev_desc = desc.groupby(df['game_id'], sort=False).shift(1).fillna('')
    df['_flag_prevdesc_last_ft'] = _prev_desc.str.contains(
        r'\b1 of 1\b|\b2 of 2\b|\b3 of 3\b', regex=True, na=False)

    # --- from build_change_mask ---
    df['_flag_desc_last_ft'] = desc.str.contains(
        r'\b1 of 1\b|\b2 of 2\b|\b3 of 3\b', regex=True, na=False)
    df['_flag_desc_retained_ft'] = desc.str.contains(
        r'technical|t\.foul|flagrant|clear path|away from play', regex=True, case=False, na=False)
    df['_flag_desc_off_foul'] = desc.str.contains(
        r'offensive|charge|off\.foul', regex=True, case=False, na=False)

    # --- from the main foul/free-throw classification section ---
    df['_flag_desc_first_ft'] = desc.str.contains(
        r'\b1 of 2\b|\b1 of 3\b|1for2|1for3', regex=True, na=False)
    df['_flag_desc_single_ft'] = desc.str.contains(r'\b1 of 1\b|1for1', regex=True, na=False)
    df['_flag_desc_tech_or_flagrant'] = desc.str.contains(
        r'technical|t\.foul|flagrant', regex=True, case=False, na=False)
    df['_flag_desc_shooting_or_tech'] = desc.str.contains(
        r'shooting|s\.foul|technical|t\.foul|flagrant', regex=True, case=False, na=False)
    df['_flag_desc_excluded_foul'] = desc.str.contains(
        r'offensive|charge|off\.foul|technical|t\.foul|double', regex=True, case=False, na=False)
    df['_flag_desc_flagrant'] = desc.str.contains('flagrant', na=False, regex=False)

    # --- from _apply_sub_out_corrections ---
    df['_flag_desc_sub_out'] = desc.str.contains('sub out', na=False, regex=False)

    # --- from _propagate_foul_lineups_to_freethrows ---
    df['_flag_desc_off_foul_ci'] = desc.str.contains(
        r'offensive|charge|off\.foul', regex=True, case=False, na=False)

    # --- from the event-classification block (~line 793 onward) ---
    df['_flag_desc_shooting_foul'] = desc.str.contains(
        r'shooting|s\.foul', regex=True, case=False, na=False)
    df['_flag_desc_technical'] = desc.str.contains(r'technical|t\.foul', regex=True, case=False, na=False)
    df['_flag_desc_charge'] = desc.str.contains(
        r'charge|charging|off\.foul|offensive foul', regex=True, case=False, na=False)
    df['_flag_desc_loose_ball'] = desc.str.contains('loose ball', na=False, regex=False)
    df['_flag_desc_offensive_ci'] = desc.str.contains(
        r'offensive|off\.foul', regex=True, case=False, na=False)
    df['_flag_desc_take'] = desc.str.contains('take', na=False, regex=False)
    df['_flag_desc_goaltend'] = desc.str.contains('goaltending', na=False, regex=False)
    df['_flag_desc_putback_tip'] = desc.str.contains(r'putback|tip', regex=True, na=False)
    df['_flag_desc_d3sec'] = desc.str.contains(
        r'defensive 3-second|defensive three second|d3 second', regex=True, case=False, na=False)
    df['_flag_desc_dead_turnover'] = desc.str.contains(
        r'offensive foul|shot clock|backcourt|out-of-bounds|out of bounds|turnover:\s*shot clock|'
        r'3 second violation|discontinue.*dribble|inbound turnover|double dribble|palming|violation|travel',
        regex=True, case=False, na=False)
    df['_flag_desc_bad_pass'] = desc.str.contains('bad pass', na=False, regex=False)
    df['_flag_desc_lost_ball'] = desc.str.contains('lost ball', na=False, regex=False)
    df['_flag_desc_travel'] = desc.str.contains('travel', na=False, regex=False)
    df['_flag_desc_step_oob'] = desc.str.contains('step out-of-bounds', na=False, regex=False)
    df['_flag_desc_oob'] = desc.str.contains('out-of-bounds', na=False, regex=False)
    _prev_desc2 = desc.groupby(df['game_id'], sort=False).shift(1).fillna('')
    df['_flag_prevdesc_bad_pass'] = _prev_desc2.str.contains('bad pass', na=False, regex=False)
    df['_flag_prevdesc_lost_ball'] = _prev_desc2.str.contains('lost ball', na=False, regex=False)
    df['_flag_qual_3ft'] = qual.str.contains('3freethrow', na=False, regex=False)
    df['_flag_qual_inpenalty'] = qual.str.contains('inpenalty', na=False, regex=False)
    df['_flag_qual_freethrow'] = qual.str.contains('freethrow', na=False, regex=False)
    df['_flag_qual_pitp'] = qual.str.contains('pointsinthepaint', na=False, regex=False)
    df['_flag_qual_fastbreak'] = qual.str.contains('fastbreak', na=False, regex=False)
    df['_flag_qual_fromturnover'] = qual.str.contains('fromturnover', na=False, regex=False)
    df['_flag_qual_2ndchance'] = qual.str.contains('2ndchance', na=False, regex=False)

    # --- from calculate_lineup_stats ---
    df['_flag_desc_freethrow_last'] = desc.str.contains(
        r'Free Throw (?:1 of 1|2 of 2|3 of 3)', case=False, regex=True, na=False)
    df['_flag_qual_lastfreethrow'] = qual.str.contains('lastfreethrow', na=False, regex=False)

    # --- from _compute_xfg_stats's QUALIFIERS loop ---
    for q in ['pointsinthepaint', 'fromturnover', 'fastbreak', '2ndchance', 'alleyoop']:
        df[f'_flag_qual_{q}'] = qual.str.contains(q, na=False, regex=False)

    return df