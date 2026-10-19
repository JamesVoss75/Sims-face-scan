@echo off
rem Experiment 2 setup: back up saves, build and install the test mod (asks first)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\install_bridge_mod.ps1" %*
echo.
pause
