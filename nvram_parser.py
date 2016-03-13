#!/usr/bin/python

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

# Helper class to track whether multi-byte values in nvram file are big-endian
# (MSB-first) or little-endian (LSB-first).  6809 (WPC) is big-endian.
class Endian:
    LITTLE = 1234
    BIG = 4321

class ParseNVRAM(object):
	def __init__(self, nv_json, nvram):
		self.nv_json = nv_json
		self.nvram = nvram
		self.byteorder = Endian.BIG  # default setting
	
	def load_json(self, json_path):
		json_fh = open(json_path, 'r')
		self.nv_json = json.load(json_fh)
		json_fh.close()
		if (self.nv_json.has_key('_endian') and
			self.nv_json['_endian'] == 'little'):
				self.byteorder = Endian.LITTLE
		
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
		
	# return 'start' to 'end' bytes (inclusive) from 'self.nvram', or
	# 'start' to 'start + length - 1' bytes (inclusive)
	# or the single byte at 'start' if 'end' and 'length' are not specified
	def get_bytes(self, dict):
		start = 0
		if dict.has_key('start'):
			start = self.to_int(dict['start'])
		end = start
		if dict.has_key('length'):
			length = self.to_int(dict['length'])
			if length <= 0:
				raise AssertionError('invalid length (%s); must be > 0'
					% (dict['length']))
			end = start + length - 1
		elif dict.has_key('end'):
			end = self.to_int(dict['end'])
			if end < start:
				raise AssertionError('end (%s) is less than start (%s)'
					% (dict['end'], dict['start']))
		
		return self.nvram[start:end + 1]
	
	# Return an integer value from one or more bytes in memory
	# handles multi-byte integers (int), binary coded decimal (bcd) and
	# single-byte enumerated (enum) values.  Returns None for unsupported
	# encodings.
	def get_value(self, dict):
		value = None
		if dict.has_key('encoding'):
			format = dict['encoding']
			bytes = self.get_bytes(dict)
			if self.byteorder == Endian.BIG:
				byte_iter = iter(bytes)
			else:
				byte_iter = bytes.reversed()
			
			if format == 'bcd':
				value = 0
				for b in byte_iter:
					value = value * 100 + (b >> 4) * 10 + (b & 0x0F)
			elif format == 'int':
				value = 0
				for b in byte_iter:
					value = value * 256 + b
			elif format == 'enum':
				value = bytes[0]
					
			if value is not None:
				if dict.has_key('scale'):
					value *= self.to_int(dict['scale'])
				if dict.has_key('offset'):
					value += self.to_int(dict['offset'])
		
		return value
	
	# replace a value stored in self.nvram[]
	def set_value(self, dict, value):
		format = dict['encoding']
		old_bytes = self.get_bytes(dict);
		start = self.to_int(dict['start'])
		end = start + len(old_bytes)
		# can now replace self.nvram[start:end]
		new_bytes = []
		
		if format == 'bcd':
			for x in old_bytes:
				b = value % 100
				new_bytes.append(b % 10 + 16 * (b / 10))
				value /= 100
			if self.byteorder == Endian.BIG:
				new_bytes = reversed(new_bytes)
		elif format == 'int' or format == 'enum':
			for x in old_bytes:
				b = value % 256
				new_bytes.append(b)
				value /= 256
			if self.byteorder == Endian.BIG:
				new_bytes = reversed(new_bytes)
		elif format == 'ch':
			assert type(value) is str and len(value) == len(old_bytes)
			new_bytes = list(value)
			
		self.nvram[start:end] = bytearray(new_bytes)
	
	# format a multi-byte integer using options in 'dict'
	def format_value(self, dict, value):
		# `special_values` contains strings to use in place of `value`
		# commonly used at the low end of a range for off/disabled
		if dict.has_key('special_values'):
			if dict['special_values'].has_key(str(value)):
				return dict['special_values'][str(value)]
		
		if dict.has_key('units'):
			if dict['units'] == 'seconds':
				m, s = divmod(value, 60)
				h, m = divmod(m, 60)
				return "%d:%02d:%02d" % (h, m, s)
			elif dict['units'] == 'minutes':
				return "%d:%02d:00" % divmod(value, 60)
		suffix = ''
		if dict.has_key('suffix'):
			suffix = dict['suffix']
		return self.format_score(value) + suffix
	
	# format bytes from 'nvram' depending on members of 'dict'
	# uses 'encoding' to specify format
	# 'start' and either 'end' or 'length' for range of bytes
	def format(self, dict):
		if not dict.has_key('encoding'):
			return None
		format = dict['encoding']
		value = self.get_value(dict)
		if format == 'bcd' or format == 'int':
			return self.format_value(dict, value)
		elif format == 'enum':
			values = dict['values']
			if value > len(values):
				return '?' + str(value)
			return values[value]
		if format == 'ch':
			return str(self.get_bytes(dict))
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
		grouping = len(bytes)
		if dict.has_key('groupings'):
			grouping = dict['groupings']
		count = 0
		sum = 0
		for b in bytes:
			if count == grouping - 1:
				checksum = 0xFF - (sum & 0xFF)
				if checksum != b:
					if verbose:
						retval = False
						print ("%u bytes at 0x%04X checksum8 0x%02X != 0x%02X"
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
		if self.nv_json.has_key('checksum8'):
			for c in self.nv_json['checksum8']:
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
				print "checksum16 at %s: 0x%04X != 0x%04X" % (dict['start'],
					calc_sum, stored_sum)
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
		if self.nv_json.has_key('checksum16'):
			for c in self.nv_json['checksum16']:
				retval &= self.verify_checksum16(c, verbose, fix)
		return retval
	
	def last_game_scores(self):
		scores = []
		if self.nv_json.has_key('last_game'):
			for p in self.nv_json['last_game']:
				s = self.format(p)
				if s != '0':
					scores.append(s)
		return scores
	
	# section should be 'high_scores' or 'mode_champions'
	def high_scores(self, section = 'high_scores', short_labels = False):
		scores = []
		for score in self.nv_json[section]:
			label = score['label']
			if short_labels and score.has_key('short_label'):
				label = score['short_label']
			initials = self.format(score['initials'])
			# ignore scores with blank initials
			if initials != '   ':
				if score.has_key('score'):
					scores.append('%s: %s %s' % (label, initials,
						self.format(score['score'])))
				else:
					scores.append('%s: %s' % (label, initials))
		return scores
	
	def last_played(self):
		if not self.nv_json.has_key('last_played'):
			return None
		return self.format(self.nv_json['last_played'])

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
	
	for section in ['audits', 'adjustments']:
		if p.nv_json.has_key(section):
			for group in sorted(p.nv_json[section].keys()):
				print group
				print '-' * len(group)
				audit_group = p.nv_json[section][group]
				for audit in sorted(audit_group.keys()):
					dict = audit_group[audit]
					print audit + ' ' + dict['label'] + ': ' + p.format(dict)
				print
	
	for section in ['high_scores', 'mode_champions']:
		if p.nv_json.has_key(section):
			for score in p.high_scores(section, short_labels = True):
				print score
	
	print
	print "---Last Game---"
	if p.nv_json.has_key('last_played'):
		print p.format(p.nv_json['last_played'])
	for s in p.last_game_scores():
		print s
	
	# Verify all checksums in the file.  Note that we can eventually re-use
	# that part of the memory map to update checksums if modifying nvram values.
	p.verify_all_checksum16(verbose = False)
	p.verify_all_checksum8(verbose = False)	
	
if __name__ == '__main__': main()

