#!/bin/bash

bash quick_update.sh
pip3 install -U -r requirements.txt --no-cache-dir
python main.py
