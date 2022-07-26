#!/bin/bash

[ -z "$IS_SOURCE" ] || { python3 preview.py; kill "$PPID"; exit 1; }

if [ ! -d "venv" ] || [ ! -f "venv/bin/python310" ]; then
  bash quick_update.sh
  rm -rf venv
  python3 -m venv venv
  . venv/bin/activate
  python3 -m pip config unset --user install.use-feature
  python3 -m pip install -U pip
  python3 -m pip install -r requirements.txt
  clear
else
  . venv/bin/activate
fi

python3 main.py
