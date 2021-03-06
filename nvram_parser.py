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
    def format_score(self, number):
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
    def to_int(self, v):
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
        bytes = self.get_bytes_unmasked(dict)
        if 'mask' in dict:
            mask = self.to_int(dict['mask'])
            return bytearray(map((lambda b: b & mask), bytes))
        return bytes

    # Return an integer value from one or more bytes in memory
    # handles multi-byte integers (int), binary coded decimal (bcd) and
    # single-byte enumerated (enum) values.  Returns None for unsupported
    # encodings.
    def get_value(self, dict):
        value = None
        if 'encoding' in dict:
            format = dict['encoding']
            bytes = self.get_bytes(dict)
            packed = dict.get('packed', True)
            if self.byteorder == Endian.LITTLE:
                bytes.reverse()

            if format == 'bcd':
                value = 0
                for b in bytes:
                    if packed:
                        value = value * 100 + (b >> 4) * 10 + (b & 0x0F)
                    else:
                        value = value * 10 + (b & 0x0F)
            elif format == 'int' or format == 'bits':
                value = 0
                for b in bytes:
                    value = value * 256 + b
            elif format == 'enum':
                value = bytes[0]

            if value is not None:
                value *= self.to_int(dict.get('scale', '1'))
                value += self.to_int(dict.get('offset', '0'))

        return value

    # replace a value stored in self.nvram[]
    def set_value(self, dict, value):
        format = dict['encoding']
        old_bytes = self.get_bytes(dict);
        start = self.to_int(dict['start'])
        end = start + len(old_bytes)
        # can now replace self.nvram[start:end]
        new_bytes = []

        if format == 'ch':
            assert type(value) is str and len(value) == len(old_bytes)
            new_bytes = list(value)
        elif format == 'wpc_rtc':
            if type(value) is datetime:
                # for day of week 1=Sunday, 7=Saturday
                # isoweekday() returns 1=Monday 7=Sunday
                new_bytes = [value.year / 256, value.year % 256,
                    value.month, value.day, value.isoweekday() % 7 + 1,
                    value.hour, value.minute]
        else:   # all formats where byte order applies
            if format == 'bcd':
                for x in old_bytes:
                    b = value % 100
                    new_bytes.append(b % 10 + 16 * (b / 10))
                    value /= 100
            elif format == 'int' or format == 'enum':
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
        return self.format_score(value) + dict.get('suffix', '')

    # format bytes from 'nvram' depending on members of 'dict'
    # uses 'encoding' to specify format
    # 'start' and either 'end' or 'length' for range of bytes
    def format(self, dict):
        if dict is None or 'encoding' not in dict:
            return None
        format = dict['encoding']
        value = self.get_value(dict)
        packed = dict.get('packed', True)
        if format == 'bcd' or format == 'int':
            return self.format_value(dict, value)
        elif format == 'bits':
            values = dict.get('values', [])
            mask = 1
            bits_value = 0
            for b in values:
                if value & mask:
                    bits_value += b
                mask <<= 1
            return self.format_value(dict, bits_value)
        elif format == 'enum':
            values = dict['values']
            if value > len(values):
                return '?' + str(value)
            return values[value]
        if format == 'ch':
            result = ''
            bytes = self.get_bytes(dict)
            if packed:
                result = bytes.decode('latin-1', 'ignore')
            else:
                while bytes:
                    result += chr((bytes.pop(0) & 0x0F) * 16 + (bytes.pop(0) & 0x0F))
            if result == dict.get('default', '   '):
                return None
            return result
        elif format == 'raw':
            bytes = self.get_bytes(dict)
            return ' '.join("%02x" % b for b in bytes)
        elif format == 'wpc_rtc':
            # day of week is Sunday to Saturday indexed by [bytes[4] - 1]
            bytes = self.get_bytes(dict)
            return '%04u-%02u-%02u %02u:%02u' % (
                bytes[0] * 256 + bytes[1],
                bytes[2], bytes[3],
                bytes[5], bytes[6])
        return '[?' + format + '?]'

    def verify_checksum8(self, dict, verbose = False, fix = False):
        retval = True
        bytes = self.get_bytes(dict)
        offset = self.to_int(dict['start'])
        grouping = dict.get('groupings', len(bytes))
        count = 0
        sum = 0
        for b in bytes:
            if count == grouping - 1:
                checksum = 0xFF - (sum & 0xFF)
                if checksum != b:
                    if verbose:
                        retval = False
                        print("%u bytes at 0x%04X checksum8 0x%02X != 0x%02X"
                            % (grouping, offset - count, checksum, b))
                    if fix:
                        self.nvram[offset] = checksum
                count = sum = 0
            else:
                sum += b
                count += 1
            offset += 1
        return retval

    def verify_all_checksum8(self, verbose = False, fix = False):
        retval = True
        for c in self.nv_json.get('checksum8', []):
            retval &= self.verify_checksum8(c, verbose, fix)
        return retval

    def verify_checksum16(self, dict, verbose = False, fix = False):
        bytes = self.get_bytes(dict)
        # pop last two bytes as stored checksum16
        if self.byteorder == Endian.BIG:
            stored_sum = bytes.pop() + bytes.pop() * 256
        else:
            stored_sum = bytes.pop() * 256 + bytes.pop()
        checksum_offset = self.to_int(dict['start']) + len(bytes)
        calc_sum = 0xFFFF - (sum(bytes) & 0xFFFF)
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
        retval = True
        for c in self.nv_json.get('checksum16', []):
            retval &= self.verify_checksum16(c, verbose, fix)
        return retval

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

    def dump_audit(self, audit, key=None):
        value = self.format(audit)
        if value is None:
            value = audit.get('default', '')
        if key:
            label = key + ' ' + audit['label']
        else:
            label = audit['label']
        print(label + ': ' + value)
    
    def dump(self, checksums=True):
        for section in ['audits', 'adjustments']:
            if section in self.nv_json:
                for group in sorted(self.nv_json[section].keys()):
                    if group.startswith('_'):
                        continue
                    print(group)
                    print('-' * len(group))
                    audit_group = self.nv_json[section][group]
                    if isinstance(audit_group, list):
                        for audit in audit_group:
                            self.dump_audit(audit)
                    elif isinstance(audit_group, dict):
                        for audit_key in sorted(audit_group.keys()):
                            if audit_key.startswith('_'):
                                continue
                            self.dump_audit(audit_group[audit_key], audit_key)
                    else:
                        print("Can't process: ", audit_group)
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

