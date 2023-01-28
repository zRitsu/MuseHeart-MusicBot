#!/bin/bash

rm -f poetry.lock && rm -f pyproject.toml
pip3 uninstall poetry -y

if [ -n "${VIDEO_PREVIEW}" ]; then
  if [ ! -d "venv" ]; then
    python3 -m venv venv
  fi
  . venv/bin/activate
  pip3 install tornado
  python3 preview.py
  kill "$PPID"
  exit 1
fi

deployed=$(grep -Fxqs "$REPL_SLUG-$REPL_OWNER" ./venv/.deployed)

if [ ! -d "venv" ] || [ ! -f "./venv/bin/requirements.txt" ] || [ -z $deployed ]; then
  rm -rf venv && rm -rf .config && rm -rf .cache && rm -rf .git
  bash quick_update.sh
  rm -f poetry.lock && rm -f pyproject.toml
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
  cp -r requirements.txt ./venv/bin/requirements.txt
  echo "$REPL_SLUG-$REPL_OWNER" > ./venv/.deployed

elif ! cmp --silent -- "./requirements.txt" "./venv/bin/requirements.txt"; then
  echo "############################################"
  echo "## Instalando/Atualizando dependências... ##"
  echo "############################################"
  . venv/bin/activate
  pip3 install -U -r requirements.txt --no-cache-dir
  cp -r requirements.txt ./venv/bin/requirements.txt

else
  . venv/bin/activate

fi

python3 main.py
