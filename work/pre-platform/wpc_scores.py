#!/usr/bin/env python3

"""
Update Williams WPC maps with additional information.
"""

import glob
import json
from collections import OrderedDict
import sys

MAP_DIR = '../maps/maps/williams/wpc/'
NV_DIR = '../../pinmame/release/nvram/'
PINMAME = '../../pinmame/release/'

CURRENT_ROM = None
SCORE_6BYTE = b'\x01\x23\x45\x67\x89\x10'
SCORE_5BYTE = b'\x12\x34\x56\x78\x90'


def add_scores(map_data, data, bc_offset, score_length):
    print("%s 00BC offset is %u" % (CURRENT_ROM, bc_offset))
    score_offset = bc_offset - 4 * (score_length + 1)
    scores = []
    for i in range(0, 4):
        scores.append({
            'label': 'Player %u' % (i + 1),
            'start': score_offset,
            'encoding': 'bcd',
            'length': score_length
        })
        if score_length == 5:
            data[score_offset:score_offset + 5] = SCORE_5BYTE
        else:
            data[score_offset:score_offset + 6] = SCORE_6BYTE
        score_offset += score_length + 1
    map_data['game_state']['scores'] = scores
    map_data['game_state'].move_to_end('scores', last=False)
    if 'player_count' in map_data['game_state']:
        map_data['game_state'].move_to_end('player_count', last=False)
    if 'last_game' in map_data:
        del map_data['last_game']

    # Write to a huge range of bytes trying to find the player_count.
    # Note that this technique failed for hurr_l2 and tz_94h and I had
    # to manually update those maps.
    for i in range(70, 100):
        data[bc_offset + i] = 4


def bc_offset(map_data, data):
    # look for 00BC byte sequence
    score_length = map_data['high_scores'][0]['score']['length']
    offset = 5760 + 4 * (score_length + 1)
    while offset < 6100:
        if data[offset] == 0x00 and data[offset + 1] == 0xBC:
            return offset, score_length
        offset += 16

    print("%s 00BC offset NOT FOUND" % CURRENT_ROM)
    return None, None


def update_with_scores(map_data, data):
    offset, score_length = bc_offset(map_data, data)
    if offset:
        add_scores(map_data, data, offset, score_length)


def update_count(map_data, data):
    offset, score_length = bc_offset(map_data, data)
    if offset:
        # look for player count
        skip = True
        for i in range(70, 100):
            if skip:
                if data[offset + i] != 4:
                    skip = False
            else:
                if data[offset + i] == 4 and data[offset + i - 1] == 0:
                    map_data['game_state']['player_count'] = {
                        'label': 'Players',
                        'start': offset + i,
                        'encoding': 'int'
                    }
                    map_data['game_state'].move_to_end('player_count', last=False)
                    break


def set_player_count(map_data, data, count):
    offset = map_data['game_state']['player_count']['start']
    data[offset] = count


update_score = False
verify = False
if sys.argv[1] == '--score':
    update_score = True
elif sys.argv[1] == '--verify':
    verify = True
elif sys.argv[1] != '--count':
    print('Pass either --score or --count to update that element.')
    exit(1)

run_all = open(PINMAME + 'run_all_wpc.bat', 'w', newline='\r\n')
test_all = open('test_all_wpc.sh', 'w')
test_all.write('#!/bin/sh\n\n')

for map_filename in glob.glob(MAP_DIR + '*.nv.json'):
    if 'dm_dt101.nv.json' in map_filename:
        continue  # not a Williams WPC game

    with open(map_filename, 'r') as f:
        print("--- processing %s" % map_filename)
        nv_map = json.load(f, object_pairs_hook=OrderedDict)

    nv_data = None
    # first find an NV file to use as reference
    for rom_name in nv_map['_roms']:
        try:
            with open(NV_DIR + rom_name + '.nv', 'rb') as f:
                CURRENT_ROM = rom_name
                run_all.write('call run %s\n' % rom_name)
                test_all.write('../nvram_parser.py --dump --nvram %s > tmp/%s.txt\n' %
                               (NV_DIR + rom_name + '.nv', rom_name))
                nv_data = bytearray(f.read())
                break
        except FileNotFoundError:
            pass

    if not nv_data:
        print("Error: missing .nv file for (%s)" % ', '.join(nv_map['_roms']))
    else:
        if update_score:
            update_with_scores(nv_map, nv_data)
        elif verify:
            # Set player count to 2 and see if it clips the scores in attract.
            # I thought the ROM might clear the score area of RAM, but it does not.
            set_player_count(nv_map, nv_data, 2)
        else:
            update_count(nv_map, nv_data)
        with open(NV_DIR + rom_name + '.nv', 'wb') as f:
            f.write(nv_data)
        with open(map_filename, 'w') as f:
            f.write(json.dumps(nv_map, indent=2))
            f.write('\n')

run_all.close()
test_all.close()
