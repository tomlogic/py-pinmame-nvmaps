#!/usr/bin/env python3
"""
A special hex dump for .nv files that displays known fields instead of
the traditional ASCII character display.

Uses decimal offsets for ease of updating JSON map files.

TODO:
- command-line option to show hex offsets
- command-line option to select bytes per line
- fix high score parsing/display -- some games split initials from scores
    - have separate mapping for initials and score
"""
import argparse
import json
from curses.ascii import isprint

import nvram_parser
from nvram_parser import NIBBLE_LOW, NIBBLE_HIGH, NIBBLE_BOTH

BYTES_PER_LINE = 16

class ChecksumMapping(object):
    """Simplified RamMapping object used for checksum values."""
    def __init__(self, start, end, label, checksum16=False):
        self.start = start
        self.end = end
        self.label = label
        self.checksum16 = checksum16

    def offsets(self):
        if self.checksum16:
            return [self.end - 1, self.end]
        return [self.end]

    def format_mapping(self, nvram):
        """Return a tuple of (label, value) for this entry for the given nvram data."""
        # TODO: update to take endian into consideration
        if self.checksum16:
            label = 'checksum16[%u:%u]' % (self.start, self.end - 1)
            value = '0x%04X' % (nvram[self.end - 1] * 256 + nvram[self.end])
        else:
            label = 'checksum8[%u:%u]' % (self.start, self.end)
            value = '0x%02X' % nvram[self.end]

        if self.label:
            value += ' (%s)' % self.label
        return label, value

global nibble, nv

def hex_line(offset, count, text=None):
    b = []
    ch = []
    while len(b) < BYTES_PER_LINE:
        if offset < len(nv) and len(b) < count:
            if nibble == NIBBLE_LOW:
                b.append(' %1X' % (nv[offset] & 0x0F))
            elif nibble == NIBBLE_HIGH:
                b.append('%1X ' % (nv[offset] >> 8))
            else:
                b.append('%02X' % nv[offset])

            if nibble == NIBBLE_BOTH:
                # we can potentially have printable text
                if isprint(nv[offset]):
                    ch.append(chr(nv[offset]))
                else:
                    ch.append('.')
            else:
                ch.append(' ')
        else:
            # padding
            b.append('  ')
            ch.append(' ')
        offset += 1

    if not text:
        text = ''.join(ch)
    return "%s | %s" % (' '.join(b), text)


def main():
    global nibble, nv

    parser = argparse.ArgumentParser(description='PinMAME nvram hex dumper')
    parser.add_argument('--map',
                        help='use this map (typically ending in .nv.json)')
    parser.add_argument('--rom',
                        help='use default map for <rom> instead of one based on <nvram> filename')
    parser.add_argument('filename', help='nvram file to dump')
    args = parser.parse_args()

    if not args.map:
        # find a JSON file for the given nvram file
        if not args.rom:
            args.rom = nvram_parser.rom_for_nvpath(args.filename)
        args.map = nvram_parser.map_for_rom(args.rom)

        if not args.map:
            print("Couldn't find a map for %s" % args.filename)
            return

    with open(args.map, 'r') as f:
        nv_map = json.load(f)

    with open(args.filename, 'rb') as f:
        nv = bytearray(f.read())

    parser = nvram_parser.ParseNVRAM(nv_map, nv)

    print('dumping %s' % args.filename)
    nibble = parser.metadata.get('nibble')
    if nibble == 'low':
        nibble = NIBBLE_LOW
    elif nibble == 'high':
        nibble = NIBBLE_HIGH
    else:
        nibble = NIBBLE_BOTH

    # Create a dictionary of RamMapping objects using offset as the key.
    entry = {}
    for m in parser.mapping:
        if m.section == 'dip_switches':
            # skip over dip_switches -- their offsets aren't memory addresses
            continue

        # sometimes offsets is a map(?) so convert it to a list
        offsets = list(m.offsets())
        entry[offsets[0]] = m

    # add fake entries for checksum8 and checksum16 values
    for checksum in ['checksum8', 'checksum16']:
        is_16 = (checksum == 'checksum16')
        for c in nv_map.get(checksum, []):
            start = c['start']
            end = c['end']
            grouping = c.get('groupings', end - start + 1)
            while start < c['end']:
                end = start + grouping - 1
                entry[end - is_16] = ChecksumMapping(start, end, c.get('label'), is_16)
                start = end + 1

    offset = 0
    while offset < len(nv):
        # If this offset is in entry[], display it with its formatted value.
        mapping = entry.get(offset)
        if mapping:
            count = len(list(mapping.offsets()))
            (label, value) = mapping.format_mapping(nv)
            if label:
                text = '%s: %s' % (label, value)
            else:
                text = value
        else:
            # show printable ASCII characters for conversion
            text = None

            # Display up to BYTES_PER_LINE bytes, avoiding the next known entry
            count = 1
            while count < BYTES_PER_LINE and not entry.get(offset + count):
                count += 1

        print("%6u: %s" % (offset, hex_line(offset, count, text)))
        offset += count


if __name__ == '__main__':
    main()
