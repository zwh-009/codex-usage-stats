@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating local Python environment...
    python -m venv .venv
)

echo Installing Python dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt

if not exist "frontend\node_modules" (
    echo Installing frontend dependencies...
    call npm --prefix frontend install
)

echo Building frontend...
call npm --prefix frontend run build

set "PYTHONPATH=%~dp0src"
if not exist "data" mkdir "data"
set "CODEX_USAGE_LOG_FILE=%~dp0data\desktop-debug.log"
echo Starting Codex usage tool in debug mode.
echo Keep this window open while using the app.
echo.
".venv\Scripts\python.exe" -m codex_usage_tool
pause
