chcp 65001
echo atualizando bot...
cd "%~dp0"
@echo off
if not exist ".logs\" mkdir .logs
>.logs\update.log (
  git reset --hard && git pull --allow-unrelated-histories -X theirs && pip3 install -r requirements.txt --force-reinstall
) 2>&1

type .logs\update.log
pause
