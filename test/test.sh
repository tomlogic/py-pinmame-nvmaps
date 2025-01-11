#!/bin/sh

# Absolute path to this script, e.g. /home/user/bin/foo.sh
SCRIPT=$(readlink -f "$0")
# Absolute path this script is in, thus /home/user/bin
SCRIPTPATH=$(dirname "$SCRIPT")

(
  cd "$SCRIPTPATH"
  mkdir -p results
  rm results/*.txt
  for file in nvram/*.nv; do
    filename=$(basename "$file")
    python3 ../nvram_parser.py --nvram "$file" --dump > "results/$filename.txt" 2>&1
  done
  diff --unified --recursive --ignore-matching-lines '^Using map ' expected results | more

  python3 missing-test.py
)
