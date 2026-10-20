@echo off
cd /d "%~dp0"
py -3 -m devsweep
if errorlevel 1 pause
