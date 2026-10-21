"""
enrich_cdn_season_files.py
=============================
The post-2020-21 NBA CDN data source already provides play-by-play in
almost exactly the target format legacy_pipeline.py was built to produce
for pre-2020 data -- confirmed directly against a real file
(PHX_2026_ps.parquet): all 29 core columns match legacy_pipeline.py's
own output exactly, plus the same 4 columns build_season_files.py adds
(date, playoffs, team, opp_team). Unlike pre-2020 data, this source's
players_on is ALREADY complete and correct natively (confirmed: 0
poc_ok=False rows across every game checked) -- none of the reconstruction
machinery built for the pre-2020 archive (reversed-stints fix, BRef
starter data, substitution-name resolution) is needed here, because
those all exist specifically to compensate for gaps THIS source doesn't
have.

The only two things genuinely missing to match the target format:
  1. poc_ok -- computed identically to legacy_pipeline.py's own version.
  2. The precomputed text-matching flags from precompute_text_flags.py --
     added here for consistency, so the stats engine gets the same
     speed benefit regardless of which era a given file came from.

--in-place mode: for running this DIRECTLY inside the engine's own
data/pbp/<regular_season|playoffs>/ directory, where post-2020 CDN files
often sit flat, side by side with pre-2020 files build_season_files.py
already enriched. Every file is checked for existing flag columns first
and safely SKIPPED if already enriched (idempotent, cheap to re-run over
a mixed directory without re-processing files that don't need it), then
enriched files are written back to the EXACT SAME PATH they were read
from -- no separate --out staging directory, no season_type subfolder
nesting (since running this from inside data/pbp/regular_season/ already
means the season type is implicit in the directory itself).

Usage:
    # Staging workflow (writes to a separate --out location):
    python enrich_cdn_season_files.py --input PHX_2026_ps.parquet --out season_pbp
    python enrich_cdn_season_files.py --input-dir raw_cdn_season_files --out season_pbp

    # In-place workflow (run directly inside the engine's own data dir):
    cd web_app/data/pbp/regular_season
    python enrich_cdn_season_files.py --input-dir . --in-place
"""

import argparse
import glob
import os

import pandas as pd

from precompute_text_flags import precompute_text_flags


def compute_poc_ok(df: pd.DataFrame) -> pd.Series:
    """Identical to legacy_pipeline.py's own poc_ok computation: exactly
    10 pipe-delimited entries in players_on."""
    poc = df['players_on'].fillna('').astype(str).str.count(r'\|') + 1
    return poc == 10


def already_enriched(df: pd.DataFrame) -> bool:
    """True if this file already has the precomputed flag columns (and
    poc_ok) -- whether from a prior run of this script, or because
    build_season_files.py already enriched it (pre-2020 files do, since
    that script bakes these in at build time)."""
    return 'poc_ok' in df.columns and any(c.startswith('_flag_') for c in df.columns)


def sort_players_on(df: pd.DataFrame) -> pd.DataFrame:
    """Sorts each row's players_on numerically -- same rationale as
    build_season_files.py's identical step: free while these files are
    being freshly generated/re-uploaded, would mean re-touching
    everything if added later. Needed for a future lineup_hash to be
    consistent regardless of substitution order; has no effect on any
    current consumer, which all do plain string-membership checks."""
    df = df.copy()
    df['players_on'] = df['players_on'].fillna('').apply(
        lambda s: '|'.join(sorted(s.split('|'), key=lambda x: int(x) if x.isdigit() else 0)) if s else s
    )
    return df


def enrich_cdn_file(input_path: str) -> pd.DataFrame:
    """Returns the enriched DataFrame -- adds poc_ok and every precomputed
    text-matching flag, without altering any existing column."""
    df = pd.read_parquet(input_path)

    if 'poc_ok' not in df.columns:
        df['poc_ok'] = compute_poc_ok(df)

    df = sort_players_on(df)
    df = precompute_text_flags(df)
    return df


def report_quality(df: pd.DataFrame, label: str):
    non_sub = df[df['actionType'] != 'substitution']
    bad = (~non_sub['poc_ok'].astype(bool)).sum()
    if bad:
        print(f"  [warn] {label}: {bad} / {len(non_sub)} flagged (poc_ok=False) rows -- "
              f"unexpected for CDN-sourced data, worth investigating this specific file "
              f"before trusting it the way the rest of the archive has been validated.")
    else:
        print(f"  {label}: 0 flagged rows across {df['game_id'].nunique()} game(s) -- clean.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', type=str, default=None, help="Single CDN-format parquet file to enrich.")
    parser.add_argument('--input-dir', type=str, default=None,
                         help="Directory of CDN-format parquet files to enrich. Searched "
                              "RECURSIVELY, so pointing this at a parent directory containing "
                              "both regular_season/ and playoffs/ subdirectories (e.g. "
                              "web_app/data/pbp) processes both in one pass -- pointing it at a "
                              "single season-type directory directly still works exactly as "
                              "before. Safe to point at a directory mixing already-enriched and "
                              "not-yet-enriched files.")
    parser.add_argument('--out', type=str, default="season_pbp",
                         help="Output root directory for the STAGING workflow (default: "
                              "season_pbp) -- matches build_season_files.py's own convention, "
                              "so files land in <out>/<regular_season|playoffs>/ ready for the "
                              "stats engine. Ignored when --in-place is set.")
    parser.add_argument('--in-place', action='store_true',
                         help="Write each enriched file back to the exact path it was read "
                              "from, instead of a separate --out location. For running this "
                              "directly inside the engine's own data/pbp/<season_type>/ "
                              "directory, where the season type is already implicit and no "
                              "staging copy is needed.")
    parser.add_argument('--overwrite', action='store_true',
                         help="Re-enrich files that already have poc_ok and flag columns "
                              "present, instead of skipping them. Rarely needed -- mainly for "
                              "if precompute_text_flags.py's own flag catalogue changes and "
                              "existing files need the new columns added.")
    args = parser.parse_args()

    if not args.input and not args.input_dir:
        raise SystemExit("Specify --input <file> or --input-dir <directory>")

    input_paths = [args.input] if args.input else sorted(
        glob.glob(os.path.join(args.input_dir, '**', '*.parquet'), recursive=True))
    print(f"{len(input_paths)} file(s) found.\n")

    for input_path in input_paths:
        fname = os.path.basename(input_path)

        existing = pd.read_parquet(input_path)
        if already_enriched(existing) and not args.overwrite:
            print(f"  [skip] {fname} already enriched (use --overwrite to re-enrich)")
            continue

        if args.in_place:
            csv_path = input_path.replace('.parquet', '.csv')
            parquet_path = input_path
        else:
            is_playoff = bool(existing['playoffs'].iloc[0]) if len(existing) and 'playoffs' in existing.columns else False
            season_type_dir = "playoffs" if is_playoff else "regular_season"
            out_dir = os.path.join(args.out, season_type_dir)
            os.makedirs(out_dir, exist_ok=True)
            csv_path = os.path.join(out_dir, fname.replace('.parquet', '.csv'))
            parquet_path = os.path.join(out_dir, fname)
            if os.path.exists(parquet_path) and not args.overwrite:
                print(f"  [skip] {parquet_path} already exists (use --overwrite to regenerate)")
                continue

        enriched = enrich_cdn_file(input_path)
        report_quality(enriched, fname)

        enriched.to_csv(csv_path, index=False)
        enriched.to_parquet(parquet_path, index=False)
        print(f"  Wrote {parquet_path} ({len(enriched):,} rows, "
              f"{enriched['game_id'].nunique()} games)\n")


if __name__ == "__main__":
    main()