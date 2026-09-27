@echo off
chcp 65001 >nul 2>&1
title ASCII Art Player

echo ================================
echo      ASCII Art Player v5
echo ================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    echo Please install Python from https://www.python.org
    pause
    exit /b 1
)

:: Install dependencies
echo Installing dependencies...
pip install -r "%~dp0requirements.txt" -q

echo.
echo Launching ASCII Art Player...
echo.

:: Run the player
python "%~dp0ascii_player.py" %*

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Player exited with error code %errorlevel%
    pause
)
