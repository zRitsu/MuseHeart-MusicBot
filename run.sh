#!/bin/bash

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/Scripts/activate
python main.py
