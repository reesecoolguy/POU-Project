@echo off
rem  Regenerates flows\ and app\ from the generator sources (only needed if you change schema\ or the generators).
cd /d "%~dp0.."
call "%~dp0config.cmd"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -m pou_flows.build --site-url %SITE_URL% --out flows || exit /b 1
python -m pou_app.build || exit /b 1
python -m pou_tools.docs_gen
python -m pytest -q
