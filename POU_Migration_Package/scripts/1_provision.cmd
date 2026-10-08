@echo off
rem  Creates / verifies the lists, columns, indexes, unique constraints, permission groups and default settings.
rem  DRY RUN by default (reads only). Run with:  1_provision.cmd APPLY   to make the changes. Safe to re-run.
call "%~dp0_common.cmd" || exit /b %errorlevel%
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
set FLAG=
if /i "%1"=="APPLY" set FLAG=--apply
python -m pou_tools.provision %AUTHARGS% --seed-station CAB-01 --report migration\provision_report.json %FLAG%
