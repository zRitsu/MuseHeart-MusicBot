#!/bin/bash

if [ -n "${VIDEO_PREVIEW}" ]; then
  . venv/bin/activate
  python3 -m pip install tornado
  python3 preview.py
  kill "$PPID"
  exit 1
fi

if [ ! -d "venv" ] || [ ! -f "./venv/requirements.txt" ]; then
  rm -rf venv && rm -rf .config && rm -rf .cache
  bash quick_update.sh
  echo "##################################"
  echo "## Inicializando virtual_env... ##"
  echo "##################################"
  python3 -m venv venv
  . venv/bin/activate
  python3 -m pip install -U pip
  echo "#################################################"
  echo "## Instalando dependências...                  ##"
  echo "## (Esse processo pode demorar até 3 minutos). ##"
  echo "#################################################"
  pip3 install -U -r requirements.txt --no-cache-dir
  cp -r requirements.txt ./venv/requirements.txt

elif ! cmp --silent -- "./requirements.txt" "./venv/requirements.txt"; then
  echo "############################################"
  echo "## Instalando/Atualizando dependências... ##"
  echo "############################################"
  pip3 install -U -r requirements.txt --no-cache-dir
  cp -r requirements.txt ./venv/requirements.txt

else
  . venv/bin/activate

fi

rm -f poetry.lock && rm -f pyproject.toml

python3 main.py
