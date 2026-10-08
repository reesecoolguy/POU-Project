@echo off
call "%~dp0config.cmd"
cd /d "%~dp0.."
where py >nul 2>nul
if errorlevel 1 ( echo Python launcher 'py' not found. Install Python 3.10+ from python.org ^(tick "Add python.exe to PATH" and "py launcher"^). & exit /b 9 )
echo %SITE_URL% | findstr /i "CHANGE-ME" >nul
if not errorlevel 1 ( echo Edit scripts\config.cmd first: SITE_URL still contains CHANGE-ME. & exit /b 9 )
set AUTHARGS=--site-url %SITE_URL% --tenant %TENANT% --client-id %CLIENT_ID%
