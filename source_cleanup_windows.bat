@echo off
del /q /f Lavalink.jar

rmdir /q /s "venv" ".java" ".jabba" ".db_cache" "plugins"

echo Arquivos deletados com sucesso!
pause