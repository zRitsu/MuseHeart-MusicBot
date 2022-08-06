#!/bin/bash

[ -z "$VIDEO_PREVIEW" ] || { . venv/bin/activate && python3 preview.py; kill "$PPID"; exit 1; }

if [ ! -d "venv" ] || [ ! -f "./venv/pyproject.toml" ]; then
  bash quick_update.sh
  rm -rf venv
  rm poetry.lock
  echo "Inicializando virtual_env..."
  python3 -m venv venv
  . venv/bin/activate
  python3 -m pip config unset --user install.use-feature
  python3 -m pip install -U pip poetry
  echo "Instalando dependências (isso pode demorar até 5 minutos)..."
  poetry install
  cp -r pyproject.toml ./venv/pyproject.toml
else
  . venv/bin/activate
  if  ! cmp --silent -- "./pyproject.toml" "./venv/pyproject.toml"; then
    echo "Instalando/Atualizando dependências..."
    poetry install
    cp -r pyproject.toml ./venv/pyproject.toml
  fi
fi

python3 main.py
