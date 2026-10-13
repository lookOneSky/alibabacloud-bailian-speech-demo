@echo off
chcp 65001 >nul
call "%~dp0generate.bat" --model qwen-audio-3.0-tts-plus --name "玄岳门_武炎炎_Plus" %*
exit /b %errorlevel%
