#!/bin/bash

[ -z "$VIDEO_PREVIEW" ] || { . venv/bin/activate && python3 preview.py; kill "$PPID"; exit 1; }

if [ ! -d "venv" ] || [ ! -f "./venv/.deployed" ]; then
  bash quick_update.sh
  rm -rf venv
    echo "Inicializando virtual_env..."
  python3 -m venv venv
  . venv/bin/activate
  python3 -m pip config unset --user install.use-feature
  python3 -m pip install -U pip poetry
  touch ./venv/.deployed
else
  . venv/bin/activate
fi

poetry install
python3 main.py
