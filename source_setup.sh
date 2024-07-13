#!/bin/bash

export PYTHONIOENCODING=utf8

trap 'kill $(jobs -pr)' SIGINT SIGTERM EXIT

echo "VENV oluşturuluyor (lütfen bekleyin...)"

rm -rf venv

if [ -x "$(command -v py)" ]; then
  py -3 -m venv venv
else
  python3 -m venv venv
fi

if [ ! -d "venv" ]; then
  echo "Venv klasörü oluşturulmadı! Python'u doğru yüklediğinizden (ve PATH/env'de yapılandırıldığından) emin olun."
  sleep 45
  exit 1
fi

if [[ $OSTYPE == "msys" ]]; then
  VENV_PATH=venv/Scripts/activate
else
  VENV_PATH=venv/bin/activate
fi

source $VENV_PATH

mkdir -p ./.logs

touch "./.logs/setup.log"

python -m pip install -U pip

pip install -r ./requirements.txt 2>&1 | tee "./.logs/setup.log"

pip install setuptools>=70.0.0

if [ ! -f ".env" ] && [ ! -f "config.json" ]; then
  cp .example.env .env
  echo '.env dosyasına gerekli jetonları eklemeyi unutmayın'
fi

sleep 60s
