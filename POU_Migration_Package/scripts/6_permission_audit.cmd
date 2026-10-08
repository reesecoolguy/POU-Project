@echo off
rem  Run this once signed in AS each kind of test account:  6_permission_audit.cmd operators | supervisors | admins | flowservice
rem  (when the sign-in page opens, choose the TEST account, not your own). Read-only.
call "%~dp0_common.cmd" || exit /b %errorlevel%
if "%1"=="" ( echo usage: 6_permission_audit.cmd operators^|supervisors^|admins^|flowservice & exit /b 9 )
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -m pou_tools.permission_audit %AUTHARGS% --as %1
