#!/usr/bin/env python3

"""
Update Williams WPC maps with additional information.
"""

import glob
import json
from collections import OrderedDict

MAP_DIR = './new_maps'
NV_DIR = '../../pinmame/release/nvram/'
PINMAME = '../../pinmame/release/'

CURRENT_ROM = None


def find_checksum16_end(data, offset, max_offset):
    calc_checksum = data[offset]
    while offset < max_offset:
        offset += 1
        stored_checksum = data[offset] * 256 + data[offset + 1]
        if stored_checksum + calc_checksum == 0xFFFF:
            return offset + 1
        calc_checksum += data[offset]
    return None


def find_adjustments(data, audits_end):
    offset = audits_end + 1
    # skip over unused audits between audits and adjustments
    while data[offset:offset + 6] == b'\xFF\xFF\xFF\xFF\xFF\xFF':
        offset += 6
    start = offset
    end = find_checksum16_end(data, offset, 7500)
    return start, end


def is_initial(ba):
    for b in ba:
        if b != ord(' ') and (b < ord('A') or b > ord('Z')):
            return False
    return True


def hs(data):
    initials = []
    for i in range(7200, 7700):
        if is_initial(data[i:(i+3)]):
            if initials and i == initials[-1] + 1:
                print("(updating to %u)" % i)
                initials[-1] = i
            elif len(initials) == 5:
                break
            else:
                if initials and i - initials[-1] > 20:
                    print("removing false positive")
                    initials.pop()
                print("found initials starting at %u" % i)
                initials.append(i)
    if not initials:
        print("couldn't find initials")
    return initials


def find_audits_end(data):
    offset = 6161
    while True:
        checksum = 0
        for b in data[offset:offset + 6]:
            checksum += b
        if (checksum & 0xFF) != 0xFF:
            print("audits from 6061 to %u" % (offset - 1))
            return offset - 1
        offset += 6


def c16_add(d, start, end, label):
    if not d.get(start):
        # create new entry
        d[start] = {"start": start, "end": end}
    if label:
        d[start]['label'] = label


def update_checksums(map_data, data):
    global CURRENT_ROM

    audits_end = find_audits_end(data)
    adj_start, adj_end = find_adjustments(data, audits_end)
    initials = hs(data)
    score_length = initials[1] - initials[0] - 3
    gc_end = initials[4] + score_length + 3 + 1
    if CURRENT_ROM == 'hd_l3':
        # this game has 24 extra 0xFF bytes between GC's score and the checksum
        gc_end += 24

    # replace any existing checksum8 records with single Audits
    map_data['checksum8'] = [{
        "start": 6161,
        "end": audits_end,
        "groupings": 6,
        "label": "Audits"
    }]

    c16_dict = {}
    for entry in map_data.get('checksum16', []):
        c16_dict[entry['start']] = entry

    c16_add(c16_dict, adj_start, adj_end, 'Adjustments')
    ts_start = adj_end + 3
    if CURRENT_ROM in ['pz_l3', 'hd_l3', 'hd_l4']:
        # for some reason, Timestamps on these ROMs start one byte earlier
        ts_start -= 1
    c16_add(c16_dict, ts_start, initials[0] - 1, 'Timestamps')
    c16_add(c16_dict, initials[0], initials[4] - 1, 'High Scores')

    c16_add(c16_dict, initials[4], gc_end, 'Grand Champion')

    game_state = map_data['game_state']

    # there are 7 checksum16 areas after the grand champion spot
    c16_names = ["HSTD Reset", "Credits", "Volume", None, None,
                 "Custom Message (3x32)", "Custom Message (2x32)"]
    end = gc_end
    for i in range(0, 7):
        offset = end + 1
        if i == 6 and CURRENT_ROM in ['cv_20h', 'fs_lx5', 'tz_92', 'tz_94h']:
            # these games don't have the second Custom Message area
            continue
        if CURRENT_ROM in ['cv_20h', 'ww_lh6']:
            # these HOME/FREE PLAY ONLY ROMS are missing the credits section
            if i == 1:
                if CURRENT_ROM in ['cv_20h']:
                    end = offset + 9
                elif CURRENT_ROM in ['ww_lh6']:
                    end = offset + 8
                continue

        end = find_checksum16_end(data, offset, len(data) - 10)
        if not end:
            print("failed to find checksum end (index %u, start=%u)" % (i, offset))
        name = c16_names[i]
        c16_add(c16_dict, offset, end, name)

        if i == 1 and 'credits' not in game_state:
            game_state['credits'] = {
                "_note": "1-byte credits followed by 6 bytes encoding partial/bonus credits",
                'label': 'Credits', 'start': offset, 'encoding': 'int'}
        elif i == 2 and 'volume' not in game_state:
            game_state['volume'] = {'label': 'Volume',
                                    'start': offset,
                                    'encoding': 'int',
                                    'min': 0, 'max': 31}
        elif i == 4 and 'replay' not in game_state:
            # Replay is in the start of the 5th checksum16 range.
            # I haven't been able to reliably calculate the offset...
            # 6-digit games: jb_10r=+10;
            # 5-digit: gi_l9=+9; T2=+10; TAFG=+10
            replay_offset = offset + 10
            game_state['replay'] = {'label': 'Replay',
                                    'start': replay_offset,
                                    'encoding': 'bcd',
                                    'length': 2,
                                    'scale': 1000000
                                    }
            if CURRENT_ROM.startswith('nbaf_'):
                # no scale, replay of 100
                del game_state['replay']['scale']
            elif CURRENT_ROM.startswith('afm_'):
                # replay in the xx.xB range
                game_state['replay']['scale'] = 100000000
            elif CURRENT_ROM.startswith('sc_', 'totan_', 'fh_', 'hd_'):
                # these games have a replay in the xx.xM range
                game_state['replay']['scale'] = 10000

    if find_checksum16_end(data, 6012, 6200) == 6143:
        c16_add(c16_dict, 6012, 6143, "Custom Message (2x32)")

    new_c16 = []
    for key, entry in sorted(c16_dict.items()):
        new_c16.append(entry)

    map_data['checksum16'] = new_c16


def update(map_data, data):
    """Update map with contents of data loaded from a .nv file."""

    # if _notes is string, convert it to a list
    if isinstance(map_data['_notes'], str):
        map_data['_notes'] = [map_data['_notes']]

    # move _game into _notes
    if '_game' in map_data:
        map_data['_notes'].append(map_data['_game'])
        del map_data['_game']

    # If _notes doesn't have a SYS entry, add it
    has_sys = None
    for entry in map_data['_notes']:
        if ', SYS ' in entry:
            has_sys = entry
            break
    if not has_sys:
        gamestr = 'WPC %s, SYS %u.%02u REV %u.%u' % (
            data[6156:6161].decode(), data[6153], data[6154],
            data[6155] >> 4, data[6155] & 0xF
        )
        map_data['_notes'].append(gamestr)

    # add/correct _ramsize
    map_data['_ramsize'] = len(data) & 0xFF00
    if 'game_state' not in map_data:
        map_data['game_state'] = {}

    # _ramsize and/or game_state added to end; re-order to the front of the list
    for entry in ['game_state', 'last_game', 'last_played', '_version', '_fileformat', '_roms',
                  '_ramsize', '_endian', '_license', '_copyright', '_notes']:
        if entry in map_data:
            map_data.move_to_end(entry, last=False)

    # if replay.length == 3, increment start and adjust length to 2
    # (correct an error I made in originally mis-understanding differences in 5/6-byte scores)
    if 'replay' in map_data['game_state']:
        if map_data['game_state']['replay']['length'] == 3:
            map_data['game_state']['replay']['length'] = 2
            map_data['game_state']['replay']['start'] += 1

    # make sure all checksum16 entries are present
    update_checksums(map_data, data)

    # re-order checksums to the end of the list
    for entry in ['checksum8', 'checksum16']:
        if entry in map_data:
            map_data.move_to_end(entry)


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
