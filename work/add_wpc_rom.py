#!/usr/bin/env python3

"""
Tool to automate adding maps for WPC games.

- Use with add_test.sh and test_new.sh when bringing in new ROMs.
- Add CSV file to mode_champ with entries for Mode Champions and related
  checksum16 entries.
- Note that Replay score location may be off by a byte or two.

2025-07-08: updated for fileformat 0.7 (_metadata and platform properties)
"""

import argparse
import copy
import csv
import json
import os


MY_DIR = os.path.dirname(__file__)
NVRAM_DIR = '../../../pinmame/release/nvram'
HS_LONG = ['First Place', 'Second Place', 'Third Place', 'Fourth Place']
HS_SHORT = ['1st', '2nd', '3rd', '4th']

SCORE_TEMPLATE = {
  "label": "Grand Champion",
  "short_label": "GC",
  "initials": {
    "start": 7303,
    "encoding": "ch",
    "length": 3
  },
  "score": {
    "start": 7306,
    "encoding": "bcd",
    "length": 6
  }
}


def score(label, start, score_length, *,
          short_label=None, suffix=None):
    entry = copy.deepcopy(SCORE_TEMPLATE)
    entry['label'] = label
    if short_label:
        entry['short_label'] = short_label
    else:
        del entry['short_label']
    entry['initials']['start'] = start
    if score_length:
        entry['score']['start'] = start + 3
        entry['score']['length'] = score_length
        if suffix:
            entry['score']['suffix'] = ' ' + suffix
    else:
        del entry['score']
    return entry


def load_nv(rom):
    with open(os.path.join(NVRAM_DIR, rom + '.nv'), 'rb') as f:
        data = bytearray(f.read())
    print("loaded %u bytes from %s.nv" % (len(data), rom))
    gamestr = 'WPC %s, SYS %u.%02u REV %u.%u' % (
        data[6156:6161].decode(), data[6153], data[6154],
        data[6155] >> 4, data[6155] & 0xF
    )
    print(gamestr)
    with open(os.path.join(MY_DIR, 'template-wpc.json')) as f:
        map_data = json.load(f)
    if (len(data) & 0xFF00) == 8192:
        map_data['_metadata']['platform'] = "williams-wpc-8K"
    else:
        map_data['_metadata']['platform'] = "williams-wpc-12K"
    map_data['_metadata']['roms'].append(rom)
    map_data['_notes'][1] = gamestr
    initials = hs(data)
    audits_end = find_audits_end(data)
    adj_start, adj_end = find_adjustments(data, audits_end)

    score_length = initials[1] - initials[0] - 3
    map_data['high_scores'].append(score('Grand Champion',
                                         initials[4],
                                         score_length,
                                         short_label='GC'))
    print(' gc: initials at %u, %u-length score at %u' %
          (initials[4], score_length, initials[4] + 3))
    for i in range(0, 4):
        map_data['high_scores'].append(score(HS_LONG[i],
                                             initials[i],
                                             score_length,
                                             short_label=HS_SHORT[i]))
        print('hs%u: initials at %u, %u-length score at %u' %
              (i + 1, initials[i], score_length, initials[i] + 3))

    map_data['checksum16'].append({'start': adj_end + 3,
                                   'end': initials[0] - 1,
                                   'label': 'Timestamps'})
    map_data['checksum16'].append({'start': initials[0],
                                   'end': initials[4] - 1,
                                   'label': 'High Scores'})
    gc_end = initials[4] + score_length + 3 + 1
    map_data['checksum16'].append({'start': initials[4],
                                   'end': gc_end,
                                   'label': 'Grand Champion'})

    # there are 7 checksum16 areas after the grand champion spot
    c16_names = ["HSTD Reset", "Credits", "Volume", None, None,
                 "Custom Message (3x32)", "Custom Message (2x32)"]
    end = gc_end
    for i in range(0, 7):
        offset = end + 1
        end = find_checksum16_end(data, offset, 8192)
        record = {'start': offset, 'end': end}
        name = c16_names[i]
        if name:
            record['label'] = name
        else:
            name = 'unnamed'
        print("checksum16 from %u to %u (%s)" % (offset, end, name))
        map_data['checksum16'].append(record)
        if i == 1:
            map_data['game_state']['credits'] = {
                "_notes": "1-byte credits followed by 6 bytes encoding partial/bonus credits",
                'label': 'Credits', 'start': offset, 'encoding': 'int'}
        elif i == 2:
            map_data['game_state']['volume'] = {'label': 'Volume',
                                                'start': offset,
                                                'encoding': 'int',
                                                'min': 0, 'max': 31}
        elif i == 4:
            # Replay is in the start of the 5th checksum16 range.
            # I haven't been able to reliably calculate the offset...
            # 6-digit games: jb_10r=+10;
            # 5-digit: gi_l9=+9; T2=+10; TAFG=+10
            replay_offset = offset + 10
            map_data['game_state']['replay'] = {'label': 'Replay',
                                                'start': replay_offset,
                                                'encoding': 'bcd',
                                                'length': 2,
                                                'scale': 1000000
                                                }

    # Try to add Mode Champions via CSV file
    try:
        with open('mode_champ/' + rom + '.csv', 'r') as f:
            for row in csv.DictReader(f, delimiter=','):
                start = int(row['start'])
                score_length = int(row['score_length'])
                if row['suffix'] == 'c16':
                    # this is a checksum entry
                    map_data['checksum16'].append({'start': start,
                                                   'end': score_length,
                                                   'label': row['label']})
                else:
                    suffix = row.get('suffix')
                    entry = score(row['label'], start, score_length,
                                  suffix=suffix)
                    map_data['mode_champions'].append(entry)

    except FileNotFoundError:
        del map_data['mode_champions']
        print("Couldn't open %s.csv with mode champions" % rom)

    map_data['checksum8'][0]['end'] = audits_end

    print("adjustments from %u to %u" % (adj_start, adj_end))
    map_data['checksum16'][0]['start'] = adj_start
    map_data['checksum16'][0]['end'] = adj_end

    with open(os.path.join(MY_DIR, rom + '.nv.json'), 'w') as output:
        output.write(json.dumps(map_data, indent=2))
        output.write('\n')      # end with newline


def is_initial(ba):
    for b in ba:
        if b != ord(' ') and (b < ord('A') or b > ord('Z')):
            return False
    return True


def hs(data):
    initials = []
    # TODO: base range on size of RAM.  Early games with smaller RAM
    # have less space to search.
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


def main():
    parser = argparse.ArgumentParser(description='Map Generator')
    parser.add_argument('--rom', help='ROM name (e.g., bop_l7, dm_lx4)')
    args = parser.parse_args()
    load_nv(args.rom)


if __name__ == '__main__':
    main()
