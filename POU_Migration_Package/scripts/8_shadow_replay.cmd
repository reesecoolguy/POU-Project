@echo off
rem  Comparison period (see docs\09_Cutover_and_Rollback.md). The workbook stays LIVE; this replays its recorded movements into a TEST site.
rem    8_shadow_replay.cmd plan     (offline)
rem    8_shadow_replay.cmd replay   (dry run against the TEST site)    8_shadow_replay.cmd replay APPLY
rem    8_shadow_replay.cmd compare
rem  SITE_URL in config.cmd MUST be the TEST site for replay/compare.
call "%~dp0_common.cmd" || exit /b %errorlevel%
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
if "%1"=="" ( echo usage: 8_shadow_replay.cmd plan^|replay^|compare [APPLY] & exit /b 9 )
set FLAG=
if /i "%2"=="APPLY" set FLAG=--apply
python -m pou_tools.shadow_replay %1 --baseline migration\shadow\baseline.json --current migration\shadow\current.json --out migration\shadow %AUTHARGS% %FLAG%
