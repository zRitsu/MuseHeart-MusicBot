#!/bin/bash
git reset --hard
git pull --allow-unrelated-histories -X theirs
python3 -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt --force-reinstall
