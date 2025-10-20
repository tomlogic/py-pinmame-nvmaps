#!/usr/bin/env python3

"""
Add ball_count and max_credits to System 11 games
"""

import json
import glob

MAP_DIR = '../maps/maps/williams/system11/'

for map_filename in glob.glob(MAP_DIR + '*.map.json'):
    if 'gmine_l2' in map_filename:
        continue  # non-standard System 11 game (e.g., no checksum8 audits)

    with open(map_filename, 'r') as f:
        map_json = json.load(f)
    map_json['game_state']['ball_count'] = {
        "label": "Ball Count",
        "start": 1928,
        "encoding": "bcd"
    }
    map_json['game_state']['max_credits'] = {
        "label": "Maximum Credits",
        "start": 1931,
        "encoding": "bcd"
    }

    with open(map_filename, 'w') as f:
        f.write(json.dumps(map_json, indent=2))
        f.write('\n')
