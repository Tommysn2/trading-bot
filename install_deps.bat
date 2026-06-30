@echo off
echo === Trading Bot — Install Python Dependencies ===
echo.

REM Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org then re-run this.
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

cd /d "%~dp0"
echo Installing dependencies from requirements.txt...
echo.

pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Some packages failed to install.
    echo Try running: pip install -r requirements.txt --upgrade
) else (
    echo.
    echo SUCCESS! All dependencies installed.
    echo.
    echo Next steps:
    echo  1. Fill in ALPACA and TELEGRAM values in .env
    echo  2. Run: python test_connections.py
)

echo.
pause
