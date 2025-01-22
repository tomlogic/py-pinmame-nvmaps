#!/usr/bin/env python3

import json
import sys

MAP_DIR = '../maps/maps/williams/wpc/'
KEYS = ['current_player', 'current_ball', 'extra_balls', 'eb_on_this_ball']
LABELS = ['Current Player', 'Ball', 'Extra Balls', 'EBs this Ball']

if len(sys.argv) != 4:
    print("usage: %s <rom> <current_player_address> <attract_address>")
    raise SystemExit(1)

rom = sys.argv[1]
address = int(sys.argv[2], 0)
attract = int(sys.argv[3], 0)
print("current_player to %u for %s" % (address, rom))

map_filename = MAP_DIR + rom + '.nv.json'
with open(map_filename, 'r') as f:
    map_data = json.load(f)

game_state = map_data['game_state']
if 'playing' in game_state:
    del game_state['playing']
game_state['attract'] = {
    'label': "Attract",
    'start': attract,
    'encoding': 'enum',
    'values': ['IN GAME', 'ATTRACT']
}

for i in range(0, len(LABELS)):
    game_state[KEYS[i]] = {
        'label': LABELS[i],
        'start': address + i,
        'encoding': 'int'
    }

with open(map_filename, 'w') as f:
    f.write(json.dumps(map_data, indent=2))
    f.write('\n')
