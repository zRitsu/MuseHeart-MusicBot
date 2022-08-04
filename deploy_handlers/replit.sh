#!/bin/bash

if [ ! -d "venv" ] || [ ! -f "./venv/.deployed" ]; then
  echo "Inicializando virtual_env..."
  bash quick_update.sh
  rm -rf venv
  python3 -m venv venv
  . venv/bin/activate
  python3 -m pip config unset --user install.use-feature
  python3 -m pip install -U pip poetry
  poetry install
  touch ./venv/.deployed
else
  . venv/bin/activate
fi

[ -z "$VIDEO_PREVIEW" ] || { python3 preview.py; kill "$PPID"; exit 1; }

python3 main.py
