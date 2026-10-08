@echo off
cd /d "%~dp0.."
py -3 -m venv .venv || exit /b 1
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Done. Run the numbered scripts in order. Each one is a DRY RUN unless you pass APPLY as its first argument.
