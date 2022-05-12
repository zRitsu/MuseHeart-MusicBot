#!/bin/bash

trap 'kill $(jobs -pr)' SIGINT SIGTERM EXIT

if [ ! -d "venv" ]; then
  if [ -x "$(command -v py)" ]; then
    py -3 -m venv venv
  else
    python3 -m venv venv
  fi

  if [ ! -d "venv" ]; then
    echo "Pasta venv não foi criada! Verifique se instalou o python corretamente (e que esteja configurado no PATH/env)"
    sleep 45
    exit 1
  fi

  source venv/Scripts/activate
  pip install -r requirements.txt
else
  source venv/Scripts/activate
fi

python main.py

read -p "\n\nPressione ENTER para finalizar..."
