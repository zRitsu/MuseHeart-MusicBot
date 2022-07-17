#!/bin/bash

bash quick_update.sh
pip3 install -U -r requirements.txt --force-reinstall
python main.py
