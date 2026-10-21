#!/bin/bash
[ -n "$NBA_SEASON_YEAR" ] || source ~/basketball/season.sh  # season config when run standalone
python async_scrape.py 
python organize_data.py
set -euo pipefail

# Create the destination directory structure


echo "==> Copying parquet files from regular_season (only files with '${NBA_SEASON_YEAR}' in the name)..."
find ~/basketball/playbyplay/organized_data/regular_season -type f -name "*${NBA_SEASON_YEAR}*.parquet" | while read -r file; do
    filename=$(basename "$file")
    echo "Copying $filename"
    cp "$file" ../web_app/data/pbp/regular_season/
done

echo "==> Copying parquet files from playoffs (only files with '${NBA_SEASON_YEAR}' in the name)..."
find ~/basketball/playbyplay/organized_data/playoffs -type f -name "*${NBA_SEASON_YEAR}*.parquet" | while read -r file; do
    filename=$(basename "$file")
    echo "Copying $filename"
    cp "$file" ../web_app/data/pbp/playoffs/
done

echo "==> All ${NBA_SEASON_YEAR} parquet files copied successfully!"

# Verify the copy worked
echo ""
echo "==> Verifying files copied:"
echo -n "Files in regular_season: "
find ../web_app/data/pbp/regular_season -type f -name "*${NBA_SEASON_YEAR}*.parquet" | wc -l
echo -n "Files in playoffs: "
find ../web_app/data/pbp/playoffs -type f -name "*${NBA_SEASON_YEAR}*.parquet" | wc -l

echo ""
echo "If everything looks good, you can change 'cp' to 'mv' in the script to move the files instead of copying."
