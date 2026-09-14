@echo off
rem ============================================================================
rem Scheduled task manager (one-click): install / uninstall / status
rem
rem   tools\manage_scheduled_task.bat install     register the every-N-minutes task
rem   tools\manage_scheduled_task.bat status      is it there, and how did it go?
rem   tools\manage_scheduled_task.bat uninstall   unregister (state and ledgers stay)
rem
rem Interval comes from IG_TICK_MINUTES (default 10). The real registration logic
rem lives in tools\scheduled_task.ps1 - this file only forwards, so it can be
rem double-clicked.
rem
rem NOTE: ASCII-only on purpose (cmd.exe reads .bat in the OEM code page).
rem ============================================================================
setlocal EnableExtensions
set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=status"

where powershell >nul 2>nul
if not "%ERRORLEVEL%"=="0" (
  echo FAIL: powershell not found - registering a scheduled task needs PowerShell.
  endlocal & exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scheduled_task.ps1" -Action "%ACTION%"
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%
