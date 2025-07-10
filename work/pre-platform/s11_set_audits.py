#!/usr/bin/env python3

# Use the System 11 map files to set values for each audit in existing PinMAME .nv files

import json

sys11_maps = '../maps/maps/williams/system11/'
nv_files = '../../pinmame/release/nvram/'
map_dir = '../maps/'


with open(map_dir + 'index.json', 'r') as f:
    maps = json.load(f)

for rom, file in maps.items():
    if 'system11' in file:
        print("patch NV %s" % rom)
        with open(map_dir + file) as f:
            nv_map = json.load(f)
        nv_file = nv_files + rom + '.nv'
        with open(nv_file, 'rb') as f:
            nvdata = bytearray(f.read())

        audits = nv_map.get('audits', {'Audits': {}})
        for index, audit in audits['Audits'].items():
            value = int(index, 10)
            bcd = (value // 10) * 16 + (value % 10)
            audit_value = [0, 0, bcd, 0xFF - bcd]
            start = audit['start']
            nvdata[start:start + 4] = bytearray(audit_value)

        with open(nv_file, 'wb') as f:
            f.write(nvdata)
