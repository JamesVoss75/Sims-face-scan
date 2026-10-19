@echo off
rem Experiment 2 results: read-only check of the validation records and newest save
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\check_experiment2.ps1" %*
echo.
pause
