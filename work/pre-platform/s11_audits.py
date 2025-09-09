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


charmapping = b' 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def charmap_to_bytes(bytestring):
    retval = []
    for b in bytestring:
        if b < len(charmapping):
            retval.append(charmapping[b])
        elif b == 0x2E:
            retval.append(ord('<'))
        elif b == 0x2F:
            retval.append(ord('='))
        elif b == 0x30:
            retval.append(ord('>'))
        elif b == 0x39:
            retval.append(ord('-'))
        elif b == 0x4C:
            retval.append(ord("'"))
        elif 85 <= b < 85 + len(charmapping):
            retval.append(charmapping[b - 85])
            retval.append(ord('.'))
        elif 170 <= b <= 170 + len(charmapping):
            retval.append(charmapping[b - 170])
            retval.append(ord(','))
        else:
            print('0x%02X' % b)
            retval.append(ord('?'))
            # raise ValueError("Can't convert charmap to string %r" % bytestring)

    return bytearray(retval)


def get_bytes_via_table(romdata, entry_address, offset_mask):
    # offset is address of big endian address to 8 characters
    str_address = romdata[entry_address] * 256 + romdata[entry_address + 1]
    str_offset = str_address & ~offset_mask        # mask off address bit to get file offset
    return romdata[str_offset:str_offset + 8]


def get_rom_label(romdata, offset, offset_mask, is_split):
    if offset_mask:
        # offset is address of two string table entries
        return get_bytes_via_table(romdata, offset, offset_mask) + get_bytes_via_table(romdata, offset + 2, offset_mask)
    elif is_split:
        return romdata[offset:offset + 7] + b' ' + romdata[offset + 7: offset + 14]
    else:
        return romdata[offset: offset + 16]


# taxi_l4 shifts some audits to higher positions
# this table is the offset for each shift
taxi_adjust = {
    33: 6,
    40: 3,
    41: 3,
    42: 3,
    43: 3,
    44: 3,
    45: 3,
    46: 3,
    47: 3
}


def get_audits(file, romdata, audit_regions):
    charmap = False
    split = False
    offset_mask = 0
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
            offset_increment = 4    # two 16-bit addresses
            offset_mask = 0x4000    # bits to set when converting between file offset and address
            coins = romdata.find(b' COINS  ')
            if coins < 0:
                # try searching for the "charmap" version of the COINS string
                charmap = True
                offset_mask = 0x8000
                # first try b'COINS   ' (Diner) and then b' COINS  ' (Rollergames)
                coins = romdata.find(str_to_charmap(b'COINS   '))
                if coins < 0:
                    # this version worked on Rollergames
                    coins = romdata.find(str_to_charmap(b' COINS  '))
            if coins < 0:
                return None
            print("coins at 0x%04X (%s charmap)" % (coins, "with" if charmap else "without"))
            # hack for converting to a bytes object
            coin_addr = coins | offset_mask
            coin_pattern = bytes([(coin_addr >> 8), coin_addr & 0xFF])
            offset = romdata.find(coin_pattern) - 2
        if offset < 0:
            return None

    audits = {}
    print('for %s, left coins at %u' % (file, offset))
    audit_index = 1

    for region, audit_region in enumerate(audit_regions):
        audit_address = audit_region['start']
        # some (all?) games actually start at the second "audit" position
        # TODO: should I update the checksum8 addresses?
        if (region == 0) and (True or CURRENT_ROM in ['hs_l4']):
            audit_address += 4
        while True:
            audit_name = ''
            label = get_rom_label(romdata, offset, offset_mask, split)
            if charmap:
                label = charmap_to_bytes(label)

            for b in label:
                if b == 0x82:
                    # special character for quoting, appears as backtick on alphanumeric display
                    audit_name += "'"
                elif b & 0x80:  # bit 7 (0x80) indicates '.' after character
                    audit_name += '%c.' % chr(b & 0x7F)
                elif b == ord('f'):
                    audit_name += ')'
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
            # remove leading/trailing whitespace
            audit_name = audit_name.strip()

            while '  ' in audit_name:
                # convert duplicated spaces to a single space
                audit_name = audit_name.replace('  ', ' ')

            # fix numbers using 'O' as leading zero (0)
            audit_name = audit_name.replace('O.0', '0.0')
            audit_name = audit_name.replace('O.4', '0.4')
            audit_name = audit_name.replace('O.5', '0.5')
            audit_name = audit_name.replace('O.9', '0.9')

            if audit_name.startswith('PERCENT') \
                    or audit_name.startswith('PERCT.') \
                    or audit_name.startswith('AV. ') \
                    or audit_name.startswith('AVG. ') \
                    or audit_name == 'FIRST REPLAY IS' \
                    or (audit_name.startswith('H.S.T.D.') and audit_name.endswith('XXX')):
                print("AUDIT %02u: %s calculated dynamically" % (audit_index, audit_name))
            elif audit_index == 11 and CURRENT_ROM == 'pool_l7':
                # AU11 on Pool Sharks L-7 would be "PERCENT SPECIAL" if the game had a SPECIAL to award
                print("AUDIT %02u: %s (PERCENT SPECIAL) calculated dynamically" % (audit_index, audit_name))
            elif audit_name in ['H.S.RESET COUNTER', 'H.S. RESET COUNTER']:
                # special location -- immediately after initials
                hstd_reset = nv_map['high_scores'][-1]['initials']['start'] + 3
                if CURRENT_ROM == 'pool_l7':
                    # Pool Sharks has two sets of initials at a non-standard location
                    hstd_reset = 1834
                print("AUDIT %02u: %s at %u **" % (audit_index, audit_name, hstd_reset))
                audits['%02u' % audit_index] = audit_dict(hstd_reset, audit_name)
            else:
                if audit_address >= audit_region['end']:
                    break
                if audit_index == 40 and CURRENT_ROM in ['bk2k_l4', 'bnzai_l3', 'eatpm_l2', 'eatpm_l4',
                                                         'esha_l4c', 'esha_la1', 'esha_la3', 'esha_ma3',
                                                         'rollr_l2']:
                    # these games skip over the expected position for audit 40 (0x6C4) and uses the next slot
                    audit_address += 4
                if CURRENT_ROM == 'taxi_l4':
                    # Audits end at 49.  Positions 50-52 used for 45-47.
                    if audit_index == 50:
                        break
                    # calculate the shifted address for Taxi
                    taxi_address = audit_address + taxi_adjust.get(audit_index, 0) * 4
                    print("AUDIT %02u: %s at %u" % (audit_index, audit_name, taxi_address))
                    audits['%02u' % audit_index] = audit_dict(taxi_address, audit_name)
                else:
                    print("AUDIT %02u: %s at %u" % (audit_index, audit_name, audit_address))
                    audits['%02u' % audit_index] = audit_dict(audit_address, audit_name)
                audit_address += 4
            audit_index += 1
            offset += offset_increment

    return audits


# use this ROM file for each specific PinMAME version
preferred_rom = {
    'grand_l4': 'lzrd_u26.l4',      # most complete list of audits
    'bnzai_l3': 'banz_u26.l3',
    'rdkng_l4': 'road_u26.l4',
    'diner_l4': 'dinr_u27.l4',
    'rollr_l2': 'rolr_u26.l2',
    'bguns_l8': 'guns_u27.l8',      # Big Guns has both ROM versions in one ZIP file
    'bguns_la': 'u27-l-a.rom',
    'whirl_l3': 'whir_u27.l3',
    'pool_l7': 'pool_u27.l7',
    'eatpm_l2': 'u26_la2.rom',
    'eatpm_l4': 'u26-lu4.rom',
    'esha_la3': 'eshk_u26.l3',
    'esha_ma3': 'eshk_u26.ma3',     # Metallica custom has slightly different labels on 3 audits
    'jokrz_l6': 'jokeru27.l6',
}


def try_audits_update(nv_map):
    global CURRENT_ROM

    for rom_name in nv_map['_roms']:
        if rom_name.startswith('hs_') or rom_name.startswith('tsptr_'):
            print('"audits" section already present')
            return
        try:
            if rom_name == 'bguns_la':
                # Big Guns LA roms are in the L8 ZIP file
                romfile = ROM_DIR + 'bguns_l8' + '.zip'
            else:
                romfile = ROM_DIR + rom_name + '.zip'
            with zipfile.ZipFile(romfile, 'r') as romzip:
                for file in romzip.namelist():
                    preferred = preferred_rom.get(rom_name)
                    if preferred and file != preferred:
                        continue
                    with romzip.open(file) as f:
                        audits = get_audits(file, f.read(), nv_map['checksum8'])
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
