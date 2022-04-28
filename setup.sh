#!/bin/bash
if [ ! -d ".git" ]; then
  git init
  git remote add origin https://github.com/zRitsu/disnake-LL-music-bot.git
  git fetch origin
  git checkout -b main -f --track origin/main
fi
python3 -m venv venv
source venv/Scripts/activate
pip install -r ./requirements.txt
