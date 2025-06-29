#!/usr/bin/env python3

import glob
import json
import os

MAP_DIR = '../maps/maps/williams/wpc/'

print('rom_name,sys,audits,adjustments,timestamps')

def item_count(entry, grouping):
    # end-start includes first byte of checksum16
    return (entry['end'] - entry['start'] - 1) // grouping


for map_filename in glob.glob(MAP_DIR + '*.nv.json'):
    basename = os.path.basename(map_filename)
    if 'dm_dt101.nv.json' in map_filename:
        continue  # not a Williams WPC game

    with open(map_filename, 'r') as f:
        nv_map = json.load(f)

    sys = '?.??'
    for note in nv_map['_notes']:
        if 'SYS' in note:
            sys = note.split()[3]

    audits = nv_map['checksum8'][0]
    counts = [item_count(audits, 6)]

    for entry in nv_map['checksum16']:
        label = entry.get('label')

        if label == 'Adjustments':
            counts.append(item_count(entry, 2))
        elif label == 'Timestamps':
            counts.append(item_count(entry, 7))

    print('%s,%s,%s' % (basename, sys, ','.join(map(str, counts))))
