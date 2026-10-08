@echo off
rem  After the openings have been processed by the flow: compares SharePoint with the import files, item/location by item/location.
call "%~dp0_common.cmd" || exit /b %errorlevel%
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -m pou_tools.verify_import %AUTHARGS% --import-dir migration\import --out migration\reconciliation\post_import_quantity_reconciliation.csv
