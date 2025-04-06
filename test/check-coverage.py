#!/usr/bin/env python3
"""
Tool used to identify ROMs and map files without a corresponding .nv file
in the test directory.

Displays uncovered ROMs on maps with no/partial coverage.

If there are maps without any coverage, the script sets a non-zero exit code.
"""
import glob
import json
import os
import sys

# Hack to allow importing nvram_parser from the parent directory.
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import nvram_parser

# glob representing our test files
NV_GLOB = os.path.join(os.path.dirname(__file__), 'nvram', '*.nv')

# list of JSON files covered by at least one ROM
map_coverage = []

# first load the index and build dictionary of map files
with open(os.path.join(nvram_parser.MAPS_ROOT, 'index.json')) as f:
    index = json.load(f)

# go through our test files, and track coverage
for nvfile in glob.glob(NV_GLOB):
    basename = os.path.basename(nvfile)
    rom = nvram_parser.rom_for_nvpath(nvfile)

    if rom not in index:
        # we've already processed this ROM
        continue

    # track that we have coverage from at least one ROM for a given map
    map_coverage.append(index[rom])

    # remove this ROM from the index
    del index[rom]

# key is filename, value is list of ROMs we don't have coverage for
map_files = {}

# look at what's left
for rom, file in index.items():
    if rom.startswith('_'):
        # skip over _note entry
        continue

    # we don't have coverage for <rom>, but maybe we have coverage for <file>
    rom_list = map_files.get(file)
    if rom_list:
        rom_list.append(rom)
    else:
        map_files[file] = [rom]

no_coverage = []

# and finally print a list of map files with no/partial coverage
if map_files:
    print("Warning: partial map coverage; missing .nv files for:")
    for file, roms in map_files.items():
        if file not in map_coverage:
            no_coverage.append(file)
        else:
            print("%s: %s" % (file, ', '.join(roms)))
    if no_coverage:
        print("\nError: no map coverage; missing .nv files for:")
        for file in map_files:
            print("%s: %s" % (file, ', '.join(map_files.get(file))))

        # partial coverage is just a warning, no coverage is failure
        exit(1)
