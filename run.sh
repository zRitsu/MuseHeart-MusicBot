#!/bin/bash

trap 'kill $(jobs -pr)' SIGINT SIGTERM EXIT

if [ ! -d "venv" ]; then
  if [ -x "$(command -v py)" ]; then
    py -3 -m venv venv
  else
    python3 -m venv venv
  fi
  source venv/Scripts/activate
  pip install -r requirements.txt
else
  source venv/Scripts/activate
fi

python main.py

read -p "\n\nPressione ENTER para finalizar..."
