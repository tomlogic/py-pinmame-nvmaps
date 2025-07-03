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

from nvram_parser import ParseNVRAM, rom_for_nvpath, map_for_rom


def main():
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
            args.rom = rom_for_nvpath(args.filename)
        args.map = map_for_rom(args.rom)

        if not args.map:
            print("Couldn't find a map for %s" % args.filename)
            return

    with open(args.map, 'r') as f:
        nv_map = json.load(f)

    with open(args.filename, 'rb') as f:
        nv = bytearray(f.read())

    parser = ParseNVRAM(nv_map, nv)

    print('dumping %s' % args.filename)

    parser.hex_dump()


if __name__ == '__main__':
    main()
