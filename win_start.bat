@echo off
chcp 65001 >NUL
echo iniciando bot (verifique se ele está online)...
@echo off
cd "%~dp0"
if not exist ".logs\" mkdir .logs

if not exist "venv\" (
  where py >nul 2>&1 && py -3 -m venv venv || python3 -m venv venv
)

call venv\Scripts\activate.bat
@echo on
python main.py 2> .logs\run.log
type .logs\run.log
@echo off
timeout /t 30