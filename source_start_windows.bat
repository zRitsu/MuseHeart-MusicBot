@echo off
set errorlevel=0

set python_cmd=py -3

python3 --version >nul 2>nul
if not errorlevel 1 (
    set python_cmd=python3
)

if not exist venv (
    %python_cmd% -m venv venv
    call "venv\Scripts\activate"
    pip install -r requirements.txt
) else (
    call "venv\Scripts\activate"
)

python main.py
pause
