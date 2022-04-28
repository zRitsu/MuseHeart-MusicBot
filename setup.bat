chcp 65001
echo instalando/atualizando dependências...
@echo off
cd "%~dp0"
if not exist ".logs\" mkdir .logs
>.logs\setup.log (
  py -3 -m venv venv
  call venv\Scripts\activate.bat
  pip install -r requirements.txt
) 2>&1

type .logs\install_deps.log
pause
