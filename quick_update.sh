#!/bin/bash

export PYTHONIOENCODING=utf8

if [ ! -d ".git" ] || [ -z "$(git remote -v)" ]; then
  git init
  if [ -z "$SOURCE_REPO" ]; then
    git remote add origin $SOURCE_REPO
  else
    git remote add origin https://github.com/zRitsu/disnake-LL-music-bot.git
  fi
  git fetch origin
  git checkout -b main -f --track origin/main
else
  git reset --hard
  git pull --allow-unrelated-histories -X theirs
fi
