#!/bin/bash

# Absolute path to this script.
SCRIPT=$(readlink -f "$0")
# Absolute path this script is in.
SCRIPT_PATH=$(dirname "$SCRIPT")

# set exit code if there's an error
# https://stackoverflow.com/a/73000327/266392
trap 'RC=1' ERR

(
  cd "$SCRIPT_PATH"  || exit 1
  mkdir -p results
  rm results/*.txt
  for file in nvram/*.nv; do
    filename=$(basename "$file")
    python3 ../nvram_parser.py --nvram "$file" --dump > "results/$filename.txt" 2>&1
  done
  diff --unified --recursive --ignore-matching-lines '^Using map ' expected results | more

  python3 missing-test.py
)

exit $RC
