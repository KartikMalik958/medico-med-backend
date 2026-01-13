@echo off
echo Starting Medical Health Assistant Backend...
echo.
echo Activating virtual environment...
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo.
echo Virtual environment activated!
echo.
echo Starting med backend on port 8001...
python main.py
pause

