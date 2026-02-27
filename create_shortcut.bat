@echo off
:: ================================================
::   Creates a Desktop shortcut for LoRA Data Toolkit
::   Run this once after setup.bat
:: ================================================

set "APP_DIR=%~dp0"
set "SHORTCUT=%USERPROFILE%\Desktop\LoRA Toolkit.lnk"
set "ICON=%APP_DIR%icon.ico"
set "TARGET=%APP_DIR%venv\Scripts\pythonw.exe"
set "ARGS=main.py"
set "WORKDIR=%APP_DIR%"

:: Use PowerShell to create the .lnk shortcut
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$sc = $ws.CreateShortcut('%SHORTCUT%');" ^
  "$sc.TargetPath = '%TARGET%';" ^
  "$sc.Arguments = '%ARGS%';" ^
  "$sc.WorkingDirectory = '%WORKDIR%';" ^
  "$sc.Description = 'LoRA Data Toolkit';" ^
  "if (Test-Path '%ICON%') { $sc.IconLocation = '%ICON%' };" ^
  "$sc.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo [OK] Desktop shortcut created!
    echo      Look for "LoRA Toolkit" on your Desktop.
) else (
    echo [ERROR] Could not create shortcut. Try running as Administrator.
)

echo.
pause
