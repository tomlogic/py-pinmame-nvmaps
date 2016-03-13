# Python samples for PinMAME NVRAM Maps

This small project contains some Python code to parse NVRAM (`.nv`)
files from PinMAME, using JSON-based mapping files from the [PinMAME
NVRAM Maps](https://github.com/tomlogic/pinmame-nvram-maps) project.

The project currently includes a Python program (`nvram_parser.py`) that
works as a standalone application to dump a parsed `.nv` file, or as a
class (ParseNVRAM) you can use from other programs.

This project started in October 2015, and should be considered "alpha"
quality.  The JSON file format may change over time, in addition to the
ParseNVRAM class in this project.

## License

This project is licensed under the GNU Lesser General Public License
v3.0 (LGPL).  LGPL requires that derived works be licensed under the
same license, but works that only link to it do not fall under this
restriction.
