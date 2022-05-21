#!/bin/bash

trap 'kill $(jobs -pr)' SIGINT SIGTERM EXIT

if [ ! -d ".git" ] || [ -z "$(git remote -v)" ]; then
  git init
  git remote add origin https://github.com/zRitsu/disnake-LL-music-bot.git
  git fetch origin
  git checkout -b main -f --track origin/main
fi

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

fi

source venv/Scripts/activate
pip install -r ./requirements.txt

if [ ! -f ".env" ] && [ ! -f "config.json" ]; then
  cp .env-example .env
  echo 'Não esqueça de adicionar os tokens necessários no arquivo .env'
fi

read -p "Pressione ENTER para finalizar..."
