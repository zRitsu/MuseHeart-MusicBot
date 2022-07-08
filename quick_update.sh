#!/bin/bash

export PYTHONIOENCODING=utf8

if [ ! -d ".git" ] || [ -z "$(git remote -v)" ]; then
  git init
  git remote add origin https://github.com/zRitsu/disnake-LL-music-bot.git
  git fetch origin
  git checkout -b main -f --track origin/main
else
  git reset --hard
  git pull --allow-unrelated-histories -X theirs
fi
