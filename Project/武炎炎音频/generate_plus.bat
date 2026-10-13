@echo off
chcp 65001 >nul
call "%~dp0generate.bat" --variant plus %*
exit /b %errorlevel%
