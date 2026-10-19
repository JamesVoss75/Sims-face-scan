@echo off
rem Remove the test mod from the Mods folder
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\uninstall_bridge_mod.ps1" %*
echo.
pause
