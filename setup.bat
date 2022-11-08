chcp 65001
echo instalando/atualizando dependências...
@echo off
cd "%~dp0"
if not exist ".logs\" mkdir .logs
>.logs\setup.log (

  rmdir /Q /S venv
  call venv\Scripts\activate.bat
  pip install -r requirements.txt

  if not exist .env (
    if not exist config.json (
      copy example.env .env
      echo Não esqueça de adicionar os tokens necessários no arquivo .env
    )
  )

) 2>&1

type .logs\setup.log
pause
