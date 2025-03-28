#!/usr/bin/env python3

"""
Update Williams System 11 maps with audits.
"""

import glob
import json
import zipfile
from collections import OrderedDict

MAP_DIR = '../maps/maps/williams/system11/'
NV_DIR = '../../pinmame/release/nvram/'
ROM_DIR = '../../pinmame/release/roms/'
PINMAME = '../../pinmame/release/'

CURRENT_ROM = None


"""
  "audits": {
    "Audits": {
      "01": {
        "start": 1700,
        "encoding": "bcd",
        "length": 3,
        "label": "Left Coins"
      },
"""


def audit_dict(address, label):
    return {"start": address, "encoding": "bcd", "length": 3, "label": label}


def str_to_charmap(s):
    retval = b''
    for ch in s:
        if ch == ord(' '):
            retval += b'\x00'
        elif ord('0') <= ch <= ord('9'):
            retval += b'%c' % (1 + ch - ord('0'))
        elif ord('A') <= ch <= ord('Z'):
            retval += b'%c' % (11 + ch - ord('A'))
        else:
            raise ValueError("Can't convert '%s'" % s)
    return retval


def get_table_string(romdata, offset):
    # offset is address of big endian address to 8 characters
    str_addr = romdata[offset] * 256 + romdata[offset + 1]
    str_addr &= ~0x4000     # mask off address bit to get file offset
    return romdata[str_addr:str_addr + 8]


def get_rom_label(romdata, offset, is_split, is_table):
    if is_table:
        # offset is address of two string table entries
        return get_table_string(romdata, offset) + get_table_string(romdata, offset + 2)
    elif is_split:
        return romdata[offset:offset + 7] + b' ' + romdata[offset + 7: offset + 14]
    else:
        return romdata[offset: offset + 16]


def get_audits(file, romdata, audit_region):
    charmap = False
    split = False
    offset = romdata.find(b"  LEFT  COINS ")
    if offset > 0:
        # High Speed era -- split 7/7 display
        split = True
        offset_increment = 14
    else:
        # Jokerz! era -- 16-character display
        offset_increment = 16
        offset = romdata.find(b"   LEFT COINS   ")
        if offset < 0:
            offset = romdata.find(b"    LEFT COINS  ")
        if offset < 0:
            # this won't work, since these games also use the string table
            offset = romdata.find(str_to_charmap(b"   LEFT COINS   "))
            if offset < 0:
                offset = romdata.find(str_to_charmap(b"    LEFT COINS  "))
            if offset > 0:
                print("found charmap LEFT COINS!")
                charmap = True
                exit(100)
        if offset < 0:
            return None

    audits = {}
    print('for %s, left coins at %u' % (file, offset))
    audit_index = 1
    audit_address = audit_region['start']
    # some (all?) games actually start at the second "audit" position
    if True or CURRENT_ROM in ['hs_l4']:
        audit_address += 4
    while True:
        audit_name = ''
        label = get_rom_label(romdata, offset, split, False)

        for b in label:
            if b == 0x82:
                # special character for quoting, appears as backtick on alphanumeric display
                audit_name += "'"
            elif b & 0x80:  # bit 7 (0x80) indicates '.' after character
                audit_name += '%c.' % chr(b & 0x7F)
            elif b == ord('i'):
                audit_name += '$'  # maybe locale-specific currency?
            elif b == ord('o'):
                audit_name += '-'
            elif b == ord('p'):
                audit_name += '/'  # "per"
            elif b in [ord('x'), ord('z')]:
                audit_name += '"'  # double quote
            elif b == ord('\\'):
                # backslash used for a "pipe" style character or "1" digit centered
                audit_name += '1'
            else:
                if ord('a') <= b <= ord('z'):
                    print("*********** unhandled lowercase letter %c" % chr(b))
                audit_name += chr(b)
        audit_name = audit_name.strip()
        while '  ' in audit_name:
            # convert duplicated spaces to a single space
            audit_name = audit_name.replace('  ', ' ')
        if audit_name.startswith('PERCENT') or audit_name == 'AV. BALL TIME':
            print("AUDIT %02u: %s calculated dynamically" % (audit_index, audit_name))
        elif audit_name in ['H.S.RESET COUNTER', 'H.S. RESET COUNTER']:
            # special location -- immediately after initials
            hstd_reset = nv_map['high_scores'][-1]['initials']['start'] + 3
            print("AUDIT %02u: %s at %u **" % (audit_index, audit_name, hstd_reset))
            audits['%02u' % audit_index] = audit_dict(hstd_reset, audit_name)
        else:
            if audit_address >= audit_region['end']:
                break
            print("AUDIT %02u: %s at %u" % (audit_index, audit_name, audit_address))
            audits['%02u' % audit_index] = audit_dict(audit_address, audit_name)
            audit_address += 4
        audit_index += 1
        offset += offset_increment

    return audits


def try_audits_update(nv_map):
    global CURRENT_ROM

    for rom_name in nv_map['_roms']:
        if rom_name.startswith('hs_') or rom_name.startswith('tsptr_'):
            print('"audits" section already present')
            return
        try:
            with zipfile.ZipFile(ROM_DIR + rom_name + '.zip', 'r') as romzip:
                for file in romzip.namelist():
                    if rom_name == 'grand_l4' and file != 'lzrd_u26.l4':
                        # prefer this ROM image in the ZIP over all others (more complete list of audits)
                        continue
                    if rom_name == 'bnzai_l3' and file != 'banz_u26.l3':
                        # final audit has an actual name(?) "PLAY AT TI"
                        continue
                    if rom_name == 'rdkng_l4' and file != 'road_u26.l4':
                        continue
                    with romzip.open(file) as f:
                        audits = get_audits(file, f.read(), nv_map['checksum8'][0])
                        if audits:
                            nv_map['audits'] = {'Audits': audits}
                            break   # we've found audits for this rom, stop checking files in ZIP
        except FileNotFoundError:
            pass


for map_filename in glob.glob(MAP_DIR + '*.nv.json'):
    if 'gmine_l2' in map_filename:
        continue  # non-standard System 11 game (e.g., no checksum8 audits)

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
        try_audits_update(nv_map)
        with open(map_filename, 'w') as f:
            f.write(json.dumps(nv_map, indent=2))
            f.write('\n')

print(str_to_charmap(b"   LEFT COINS   "))
