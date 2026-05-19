@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating local Python environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create local virtual environment.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\pythonw.exe" (
    echo Local Python environment is incomplete.
    pause
    exit /b 1
)

echo Installing Python dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install local Python dependencies.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo Installing frontend dependencies...
    call npm --prefix frontend install
    if errorlevel 1 (
        echo Failed to install local frontend dependencies.
        pause
        exit /b 1
    )
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$dist='frontend\dist\index.html'; $need=!(Test-Path $dist); if(-not $need){ $distTime=(Get-Item $dist).LastWriteTime; $items=Get-ChildItem 'frontend\src','frontend\index.html','frontend\package.json','frontend\vite.config.ts','frontend\tsconfig.json' -Recurse -ErrorAction SilentlyContinue; $srcTime=($items | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime; if($srcTime -gt $distTime){ $need=$true } }; if($need){ exit 1 } else { exit 0 }"
if errorlevel 1 (
    echo Building frontend...
    call npm --prefix frontend run build
    if errorlevel 1 (
        echo Failed to build frontend.
        pause
        exit /b 1
    )
) else (
    echo Frontend build is up to date.
)

set "PYTHONPATH=%~dp0src"
if not exist "data" mkdir "data"
set "CODEX_USAGE_LOG_FILE=%~dp0data\desktop-run.log"
echo Starting Codex usage tool...
start "" ".venv\Scripts\pythonw.exe" -m codex_usage_tool
exit /b 0
