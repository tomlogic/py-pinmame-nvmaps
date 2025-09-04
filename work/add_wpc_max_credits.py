#!/usr/bin/env python3

"""
Add "Max Credits" to all WPC games.
"""

import glob
import json
from collections import OrderedDict

MAP_DIR = '../maps/maps/williams/wpc/'
NV_DIR = '../../../pinmame/release/nvram/'
PINMAME = '../../../pinmame/release/'

CURRENT_ROM = None


def update(map_data, data):
    """Update map with contents of data loaded from a .nv file."""

    # if game_state.max_credits doesn't exist, try to find it
    # $0.25/$1.00/$0.25/$1.00
    pricing = data.find(b'\x00\x19\x00\x64\x00\x19\x00\x64\x00')
    if pricing < 0:
        # $0.25/$0.25/$0.25/$0.25
        pricing = data.find(b'\x00\x19\x00\x19\x00\x19\x00\x19\x00')
    if pricing < 0:
        # $0.25/$1.00/$0.25/$0.00
        pricing = data.find(b'\x00\x19\x00\x64\x00\x19\x00\x00\x00')

    if pricing > 0:
        max_credits = pricing + 9
        print('found pricing -- max.credits = %u' % data[max_credits])
        nv_map['game_state']['max_credits'] = {
            'label': 'Maximum Credits',
            'start': max_credits,
            'encoding': 'int',
        }


for map_filename in glob.glob(MAP_DIR + '*.nv.json'):
    if 'dm_dt101.nv.json' in map_filename:
        continue  # not a Williams WPC game

    with open(map_filename, 'r') as f:
        print("--- processing %s" % map_filename)
        nv_map = json.load(f, object_pairs_hook=OrderedDict)

    nv_data = None
    # first find an NV file to use as reference
    for rom_name in nv_map['_metadata']['roms']:
        try:
            with open(NV_DIR + rom_name + '.nv', 'rb') as f:
                CURRENT_ROM = rom_name
                nv_data = bytearray(f.read())
                break
        except FileNotFoundError:
            pass

    if not nv_data:
        print("Error: missing .nv file for (%s)" % ', '.join(nv_map['_metadata']['roms']))
    else:
        update(nv_map, nv_data)
        with open(map_filename, 'w') as f:
            f.write(json.dumps(nv_map, indent=2))
            f.write('\n')
