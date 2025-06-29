#!/usr/bin/env python3

"""
Tool to automate adding maps for Williams System 11 games.

- Use with add_test.sh and test_new.sh when bringing in new ROMs.
"""

import argparse
import copy
import json
import os
from collections import OrderedDict


MY_DIR = os.path.dirname(__file__)
NVRAM_DIR = '../../pinmame/release/nvram'
HS_LONG = ['First Place', 'Second Place', 'Third Place', 'Fourth Place']
HS_SHORT = ['1st', '2nd', '3rd', '4th']

SCORE_TEMPLATE = {
  "label": "Grand Champion",
  "short_label": "GC",
  "initials": {
    "start": 1822,
    "encoding": "ch",
    "length": 3,
    "mask": 127
  },
  "score": {
    "start": 1806,
    "encoding": "bcd",
    "length": 4
  }
}


def score(label, initials_start, score_start, *,
          short_label=None, mask=False):
    entry = copy.deepcopy(SCORE_TEMPLATE)
    entry['label'] = label
    if short_label:
        entry['short_label'] = short_label
    else:
        del entry['short_label']
    if not mask:
        del entry['initials']['mask']
    entry['initials']['start'] = initials_start
    entry['score']['start'] = score_start
    return entry


def load_nv(rom):
    with open(os.path.join(NVRAM_DIR, rom + '.nv'), 'rb') as f:
        data = bytearray(f.read())
    print("loaded %u bytes from %s.nv" % (len(data), rom))
    with open(os.path.join(MY_DIR, 'template-s11.json')) as f:
        map_data = json.load(f, object_pairs_hook=OrderedDict)
    map_data['_ramsize'] = len(data) & 0xFF00
    map_data['_roms'].append(rom)
    (audits_start, audits_end) = find_audits(data)

    # initials = hs(data)
    # adj_start, adj_end = find_adjustments(data, audits_end)

    # check whether this ROM needs the _char_map
    mask = False
    if data[audits_end + 21] >= ord('A'):
        del map_data['_char_map']
        score_start = audits_end + 4
        mask = data[audits_end + 21] > 0x80
    else:
        score_start = audits_end + 5

    if rom == 'pool_l7':
        # special case -- two sets of high scores
        score_start = 1443
        initials_start = 1475
        for i in range(0, 4):
            map_data['high_scores'].append(score('8-Ball Shark #%u' % (i + 1),
                                                 initials_start + 3 * i,
                                                 score_start + 4 * i,
                                                 mask=mask))
        score_start = 1459
        initials_start = 1487
        for i in range(0, 4):
            map_data['high_scores'].append(score('9-Ball Shark #%u' % (i + 1),
                                                 initials_start + 3 * i,
                                                 score_start + 4 * i,
                                                 mask=mask))
        # had to manually find credits at 1805 with checksum at 1914
    else:
        for i in range(0, 4):
            map_data['high_scores'].append(score(HS_LONG[i],
                                                 score_start + 16 + 3 * i,
                                                 score_start + 4 * i,
                                                 short_label=HS_SHORT[i],
                                                 mask=mask))
        map_data['game_state']['credits'] = {
            "label": "Credits",
            "start": score_start - 1,
            "length": 1,
            "encoding": "bcd"
        }
        # start game_state with credits
        map_data['game_state'].move_to_end('credits', last=False)

    map_data['checksum8'][0]['start'] = audits_start
    map_data['checksum8'][0]['end'] = audits_end

    with open(os.path.join(MY_DIR, rom + '.nv.json'), 'w') as output:
        output.write(json.dumps(map_data, indent=2))
        output.write('\n')      # end with newline


def find_audits(data):
    offset = 1600
    start = None
    # start looking for first audit, 00 00 00 FF
    while True:
        checksum = 0
        for b in data[offset:offset + 4]:
            checksum += b
        if start:
            if (checksum & 0xFF) != 0xFF:
                print("audits from %u to %u" % (start, offset - 1))
                return start, offset - 1
        else:
            # make sure audit starts with 00 00 00 FF
            if data[offset:offset + 4] == b'\x00\x00\x00\xFF':
                start = offset
        offset += 1


def main():
    parser = argparse.ArgumentParser(description='Map Generator')
    parser.add_argument('--rom', help='ROM name (e.g., hs_l4)')
    args = parser.parse_args()
    load_nv(args.rom)


if __name__ == '__main__':
    main()
