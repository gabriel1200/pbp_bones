#!/bin/bash
set -euo pipefail

# ==============================
# CONFIG — Set years to copy here
# ==============================
# Brace expansion automatically generates all years from 1997 to 2026
YEARS=({2015..2016}) 

SRC_BASE=~/basketball/playbyplay/organized_data
DEST_BASE=../web_app/data/pbp

#python async_scrape.py
#python organize_data.py

echo "==> Starting parquet copy process..."

for YEAR in "${YEARS[@]}"; do
    echo ""
    echo "==> Processing year: $YEAR"

    # Regular Season
    echo "Copying regular_season parquet files for $YEAR..."
    find "$SRC_BASE/regular_season" -type f -name "*${YEAR}*.parquet" | while read -r file; do
        filename=$(basename "$file")
        echo "  Copying $filename"
        cp "$file" "$DEST_BASE/regular_season/"
    done

    # Playoffs
    echo "Copying playoffs parquet files for $YEAR..."
    find "$SRC_BASE/playoffs" -type f -name "*${YEAR}*.parquet" | while read -r file; do
        filename=$(basename "$file")
        echo "  Copying $filename"
        cp "$file" "$DEST_BASE/playoffs/"
    done
done

echo ""
echo "==> Copy complete!"

# ==============================
# Verification
# ==============================
for YEAR in "${YEARS[@]}"; do
    echo ""
    echo "Verification for $YEAR:"
    echo -n "  Files in regular_season: "
    find "$DEST_BASE/regular_season" -type f -name "*${YEAR}*.parquet" | wc -l
    echo -n "  Files in playoffs: "
    find "$DEST_BASE/playoffs" -type f -name "*${YEAR}*.parquet" | wc -l
done

echo ""
echo "If everything looks good, you can change 'cp' to 'mv' to move files instead of copying."