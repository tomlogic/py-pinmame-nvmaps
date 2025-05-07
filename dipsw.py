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
    parser.add_argument('--md', action='store_true',
                        help='output documentation in Markdown format')
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
        title = 'DIP Switches for %s' % nvram_parser.rom_name(args.rom)
    else:
        title = 'DIP Switches from %s' % args.map
    print(title)
    if args.md:
        print('=' * len(title))
    if args.nvram:
        subtitle = '(with current values from %s)' % args.nvram
        print(subtitle)
        if args.md:
            print('-' * len(subtitle))
    print()

    parser = nvram_parser.ParseNVRAM(nv_map, nv)

    off_on = ['off ', ' ON ']
    for m in parser.mapping:
        if m.section != 'dip_switches':
            continue
        columns = len(list(m.offsets()))

        # calculate maximum width for grouping name and descriptions
        max_width = len(m.format_label())
        for index, description in enumerate(m.entry_values()):
            if len(str(description)) > max_width:
                max_width = len(str(description))
        dashes = '-' * max_width
        if args.md:
            header = '|'.join(map((lambda x: ' SW%02u ' % x), m.offsets()))
            divider = '|'.join(map((lambda x: ':----:'), m.offsets()))
            print("|%s| %s |" % (header, m.format_label().ljust(max_width)))
            print("|%s|:%s-|" % (divider, dashes))
        else:
            header = '|'.join(map((lambda x: 'SW%02u' % x), m.offsets()))
            divider = '+'.join(map((lambda x: '----'), m.offsets()))
            print("    |%s| %s" % (header, m.format_label()))
            print("----+%s+-%s-" % (divider, dashes))
        if nv:
            current = m.get_value(nv)
        else:
            current = None
        for index, description in enumerate(m.entry_values()):
            switches = []
            for i in reversed(range(columns)):
                switches.append(off_on[(index & (1 << i)) != 0])
            if args.md:
                description = str(description).ljust(max_width)
                print('| %s | %s |' % (' | '.join(switches), description))
            else:
                marker = '>' if current == index else ' '
                print('%c%2u:|%s| %s' % (marker, index, '|'.join(switches), description))
        print()

if __name__ == '__main__':
    main()
