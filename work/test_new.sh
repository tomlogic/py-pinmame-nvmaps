#!/bin/sh

../nvram_parser.py --dump --map new_maps/$1.map.json --nvram ../../../pinmame/release/nvram/$1.nv
