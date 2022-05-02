chcp 65001
echo instalando/atualizando dependências...
@echo off
cd "%~dp0"
if not exist ".logs\" mkdir .logs
>.logs\setup.log (

  if not exist .git\ (
    git init
    timeout /t 2
    attrib -h -s .git
    git remote add origin https://github.com/zRitsu/disnake-LL-music-bot.git
    git fetch origin
    git checkout -b main -f --track origin/main
  )

  if not exist "venv\" (
    where py >nul 2>&1 && py -3 -m venv venv || python3 -m venv venv
  )

  call venv\Scripts\activate.bat
  pip install -r requirements.txt

  if not exist .env (
    if not exist config.json (
      copy .env-example .env
      echo Não esqueça de adicionar os tokens necessários no arquivo .env
    )
  )

) 2>&1

type .logs\setup.log
pause
