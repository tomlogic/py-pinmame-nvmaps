#!/usr/bin/env python3

import json
import sys

for file in sys.argv[1:]:
    with open(file, 'r') as f:
        map_data = json.load(f)
    map_data['_version'] += 0.1
    with open(file, 'w') as f:
        f.write(json.dumps(map_data, indent=2))
        f.write('\n')
