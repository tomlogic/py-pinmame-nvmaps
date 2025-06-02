#!/usr/bin/env python3
"""
Tool for displaying DIP switch settings from a map, and editing the
settings stored in a .nv file.

TODO: Modify command-line handling to allow for --on/--off for .nv files without a map.
"""
import argparse
import json

import nvram_parser


def parse_switch_list(switches) -> list:
    """
    Helper for --on and --off command-line options.
    :param switches: comma-separated list of switch numbers and ranges (e.g., "1,2,3-5")
    :return: list of individual switch numbers as integers
    """
    switch_list = []
    if switches:
        for item in switches.split(','):
            if '-' in item:
                (start, end) = item.split('-')
                for i in range(int(start), int(end) + 1):
                    switch_list.append(i)
            else:
                switch_list.append(int(item))
    return switch_list


def edit_item(mapping: nvram_parser.RamMapping, nv) -> bool:
    """
    Interactive editor for changing a DIP switch entry.
    :param mapping: RamMapping object for a DIP switch group
    :param nv: contents of .nv file
    :return: True if user entered a new value
    """
    label = mapping.format_label()
    current_value = mapping.get_value(nv)
    while True:
        print('\n%s\n%s' % (label, '-' * len(label)))
        for index, label in enumerate(mapping.entry_values()):
            print('%c%2u: %s' % (' *'[index == current_value], index, label))
        try:
            new = input('\nNew setting [%u]: ' % current_value)
        except EOFError:
            exit(0)
        if not new:
            # blank entry -- no change to current setting
            return False
        else:
            try:
                new_value = int(new)
                if new_value != current_value:
                    mapping.set_value(nv, new_value)
                    return True
                else:
                    return False
            except ValueError:
                if new != '?':
                    print('Invalid option')


def switch_editor(parser: nvram_parser.ParseNVRAM) -> bool:
    """
    Interactive DIP switch editor.
    :param parser: ParseNVRAM object to use with DIP switch editor.
    :return: True if user wants to save changes
    """
    groups = []
    for m in parser.mapping:
        if m.section == 'dip_switches':
            groups.append(m)

    print_menu = True
    while True:
        if print_menu:
            print_menu = False
            print()
            for index, mapping in enumerate(groups):
                print('%2u: %s = %s' % (index + 1, mapping.format_label(),
                                        mapping.format_entry(parser.nvram)))

        print()
        try:
            command = input('Entry to edit, "?" for list, "s" to save, or "q" to quit: ')
        except EOFError:
            exit(0)
        try:
            index = int(command)
            if index < 1 or index > len(groups):
                print("Invalid option")
            else:
                edit_item(groups[index - 1], parser.nvram)
                print_menu = True
        except ValueError:
            if command.startswith('s'):
                return True
            elif command.startswith('q'):
                return False
            elif command.startswith('?'):
                print_menu = True
            else:
                print_menu = True
                print("Invalid option")


def main():
    parser = argparse.ArgumentParser(description='PinMAME nvram hex dumper')
    parser.add_argument('--map',
                        help='use this map (typically ending in .nv.json)')
    parser.add_argument('--rom',
                        help='use default map for <rom> instead of one based on <nvram> filename')
    parser.add_argument('--nvram', help='nvram file to dump')
    parser.add_argument('--md', action='store_true',
                        help='output documentation in Markdown format')
    parser.add_argument('--edit', action='store_true',
                        help='run interactive switch editor')
    parser.add_argument('--on', metavar='DIPSW_LIST',
                        help='comma-separated list of switches to turn on')
    parser.add_argument('--off', metavar='DIPSW_LIST',
                        help='comma-separated list of switches to turn off')
    args = parser.parse_args()

    if (args.edit or args.on or args.off) and not args.nvram:
        parser.error('--edit, --on, and --off require the --nvram option')

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

    save_changes = False
    if nv:
        if args.on or args.off:
            save_changes = True
            for sw in parse_switch_list(args.on):
                nvram_parser.dipsw_set(nv, sw, True)
            for sw in parse_switch_list(args.off):
                nvram_parser.dipsw_set(nv, sw, False)

    parser = nvram_parser.ParseNVRAM(nv_map, nv)

    if args.edit:
        save_changes = switch_editor(parser)

    if save_changes:
        print('Saving changes to %s...' % args.nvram)
        with open(args.nvram, 'wb') as f:
            f.write(nv)
        exit(0)

    if args.edit:
        # don't show settings after editing
        exit(0)

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
