@echo off
rem Experiment 2 results: read-only check of the validation records and newest save
rem Runs Windows PowerShell by its full system path (not a powershell.exe found via the
rem current folder or PATH). -ExecutionPolicy Bypass applies to this one process only; it
rem does not change your machine or user policy.
setlocal
set "FACESCAN_PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%FACESCAN_PS%" set "FACESCAN_PS=powershell.exe"
"%FACESCAN_PS%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\check_experiment2.ps1" %*
set "FACESCAN_RC=%ERRORLEVEL%"
echo.
pause
exit /b %FACESCAN_RC%
