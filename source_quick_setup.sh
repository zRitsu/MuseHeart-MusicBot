#!/bin/bash

export PYTHONIOENCODING=utf8

touch "./.logs/setup.log"

pip install -r ./requirements.txt 2>&1 | tee "./.logs/setup.log"

if [ ! -f ".env" ] && [ ! -f "config.json" ]; then
  cp .example.env .env
  echo '.env dosyasına gerekli jetonları eklemeyi unutmayın'
fi
