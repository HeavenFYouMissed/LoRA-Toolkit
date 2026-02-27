@echo off
:: ================================================
::   LoRA Data Toolkit - Quick Launcher
::   Double-click this to run the app.
:: ================================================
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    echo         Run setup.bat first to create it.
    pause
    exit /b 1
)

start "" /B "venv\Scripts\pythonw.exe" main.py
