chcp 65001
@echo off
cd "%~dp0"
if not exist ".logs\" mkdir .logs
>.logs\start.log (
  py -3 main.py
) 2>&1
