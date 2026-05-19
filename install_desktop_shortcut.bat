@echo off
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_desktop_shortcut.ps1"
if errorlevel 1 (
    echo.
    echo Failed to create desktop shortcut.
    pause
    exit /b 1
)

echo.
echo Desktop shortcut created.
timeout /t 2 >nul
