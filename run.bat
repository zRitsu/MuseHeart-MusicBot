chcp 65001
echo iniciando bot (verifique se ele está online)...
@echo off
cd "%~dp0"
if not exist ".logs\" mkdir .logs
>.logs\run.log (
  where py >nul 2>&1 && py -3 -m venv venv || python3 -m venv venv
  call venv\Scripts\activate.bat
  python main.py
) 2>&1
