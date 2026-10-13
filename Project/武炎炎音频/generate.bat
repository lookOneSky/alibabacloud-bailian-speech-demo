@echo off
chcp 65001 >nul
setlocal
set "VOICE_PYTHON=%~dp0..\..\.venv\Scripts\python.exe"
if not exist "%VOICE_PYTHON%" (
    echo 请先配置项目根目录的 .venv 和 requirements-local.txt 中的依赖。
    pause
    exit /b 1
)
"%VOICE_PYTHON%" "%~dp0generate_voice.py" %*
set "VOICE_EXIT_CODE=%errorlevel%"
if not "%VOICE_EXIT_CODE%"=="0" pause
exit /b %VOICE_EXIT_CODE%
