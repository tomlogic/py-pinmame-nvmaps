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

# Helper class to track whether multi-byte values in nvram file are big-endian
# (MSB-first) or little-endian (LSB-first).  6809 (WPC) is big-endian.
class Endian:
    LITTLE = 1234
    BIG = 4321


class ParseNVRAM(object):
    def __init__(self, nv_json, nvram):
        self.nv_json = nv_json
        self.nvram = nvram
        self.set_byteorder()

    def set_byteorder(self):
        if self.nv_json.get('_endian') == 'little':
            self.byteorder = Endian.LITTLE
        else:
            self.byteorder = Endian.BIG  # default setting

    def load_json(self, json_path):
        json_fh = open(json_path, 'r')
        self.nv_json = json.load(json_fh)
        json_fh.close()
        self.set_byteorder()

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

    # offsets for a given dict
    def offsets(self, dict):
        if 'offsets' in dict:
            return map((lambda offset: self.to_int(offset)),
                dict['offsets'])
                
        start = self.to_int(dict.get('start', '0'))
        end = start
        if 'length' in dict:
            length = self.to_int(dict['length'])
            if length <= 0:
                raise AssertionError('invalid length (%s); must be > 0'
                    % (dict['length']))
            end = start + length - 1
        elif 'end' in dict:
            end = self.to_int(dict['end'])
            if end < start:
                raise AssertionError('end (%s) is less than start (%s)'
                    % (dict['end'], dict['start']))

        return list(range(start, end + 1))
    
    # return 'start' to 'end' bytes (inclusive) from 'self.nvram', or
    # 'start' to 'start + length - 1' bytes (inclusive)
    # or the single byte at 'start' if 'end' and 'length' are not specified
    # or the bytes from offsets in a list called 'offsets'
    def get_bytes_unmasked(self, dict):
        return bytearray(map((lambda offset: self.nvram[offset]),
            self.offsets(dict)))

    # same as get_bytes_unmasked() but apply the mask in 'mask' if present
    def get_bytes(self, dict):
        ba = self.get_bytes_unmasked(dict)
        if 'mask' in dict:
            mask = self.to_int(dict['mask'])
            return bytearray(map((lambda b: b & mask), ba))
        return ba

    # Return an integer value from one or more bytes in memory
    # handles multi-byte integers (int), binary coded decimal (bcd) and
    # single-byte enumerated (enum) values.  Returns None for unsupported
    # encodings.
    def get_value(self, dict):
        value = None
        if 'encoding' in dict:
            encoding = dict['encoding']
            ba = self.get_bytes(dict)
            packed = dict.get('packed', True)
            if self.byteorder == Endian.LITTLE:
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
                value *= self.to_int(dict.get('scale', '1'))
                value += self.to_int(dict.get('offset', '0'))

        return value

    # replace a value stored in self.nvram[]
    def set_value(self, dict, value):
        encoding = dict['encoding']
        old_bytes = self.get_bytes(dict);
        start = self.to_int(dict['start'])
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

            if self.byteorder == Endian.BIG:
                new_bytes = reversed(new_bytes)

        self.nvram[start:end] = bytearray(new_bytes)

    # format a multi-byte integer using options in 'dict'
    def format_value(self, dict, value):
        # `special_values` contains strings to use in place of `value`
        # commonly used at the low end of a range for off/disabled
        if 'special_values' in dict and str(value) in dict['special_values']:
            return dict['special_values'][str(value)]

        units = dict.get('units')
        if units == 'seconds':
            m, s = divmod(value, 60)
            h, m = divmod(m, 60)
            return "%d:%02d:%02d" % (h, m, s)
        elif units == 'minutes':
            return "%d:%02d:00" % divmod(value, 60)
        return self.format_number(value) + dict.get('suffix', '')

    # format bytes from 'nvram' depending on members of 'dict'
    # uses 'encoding' to specify format
    # 'start' and either 'end' or 'length' for range of bytes
    def format(self, entry):
        if entry is None or 'encoding' not in entry:
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

    def verify_checksum8(self, dict, verbose = False, fix = False):
        valid = True
        ba = self.get_bytes(dict)
        offset = self.to_int(dict['start'])
        grouping = dict.get('groupings', len(ba))
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

    def verify_checksum16(self, dict, verbose = False, fix = False):
        ba = self.get_bytes(dict)
        # pop last two bytes as stored checksum16
        if self.byteorder == Endian.BIG:
            stored_sum = ba.pop() + ba.pop() * 256
        else:
            stored_sum = ba.pop() * 256 + ba.pop()
        checksum_offset = self.to_int(dict['start']) + len(ba)
        calc_sum = 0xFFFF - (sum(ba) & 0xFFFF)
        if calc_sum != stored_sum:
            if verbose:
                print("checksum16 at %s: 0x%04X != 0x%04X %s" % (dict['start'],
                    calc_sum, stored_sum, dict.get('label', '')))
            if fix:
                if self.byteorder == Endian.BIG:
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
            s = self.format(p)
            if s != '0' or not scores:
                scores.append(s)
        return scores

    def high_score(self, entry, short_labels=False):
        formatted_score = None
        label = entry.get('label', '')
        if not label.startswith('_'):
            if short_labels:
                label = entry.get('short_label', label)
            initials = self.format(entry.get('initials'))
            # ignore scores with blank initials
            if initials is not None:
                if 'score' in entry:
                    formatted_score = '%s: %s %s' % (label, initials,
                        self.format(entry['score']))
                else:
                    formatted_score = '%s: %s' % (label, initials)
                if 'timestamp' in entry:
                    formatted_score += ' at ' + self.format(entry['timestamp'])
            
        return formatted_score
    
    # section should be 'high_scores' or 'mode_champions'
    def high_scores(self, section='high_scores', short_labels=False):
        scores = []
        for entry in self.nv_json.get(section, []):
            formatted_score = self.high_score(entry, short_labels)
            if formatted_score:
                scores.append(formatted_score)
        return scores

    def last_played(self):
        return self.format(self.nv_json.get('last_played'))

    def format_audit(self, audit, key=None):
        value = self.format(audit)
        if value is None:
            value = audit.get('default', '')
        if key:
            label = key + ' ' + audit['label']
        else:
            label = audit['label']
        return label + ': ' + value
    
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

    def dump(self, checksums=True):
        for section in ['audits', 'adjustments']:
            for group in sorted(self.nv_json.get(section, {}).keys()):
                if group.startswith('_'):
                    continue
                print(group)
                print('-' * len(group))
                for entry in self.entry_list(section, group):
                    print(self.format_audit(entry[1], entry[0]))
                print('')

        if 'game_state' in self.nv_json:
            for key, value in self.nv_json['game_state'].items():
                print(value.get('label', '?') + ': ' + self.format(value))
        
        for section in ['high_scores', 'mode_champions']:
            for score in self.high_scores(section, short_labels = True):
                print(score)

        print('')
        print("---Last Game---")
        last_played = self.last_played()
        if last_played is not None:
            print(last_played)
        for s in self.last_game_scores():
            print(s)

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
