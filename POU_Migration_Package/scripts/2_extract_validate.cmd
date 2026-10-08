@echo off
rem  Reads the workbook (never runs its macros), validates it and (re)generates migration\import\*.csv, the exception report and the reconciliation.
rem  Works offline; needs no sign-in.
cd /d "%~dp0.."
call "%~dp0config.cmd"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -m pou_tools.extract "%WORKBOOK%" --out migration\source_extract\extract.json || exit /b 1
python -m pou_tools.transform --extract migration\source_extract\extract.json --out migration || exit /b 1
echo.
echo Open migration\RUN_SUMMARY.md and migration\exceptions\exceptions.csv and read them BEFORE importing.
