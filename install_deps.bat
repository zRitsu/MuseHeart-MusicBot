chcp 65001
@echo off
cd "%~dp0"
if not exist "logs\" mkdir logs
>logs\install_deps.log (
  py -3 -m pip install -r requirements.txt --force-reinstall
) 2>&1

type logs\install_deps.log
pause
