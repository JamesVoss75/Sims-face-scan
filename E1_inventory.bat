@echo off
rem Experiment 1: read-only inventory of the game's face data + codec check on your saves
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\run_experiment1.ps1" %*
echo.
pause
