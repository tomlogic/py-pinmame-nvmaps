#!/usr/bin/env python3
"""
Tool for displaying DIP switch settings from a map, and editing the
settings stored in a .nv file.

TODO: make a list of sections to use for a top-level menu to select switches to change
TODO: add --edit command-line option to show menus and allow editing
Edit UI:
- use number to select section or option
- use q/x to quit/exit, s/w to save/write and exit, ? to print top menu again
- blank line keeps existing option
- blank line at top level prompts to save/exit/continue editing

TODO: add --md for markdown format
Title
=====
|     | SW01 |SW02 |SW03|SW04|SW05| Left Coin Chute              |
|-----|:----:|:---:|:--:|:--:|:--:|------------------------------|
|  0 | off  | off |off |off |off | 1 credit/coin                |

- remove colon after option/value
- add pipe to start and end
- use pipe instead of + on dividing line
- use ':--:' to center columns
- leave out initial column?
- identify current selection when nvram file specified?
"""
import argparse
import json

import nvram_parser


def main():
    parser = argparse.ArgumentParser(description='PinMAME nvram hex dumper')
    parser.add_argument('--map',
                        help='use this map (typically ending in .nv.json)')
    parser.add_argument('--rom',
                        help='use default map for <rom> instead of one based on <nvram> filename')
    parser.add_argument('--nvram', help='nvram file to dump')
    args = parser.parse_args()

    if not args.map:
        # find a JSON file for the given nvram file
        if not args.rom and args.nvram:
            args.rom = nvram_parser.rom_for_nvpath(args.nvram)
        args.map = nvram_parser.map_for_rom(args.rom)

        if not args.map:
            print("No map selected.")
            return

    with open(args.map, 'r') as f:
        nv_map = json.load(f)

    if args.nvram:
        with open(args.nvram, 'rb') as f:
            nv = bytearray(f.read())
    else:
        nv = None

    if args.rom:
        print('DIP Switches for %s' % nvram_parser.rom_name(args.rom))
    if args.nvram:
        print('(with current values from %s)' % args.nvram)
    print()

    parser = nvram_parser.ParseNVRAM(nv_map, nv)
    off_on = ['off ', ' ON ']
    for m in parser.mapping:
        if m.section != 'dip_switches':
            continue
        columns = len(list(m.offsets()))
        header = '|'.join(map((lambda x: 'SW%02u' % x), m.offsets()))
        divider = '+'.join(map((lambda x: '----'), m.offsets()))
        print("    |%s| %s" % (header, m.format_label()))
        print("----+%s+-------------------------------" % divider)
        if nv:
            current = m.get_value(nv)
        else:
            current = None
        values = m.entry_values()
        for index, audit in enumerate(values):
            if current == index:
                marker = '>'
            else:
                marker = ' '
            switches = []
            for i in reversed(range(columns)):
                switches.append(off_on[(index & (1 << i)) != 0])
            print('%c%2u:|%s| %s' % (marker, index, '|'.join(switches), audit))
        print()

if __name__ == '__main__':
    main()
