@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0local_app.py" --open-browser
if errorlevel 1 pause
