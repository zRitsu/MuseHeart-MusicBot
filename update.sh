#!/bin/bash
git reset --hard
git pull --allow-unrelated-histories -X theirs

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/Scripts/activate
pip install -r requirements.txt --force-reinstall
