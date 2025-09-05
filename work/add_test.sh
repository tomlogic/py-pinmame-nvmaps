#!/bin/sh

./add_wpc_rom.py --rom "$1"
../nvram_parser.py --dump --map "$1.nv.json" --nvram "../../../pinmame/release/nvram/$1.nv"

