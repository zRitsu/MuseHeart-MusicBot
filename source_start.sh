#!/bin/bash --utf8

export PYTHONIOENCODING=utf8

trap 'kill $(jobs -pr)' SIGINT SIGTERM EXIT

if [[ $OSTYPE == "msys" ]]; then
  VENV_PATH=venv/Scripts/activate
else
  VENV_PATH=venv/bin/activate
fi

if [ ! -d "venv" ]; then
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

  source $VENV_PATH
  pip install -r requirements.txt
else
  source $VENV_PATH
fi

echo "Bot başlatılıyor (Çevrimiçi olup olmadığını kontrol edin)..."

#mkdir -p ./.logs

#touch "./.logs/run.log"

python main.py #2>&1 | tee ./.logs/run.log

sleep 120s
