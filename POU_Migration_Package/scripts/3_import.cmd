@echo off
rem  Imports the generated files into SharePoint. DRY RUN by default; add APPLY to write.
rem  Stages: locations, employees, items, stock, ledger (legacy history), openings (OPENING requests, which the flow posts).
rem  Pass a stage list as the 2nd argument to run only some, e.g.:  3_import.cmd APPLY locations,employees,items,stock
call "%~dp0_common.cmd" || exit /b %errorlevel%
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
set FLAG=
if /i "%1"=="APPLY" set FLAG=--apply
set STAGES=locations,employees,items,stock,ledger,openings
if not "%2"=="" set STAGES=%2
python -m pou_tools.import_data %AUTHARGS% --import-dir migration\import --stages %STAGES% --report migration\import_report.json %FLAG%
