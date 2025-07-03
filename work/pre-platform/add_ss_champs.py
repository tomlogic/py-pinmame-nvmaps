#!/usr/bin/env python3

"""
Quick tool to add the 10 "Favorite Stiff" initial entries to
the Scared Stiff 1.5 map.

Written 2025-01-06 by Tom Collins <tom@tomlogic.com>
"""

import json

MAP_FILE = 'new_maps/ss_15.nv.json'
with open(MAP_FILE) as f:
    map = json.load(f)

map['mode_champions'].append({
    "label": "Favorite Stiff Count",
    "score": {
        "start": 8150,
        "encoding": "int",
        "suffix": " Stiffs"
    }
})

for i in range(0, 10):
    map['mode_champions'].append({
        "label": "Favorite Stiff #%u" % (i + 1),
        "initials": {
            "start": 8119 + 3 * i,
            "encoding": "ch",
            "default": "\u00FF\u00FF\u00FF",
            "length": 3
        }
    })

print(json.dumps(map, indent=2))
