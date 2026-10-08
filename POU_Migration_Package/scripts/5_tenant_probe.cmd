@echo off
rem  Measures the SharePoint behaviours the design depends on, in a throw-away list. Run as a SITE OWNER.
rem  tenant probe: 5_tenant_probe.cmd APPLY            (quick, a few minutes)
rem                5_tenant_probe.cmd APPLY 5100       (also proves the 5,000-item list-view-threshold behaviour; about 30-40 minutes)
call "%~dp0_common.cmd" || exit /b %errorlevel%
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
set FLAG=
if /i "%1"=="APPLY" set FLAG=--apply
set LARGE=
if not "%2"=="" set LARGE=--large %2
python -m pou_tools.tenant_probe %AUTHARGS% --report migration\tenant_probe_report.json %FLAG% %LARGE%
