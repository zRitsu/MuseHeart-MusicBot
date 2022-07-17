#!/bin/bash

if [ "${SOURCE_AUTO_UPDATE,,}" == "true" ]; then
  bash ./deploy_handlers/heroku_auto_update.sh
else
  python3 main.py
fi
