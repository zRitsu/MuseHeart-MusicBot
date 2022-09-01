#!/bin/bash

rm poetry.lock && rm pyproject.toml

[ -z "$VIDEO_PREVIEW" ] || { . venv/bin/activate && python3 preview.py; kill "$PPID"; exit 1; }

if [ ! -d "venv" ] || [ ! -f "./venv/bin/python3" ] || [ ! -f "./venv/requirements.txt" ]; then
  bash quick_update.sh && rm -rf venv && rm -rf .config && rm -rf .cache
  echo "##################################"
  echo "## Inicializando virtual_env... ##"
  echo "##################################"
  python3 -m venv venv
  . venv/bin/activate
  python3 -m pip config unset --user install.use-feature
  python3 -m pip install -U pip
  echo "#################################################"
  echo "## Instalando dependências...                  ##"
  echo "## (Esse processo pode demorar até 5 minutos). ##"
  echo "#################################################"
  pip3 install -U -r requirements.txt --no-cache-dir
  cp -r requirements.txt ./venv/requirements.txt
else
  . venv/bin/activate
  if  ! cmp --silent -- "./requirements.txt" "./venv/requirements.txt"; then
    echo "############################################"
    echo "## Instalando/Atualizando dependências... ##"
    echo "############################################"
    pip3 install -U -r requirements.txt --no-cache-dir
    cp -r requirements.txt ./venv/requirements.txt
  fi
fi

python3 main.py
