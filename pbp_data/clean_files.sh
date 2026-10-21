#!/bin/bash

# -- Configuration --
TARGET_DIR="./"
START_YEAR=1997
END_YEAR=2020

# -- Execution --
echo "Starting cleanup in $TARGET_DIR..."

for (( year=START_YEAR; year<=END_YEAR; year++ ))
do
    echo "Processing year: $year"
    
    # This targets files containing the year surrounded by underscores, 
    # e.g., "report_2014_final.pdf"
    # To include other variations, you can add more patterns.
    rm -f "$TARGET_DIR"/*"$year"_*
done

echo "Cleanup complete."