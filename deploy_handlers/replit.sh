#!/bin/bash

if [ -n "${VIDEO_PREVIEW}" ]; then
  . venv/bin/activate
  python3 -m pip install tornado
  python3 preview.py
  kill "$PPID"
  exit 1
fi

if [ ! -d "venv" ] || [ ! -f "./venv/bin/.venv_created" ]; then
  rm -rf venv && rm -rf .config && rm -rf .cache
  echo "##################################"
  echo "## Inicializando virtual_env... ##"
  echo "##################################"
  python3 -m venv venv
  . venv/bin/activate
  python3 -m pip config unset --user install.use-feature 2> /dev/null
  touch ./venv/bin/.venv_created
else
  . venv/bin/activate
fi

if [ ! -f "./venv/requirements.txt" ]; then
  bash quick_update.sh
  python3 -m pip install -U pip
  echo "#################################################"
  echo "## Instalando dependências...                  ##"
  echo "## (Esse processo pode demorar até 5 minutos). ##"
  echo "#################################################"
  pip3 install -U -r requirements.txt --no-cache-dir
  cp -r requirements.txt ./venv/requirements.txt
elif ! cmp --silent -- "./requirements.txt" "./venv/requirements.txt"; then
  echo "############################################"
  echo "## Instalando/Atualizando dependências... ##"
  echo "############################################"
  pip3 install -U -r requirements.txt --no-cache-dir
  cp -r requirements.txt ./venv/requirements.txt
fi
rm poetry.lock 2>&1 /dev/null
rm pyproject.toml 2>&1 /dev/null

python3 main.py
