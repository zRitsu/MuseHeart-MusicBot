#!/bin/bash

rm -rf poetry.lock pyproject.toml .upm
pip uninstall poetry -y

if [ ! "$REPL_SLUG-$REPL_OWNER" == "$(cat ./.deployed)" ]; then
  rm -rf .spotify_cache .config .cache local_database .logs Lavalink.jar application.yml plugins pyproject.toml poetry.lock
  echo -n "$REPL_SLUG-$REPL_OWNER" > ./.deployed
fi

if [ "${SOURCE_AUTO_UPDATE,,}" == "true" ]; then
  bash source_quick_update.sh
fi

python3 main.py
