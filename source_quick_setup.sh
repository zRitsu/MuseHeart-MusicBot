#!/bin/bash

export PYTHONIOENCODING=utf8

touch "./.logs/setup.log"

pip install -r ./requirements.txt 2>&1 | tee "./.logs/setup.log"

if [ ! -f ".env" ] && [ ! -f "config.json" ]; then
  cp .example.env .env
  echo 'Não esqueça de adicionar os tokens necessários no arquivo .env'
fi
