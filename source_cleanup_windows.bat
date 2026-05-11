@echo off
del /q /f "local_audio\Lavalink.jar"

rmdir /q /s "venv" ".app_commands_sync_data" ".java" ".jabba" ".db_cache" "local_audio\plugins"

echo Arquivos deletados com sucesso!
pause
