#!/usr/bin/env python3
import glob
import json
import os

NV_GLOB = os.path.join(os.path.dirname(__file__), 'nvram', '*.nv')
MAPS_DIR = os.path.join(os.path.dirname(__file__), '..', 'maps')

# key is filename, value is list of ROMs it works for
map_files = {}

# first load the index and build dictionary of map files
with open(os.path.join(MAPS_DIR, 'index.json')) as f:
    index = json.load(f)
for rom, file in index.items():
    if rom.startswith('_'):
        # skip over _note entry
        continue
    rom_list = map_files.get(file)
    if rom_list:
        rom_list.append(rom)
    else:
        map_files[file] = [rom]

# now go through our test files, and delete map_files entries with coverage
for nvfile in glob.glob(NV_GLOB):
    basename = os.path.basename(nvfile)
    (name, extension) = os.path.splitext(basename)
    # remove anything after the first hyphen
    (rom, _, _) = name.partition('-')

    # look up map file for this ROM
    map_file = index.get(rom)
    if map_file:
        # we have an nv file for this map, so remove it from the map_files list
        if map_files.get(map_file):
            del map_files[map_file]
    else:
        print("Missing map for %s?" % rom)

# and finally print a list of map files without coverage
if map_files:
    print("Missing coverage for:")
    for file, roms in map_files.items():
        print("%s: %s" % (file, ', '.join(roms)))
    raise SystemExit(1)
