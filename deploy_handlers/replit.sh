#!/bin/bash

rm -rf poetry.lock pyproject.toml .upm
pip3 uninstall poetry -y

if [ ! "$REPL_SLUG-$REPL_OWNER" == "$(cat ./venv/.deployed)" ]; then
  rm -rf venv .config .cache local_database .logs Lavalink.jar application.yml plugins pyproject.toml poetry.lock
  echo -n "$REPL_SLUG-$REPL_OWNER" > ./.deployed
fi

if [ "${SOURCE_AUTO_UPDATE,,}" == "true" ]; then
  bash source_quick_update.sh
fi

python3 main.py
