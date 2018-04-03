#!env python

"""
ParseNVRAM: a tool for extracting information from PinMAME's ".nv" files.
This program makes us of content from the PinMAME NVRAM Maps project.

Copyright (C) 2015 by Tom Collins <tom@tomlogic.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import json
import sys
from datetime import datetime


class ParseNVRAM(object):
    def __init__(self, nv_json, nvram):
        self.nv_json = nv_json
        self.nvram = nvram
        self.big_endian = True
        self.mapping = []
        self.process_json()

    def load_json(self, json_path):
        json_fh = open(json_path, 'r')
        self.nv_json = json.load(json_fh)
        json_fh.close()
        self.process_json()

    """Process JSON file loaded into self.nv_json.  Sets self.big_endian and
    self.mapping, a normalized list of JSON entries as 4-item lists.
        0 (section): audits, adjustments, game_state, or score_record
        1 (group): None or a group name for the section
        2 (key): None or the sortable "key" for the mapping
        3 (mapping): entry with mapping description
    """
    def process_json(self):
        self.big_endian = self.nv_json.get('_endian') != 'little'
        self.mapping = []
        for section in ['audits', 'adjustments']:
            for group in sorted(self.nv_json.get(section, {}).keys()):
                if group.startswith('_'):
                    continue
                for entry in self.entry_list(section, group):
                    self.mapping.append([section, group, entry[0],  entry[1]])

        if 'game_state' in self.nv_json:
            for key, entry in self.nv_json['game_state'].items():
                self.mapping.append(['game_state', 'Game State', key, entry])

        player_num = 1
        for p in self.nv_json.get('last_game', []):
            entry = p.copy()
            entry['label'] = 'Player %u' % player_num
            entry['short_label'] = 'P%u' % player_num
            self.mapping.append(['game_state', 'Player Scores', None, entry])
            player_num += 1

        for section in ['high_scores', 'mode_champions']:
            for entry in self.nv_json.get(section, []):
                self.mapping.append(['score_record', section, None, entry])

    def load_nvram(self, nvram_path):
        nv_fh = open(nvram_path, 'rb')
        self.nvram = bytearray(nv_fh.read())
        nv_fh.close()

    # Format large numbers with thousands separators (',' or '.').  Uses
    # locale setting in Python 2.7 or later, manually uses ',' for Python 2.6.
    @staticmethod
    def format_number(number):
        if sys.version_info >= (2,7,0):
            return '{0:,}'.format(number)

        s = '%d' % number
        groups = []
        while s and s[-1].isdigit():
            groups.append(s[-3:])
            s = s[:-3]
        return s + ','.join(reversed(groups))

    # Return 'v' if already an int, otherwise assume string and convert
    # with a base of '0' (which handles leading 0 as octal and 0x as hex)
    @staticmethod
    def to_int(v):
        if type(v) is int:
            return v
        return int(v, 0)

    # offsets for a given entry
    def offsets(self, entry):
        if 'initials' in entry or 'score' in entry:
            # special-case handling for high score records
            offsets = list()
            for sub_entry in ['initials', 'score', 'timestamp']:
                if sub_entry in entry:
                    offsets += self.offsets(entry[sub_entry])
            return offsets

        if 'offsets' in entry:
            return map((lambda offset: self.to_int(offset)),
                       entry['offsets'])
                
        start = self.to_int(entry.get('start', '0'))
        end = start
        if 'length' in entry:
            length = self.to_int(entry['length'])
            if length <= 0:
                raise AssertionError('invalid length (%s); must be > 0'
                                     % (entry['length']))
            end = start + length - 1
        elif 'end' in entry:
            end = self.to_int(entry['end'])
            if end < start:
                raise AssertionError('end (%s) is less than start (%s)'
                                     % (entry['end'], entry['start']))

        return list(range(start, end + 1))
    
    # return 'start' to 'end' bytes (inclusive) from 'self.nvram', or
    # 'start' to 'start + length - 1' bytes (inclusive)
    # or the single byte at 'start' if 'end' and 'length' are not specified
    # or the bytes from offsets in a list called 'offsets'
    def get_bytes_unmasked(self, entry):
        return bytearray(map((lambda offset: self.nvram[offset]),
                             self.offsets(entry)))

    # same as get_bytes_unmasked() but apply the mask in 'mask' if present
    def get_bytes(self, entry):
        ba = self.get_bytes_unmasked(entry)
        if 'mask' in entry:
            mask = self.to_int(entry['mask'])
            return bytearray(map((lambda b: b & mask), ba))
        return ba

    # Return an integer value from one or more bytes in memory
    # handles multi-byte integers (int), binary coded decimal (bcd) and
    # single-byte enumerated (enum) values.  Returns None for unsupported
    # encodings.
    def get_value(self, entry):
        value = None
        if 'encoding' in entry:
            encoding = entry['encoding']
            ba = self.get_bytes(entry)
            packed = entry.get('packed', True)
            if not self.big_endian:
                ba.reverse()

            if encoding == 'bcd':
                value = 0
                for b in ba:
                    if packed:
                        value = value * 100 + (b >> 4) * 10 + (b & 0x0F)
                    else:
                        value = value * 10 + (b & 0x0F)
            elif encoding == 'int' or encoding == 'bits':
                value = 0
                for b in ba:
                    value = value * 256 + b
            elif encoding == 'enum':
                value = ba[0]

            if value is not None:
                value *= self.to_int(entry.get('scale', '1'))
                value += self.to_int(entry.get('offset', '0'))

        return value

    # replace a value stored in self.nvram[]
    def set_value(self, entry, value):
        encoding = entry['encoding']
        old_bytes = self.get_bytes(entry);
        start = self.to_int(entry['start'])
        end = start + len(old_bytes)
        # can now replace self.nvram[start:end]
        new_bytes = []

        if encoding == 'ch':
            assert type(value) is str and len(value) == len(old_bytes)
            new_bytes = list(value)
        elif encoding == 'wpc_rtc':
            if type(value) is datetime:
                # for day of week 1=Sunday, 7=Saturday
                # isoweekday() returns 1=Monday 7=Sunday
                new_bytes = [value.year / 256, value.year % 256,
                    value.month, value.day, value.isoweekday() % 7 + 1,
                    value.hour, value.minute]
        else:   # all formats where byte order applies
            if encoding == 'bcd':
                for x in old_bytes:
                    b = value % 100
                    new_bytes.append(b % 10 + 16 * (b / 10))
                    value /= 100
            elif encoding == 'int' or encoding == 'enum':
                for x in old_bytes:
                    b = value % 256
                    new_bytes.append(b)
                    value /= 256

            if self.big_endian:
                new_bytes = reversed(new_bytes)

        self.nvram[start:end] = bytearray(new_bytes)

    # format a multi-byte integer using options in 'entry'
    def format_value(self, entry, value):
        # `special_values` contains strings to use in place of `value`
        # commonly used at the low end of a range for off/disabled
        if 'special_values' in entry and str(value) in entry['special_values']:
            return entry['special_values'][str(value)]

        units = entry.get('units')
        if units == 'seconds':
            m, s = divmod(value, 60)
            h, m = divmod(m, 60)
            return "%d:%02d:%02d" % (h, m, s)
        elif units == 'minutes':
            return "%d:%02d:00" % divmod(value, 60)
        return self.format_number(value) + entry.get('suffix', '')

    # format bytes from 'nvram' depending on members of 'entry'
    # uses 'encoding' to specify format
    # 'start' and either 'end' or 'length' for range of bytes
    def format_entry(self, entry):
        if entry is None:
            return None
        if 'initials' in entry or 'score' in entry:
            return self.format_high_score(entry)
        if 'encoding' not in entry:
            return None
        encoding = entry['encoding']
        value = self.get_value(entry)
        packed = entry.get('packed', True)
        if encoding == 'bcd' or encoding == 'int':
            return self.format_value(entry, value)
        elif encoding == 'bits':
            values = entry.get('values', [])
            mask = 1
            bits_value = 0
            for b in values:
                if value & mask:
                    bits_value += b
                mask <<= 1
            return self.format_value(entry, bits_value)
        elif encoding == 'enum':
            values = entry['values']
            if value >= len(values):
                return '?' + str(value)
            return values[value]

        ba = self.get_bytes(entry)
        if encoding == 'ch':
            result = ''
            if packed:
                result = ba.decode('latin-1', 'ignore')
            else:
                while ba:
                    result += chr((ba.pop(0) & 0x0F) * 16 + (ba.pop(0) & 0x0F))
            if result == entry.get('default', '   '):
                return None
            return result
        elif encoding == 'raw':
            return ' '.join("%02x" % b for b in ba)
        elif encoding == 'wpc_rtc':
            # day of week is Sunday to Saturday indexed by [ba[4] - 1]
            return '%04u-%02u-%02u %02u:%02u' % (
                ba[0] * 256 + ba[1],
                ba[2], ba[3],
                ba[5], ba[6])
        return '[?' + encoding + '?]'

    def verify_checksum8(self, entry, verbose = False, fix = False):
        valid = True
        ba = self.get_bytes(entry)
        offset = self.to_int(entry['start'])
        grouping = entry.get('groupings', len(ba))
        count = 0
        calc_sum = 0
        for b in ba:
            if count == grouping - 1:
                checksum = 0xFF - (calc_sum & 0xFF)
                if checksum != b:
                    if verbose:
                        valid = False
                        print("%u bytes at 0x%04X checksum8 0x%02X != 0x%02X"
                            % (grouping, offset - count, checksum, b))
                    if fix:
                        self.nvram[offset] = checksum
                count = calc_sum = 0
            else:
                calc_sum += b
                count += 1
            offset += 1
        return valid

    def verify_all_checksum8(self, verbose = False, fix = False):
        valid = True
        for c in self.nv_json.get('checksum8', []):
            valid &= self.verify_checksum8(c, verbose, fix)
        return valid

    def verify_checksum16(self, entry, verbose = False, fix = False):
        ba = self.get_bytes(entry)
        # pop last two bytes as stored checksum16
        if self.big_endian:
            stored_sum = ba.pop() + ba.pop() * 256
        else:
            stored_sum = ba.pop() * 256 + ba.pop()
        checksum_offset = self.to_int(entry['start']) + len(ba)
        calc_sum = 0xFFFF - (sum(ba) & 0xFFFF)
        if calc_sum != stored_sum:
            if verbose:
                print("checksum16 at %s: 0x%04X != 0x%04X %s" % (entry['start'],
                                                                 calc_sum, stored_sum, entry.get('label', '')))
            if fix:
                if self.big_endian:
                    self.nvram[checksum_offset:checksum_offset + 2] = [
                        calc_sum / 256, calc_sum % 256]
                else:
                    self.nvram[checksum_offset:checksum_offset + 2] = [
                        calc_sum % 256, calc_sum / 256]
        return calc_sum == stored_sum

    def verify_all_checksum16(self, verbose = False, fix = False):
        valid = True
        for c in self.nv_json.get('checksum16', []):
            valid &= self.verify_checksum16(c, verbose, fix)
        return valid

    def last_game_scores(self):
        scores = []
        for p in self.nv_json.get('last_game', []):
            s = self.format_entry(p)
            if s != '0' or not scores:
                scores.append(s)
        return scores

    @staticmethod
    def format_label(entry, key=None, short_label=False):
        label = entry.get('label', '?')
        if label.startswith('_'):
            return None
        if short_label:
            label = entry.get('short_label', label)
        if key:
            label = key + ' ' + label
        return label

    def format_high_score(self, entry):
        record = self.format_entry(entry.get('initials'))
        # ignore scores with blank initials
        if record:
            if 'score' in entry:
                record += ' ' + self.format_entry(entry['score'])
            if 'timestamp' in entry:
                record += ' at ' + self.format_entry(entry['timestamp'])
        return record

    def high_score(self, entry, short_labels=False):
        label = self.format_label(entry, key=None, short_label=short_labels)
        if label:
            record = self.format_high_score(entry)
            return '%s: %s' % (label, record)
        return None
    
    # section should be 'high_scores' or 'mode_champions'
    def high_scores(self, section='high_scores', short_labels=False):
        scores = []
        for entry in self.nv_json.get(section, []):
            formatted_score = self.high_score(entry, short_labels)
            if formatted_score:
                scores.append(formatted_score)
        return scores

    def last_played(self):
        return self.format_entry(self.nv_json.get('last_played'))

    def format_audit(self, audit, key=None):
        value = self.format_entry(audit)
        if value is None:
            value = audit.get('default', '')
        return self.format_label(audit, key) + ': ' + value

    def dump_audit(self, audit, key=None):
        print(self.format_audit(audit, key))

    def entry_list(self, section, group):
        entries = []
        audit_group = self.nv_json[section][group]
        if isinstance(audit_group, list):
            for audit in audit_group:
                entries.append((None, audit))
        elif isinstance(audit_group, dict):
            for audit_key in sorted(audit_group.keys()):
                if audit_key.startswith('_'):
                    continue
                entries.append((audit_key, audit_group[audit_key]))
        else:
            ValueError("Can't process %s/%s" % (section, group))
        return entries

    """Return a tuple of (label, value) for a normalized mapping entry.
    """
    def format_mapping(self, normalized):
        (section, group, key, mapping) = normalized
        value = self.format_entry(mapping)
        if section in ['audits', 'adjustments']:
            if value is None:
                value = mapping.get('default', '')
            return (self.format_label(mapping, key), value)
        elif section in ['game_state', 'score_record']:
            return (self.format_label(mapping), value)
        else:
            ValueError('Not a normalized entry', normalized)

    def dump(self, checksums=True):
        last_group = None
        for map_entry in self.mapping:
            (section, group, key, mapping) = map_entry
            if group != last_group:
                print('')
                if group is not None:
                    print(group)
                    print('-' * len(group))
                last_group = group
            print('%s: %s' % self.format_mapping(map_entry))

        last_played = self.last_played()
        if last_played is not None:
            print('Last Played:', last_played)

        if checksums:
            # Verify all checksums in the file.  Note that we can eventually re-use
            # that part of the memory map to update checksums if modifying nvram values.
            self.verify_all_checksum16(verbose = True)
            self.verify_all_checksum8(verbose = True)


def print_usage():
    print("Usage: %s <json_file> <nvram_file>" % (sys.argv[0]))


def main():
    if len(sys.argv) < 3:
        print_usage()
        return
    else:
        jsonpath = sys.argv[1]
        nvpath = sys.argv[2]
        if jsonpath.find('.json', 0) == -1 or nvpath.find('.nv', 0) == -1:
            print_usage()
            return

    json_fh = open(jsonpath, 'r')
    nv_json = json.load(json_fh)
    json_fh.close()

    nv_fh = open(nvpath, 'rb')
    nvram = bytearray(nv_fh.read())
    nv_fh.close()

    p = ParseNVRAM(nv_json, nvram)
    p.dump()


if __name__ == '__main__': main()
