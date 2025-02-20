#!/usr/bin/env python3

"""
Update Williams System 11 maps with additional information.
"""

import glob
import json
from collections import OrderedDict

MAP_DIR = '../maps/maps/williams/system11/'
NV_DIR = '../../pinmame/release/nvram/'
PINMAME = '../../pinmame/release/'

CURRENT_ROM = None


def find_audits(data):
    offset = 1582       # Rollergames has the earliest starting point
    start = None
    # start looking for first audit, 00 00 00 FF
    while True:
        checksum = 0
        for b in data[offset:offset + 4]:
            checksum += b
        if start:
            if (checksum & 0xFF) == 0xFF:
                offset += 4
            else:
                if offset - start < 15:
                    # false positive, start over
                    start = None
                else:
                    print("audits from %u to %u" % (start, offset - 1))
                    return start, offset - 1
        else:
            # make sure audit starts with 00 00 00 FF
            if data[offset:offset + 4] == b'\x00\x00\x00\xFF':
                start = offset
                offset += 4
            else:
                offset += 1


def update_checksums(map_data, data):
    if 'checksum8' not in map_data:
        map_data['checksum8'] = []
    audits_start, audits_end = find_audits(data)

    # replace first checksum8 record with single Audits
    map_data['checksum8'][0] = {
        "start": audits_start,
        "end": audits_end,
        "groupings": 4,
        "label": "Audits"
    }


def update(map_data, data):
    """Update map with contents of data loaded from a .nv file."""

    global CURRENT_ROM

    # move _game into _notes
    if '_game' in map_data:
        # if _notes is string, convert it to a list
        if isinstance(map_data['_notes'], str):
            map_data['_notes'] = [map_data['_notes']]
        map_data['_notes'].append(map_data['_game'])
        del map_data['_game']

    # add/correct _ramsize
    map_data['_ramsize'] = len(data) & 0xFF00
    if 'game_state' not in map_data:
        map_data['game_state'] = {}

    # move last_game into game_state
    if 'last_game' in map_data:
        del map_data['last_game']
        map_data['game_state']['scores'] = [
          {
            "label": "Player 1",
            "start": 512,
            "encoding": "bcd",
            "length": 4
          },
          {
            "label": "Player 2",
            "start": 516,
            "encoding": "bcd",
            "length": 4
          },
          {
            "label": "Player 3",
            "start": 520,
            "encoding": "bcd",
            "length": 4
          },
          {
            "label": "Player 4",
            "start": 524,
            "encoding": "bcd",
            "length": 4
          }
        ]

    if CURRENT_ROM != 'pool_l7' and ('credits' not in map_data['game_state']
                                     or map_data['game_state']['credits']['start'] < 1000):
        if len(map_data['high_scores']) == 5:
            # this game has a grand champion
            hs_index = 1
        else:
            hs_index = 0
        hs_start = map_data['high_scores'][hs_index]['score']['start']
        map_data['game_state']['credits'] = {
          "label": "Credits",
          "start": hs_start - 1,
          "length": 1,
          "encoding": "bcd"
        }

    # start game_state with credits
    map_data['game_state'].move_to_end('credits', last=False)

    # _ramsize and/or game_state added to end; re-order to the front of the list
    for entry in ['game_state', '_char_map', 'last_played', '_version', '_fileformat', '_roms',
                  '_ramsize', '_endian', '_license', '_copyright', '_notes']:
        if entry in map_data:
            map_data.move_to_end(entry, last=False)

    # make sure all checksum16 entries are present
    update_checksums(map_data, data)

    # re-order checksums to the end of the list
    for entry in ['checksum8']:
        if entry in map_data:
            map_data.move_to_end(entry)


for map_filename in glob.glob(MAP_DIR + '*.nv.json'):
    if 'gmine_l2' in map_filename:
        continue  # non-standard System 11 game (e.g., no checksum8 audits)

    with open(map_filename, 'r') as f:
        print("--- processing %s" % map_filename)
        nv_map = json.load(f, object_pairs_hook=OrderedDict)

    nv_data = None
    # first find an NV file to use as reference
    for rom_name in nv_map['_roms']:
        try:
            with open(NV_DIR + rom_name + '.nv', 'rb') as f:
                CURRENT_ROM = rom_name
                nv_data = bytearray(f.read())
                break
        except FileNotFoundError:
            pass

    if not nv_data:
        print("Error: missing .nv file for (%s)" % ', '.join(nv_map['_roms']))
    else:
        update(nv_map, nv_data)
        with open(map_filename, 'w') as f:
            f.write(json.dumps(nv_map, indent=2))
            f.write('\n')
