@echo off
chcp 65001 >nul
call "%~dp0..\common\generate.bat" --config "%~dp0voice.json" %*
exit /b %errorlevel%
