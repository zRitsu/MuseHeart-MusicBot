#!/bin/bash

if [ ! -d ".git" ]; then
  git init
  git remote add origin https://github.com/zRitsu/disnake-LL-music-bot.git
  git fetch origin
  git checkout -b main -f --track origin/main
fi

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/Scripts/activate
pip install -r ./requirements.txt

if [ ! -f ".env" ] && [ ! -f "config.json" ]; then
  cp .env-example .env
  echo 'Não esqueça de adicionar os tokens necessários no arquivo .env'
fi
