#!/bin/bash

echo "==> Copying parquet files from regular_season (excluding files with '2026' in the name)..."
find ~/basketball/playbyplay/organized_data/regular_season -type f -name "*.parquet" ! -name "*2026*" | while read -r file; do
    filename=$(basename "$file")
    echo "Copying $filename"
    cp "$file" ../web_app/data/pbp/regular_season/
done

echo "==> Copying parquet files from playoffs (excluding files with '2026' in the name)..."
find ~/basketball/playbyplay/organized_data/playoffs -type f -name "*.parquet" ! -name "*2026*" | while read -r file; do
    filename=$(basename "$file")
    echo "Copying $filename"
    cp "$file" ../web_app/data/pbp/playoffs/
done

echo "==> All non-2026 parquet files copied successfully!"

# Verify the copy worked
echo ""
echo "==> Verifying files copied:"
echo -n "Files in regular_season (non-2026): "
find ../web_app/data/pbp/regular_season -type f -name "*.parquet" ! -name "*2026*" | wc -l
echo -n "Files in playoffs (non-2026): "
find ../web_app/data/pbp/playoffs -type f -name "*.parquet" ! -name "*2026*" | wc -l

echo ""
echo "If everything looks good, you can change 'cp' to 'mv' in the script to move the files instead of copying."
