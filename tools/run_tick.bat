@echo off
rem ============================================================================
rem Infinigrow one-click launcher: version gate -> one tick -> gardener
rem
rem This is the only file the scheduled task runs (see docs/running.md and
rem tools\manage_scheduled_task.bat). It does nothing clever: it calls three
rem existing entry points in order and passes logs/exit codes through faithfully.
rem
rem NOTE: this file is intentionally ASCII-only. cmd.exe reads .bat in the OEM
rem code page (GBK on a Chinese Windows), so UTF-8 Chinese text inside a batch
rem file gets mangled and can break parsing. Human-readable Chinese lives in
rem docs/running.md instead.
rem
rem Exit codes (single source: src/infinigrow/core/exit_codes.py):
rem   0 ok | 2 rules/self-test failed or gardener fatal | 3 upgrade self-test failed
rem   4 strict mode could not get the latest version
rem ============================================================================
setlocal EnableExtensions
set "HERE=%~dp0"
for %%I in ("%HERE%..") do set "REPO=%%~fI"

rem Interpreter: override with IG_PYTHON (default: python from PATH)
set "PY=python"
if not "%IG_PYTHON%"=="" set "PY=%IG_PYTHON%"

rem State root: default <repo>\state ; set IG_STATE_ROOT for multi-instance/read-only
if "%IG_STATE_ROOT%"=="" set "IG_STATE_ROOT=%REPO%\state"
if not exist "%IG_STATE_ROOT%\logs" mkdir "%IG_STATE_ROOT%\logs" >nul 2>nul
set "LOG=%IG_STATE_ROOT%\logs\tick.log"

rem src/ layout: make the package importable for child processes
set "PYTHONPATH=%REPO%\src"

echo [%DATE% %TIME%] tick start (repo=%REPO%)
echo [%DATE% %TIME%] ==== tick start ==== >> "%LOG%"

rem (1) version gate: default to the latest release; if it cannot upgrade, run anyway
"%PY%" "%REPO%\tools\run_latest.py" -- %* >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo [%DATE% %TIME%] tick done rc=%RC%

rem (2) gardener: stale locks / liveness / failure escalation / ledger rotation
rem     (writes state\ALERT.md, the single human-facing alert surface)
"%PY%" -m infinigrow gardener >> "%LOG%" 2>&1
set "GRC=%ERRORLEVEL%"
if not "%GRC%"=="0" set "RC=%GRC%"

echo [%DATE% %TIME%] gardener done rc=%GRC% ; overall rc=%RC% >> "%LOG%"
endlocal & exit /b %RC%
