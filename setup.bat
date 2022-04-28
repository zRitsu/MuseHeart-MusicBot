chcp 65001
echo instalando/atualizando dependências...
@echo off
cd "%~dp0"
if not exist ".logs\" mkdir .logs
>.logs\setup.log (
  if not exist .git\ (
    git init
    attrib -h .git/
    git remote add origin https://github.com/zRitsu/disnake-LL-music-bot.git
    git fetch origin
    git checkout -b main -f --track origin/main
  )
  py -3 -m venv venv
  call venv\Scripts\activate.bat
  pip install -r requirements.txt
) 2>&1

type .logs\setup.log
pause
