#!/bin/bash

export PYTHONIOENCODING=utf8

if  [ ! -d ".git" ] || [ -z "$(git remote -v)" ]; then

  git --work-tree=. init

  if [ -z "$SOURCE_REPO" ]; then
    git --work-tree=. remote add origin https://github.com/zRitsu/MuseHeart-MusicBot.git
  else
    git --work-tree=. remote add origin $SOURCE_REPO
  fi
  git --work-tree=. fetch origin
  git --work-tree=. checkout -b main -f --track origin/main
else
  git --work-tree=. reset --hard
  git --work-tree=. pull --allow-unrelated-histories -X theirs
fi
