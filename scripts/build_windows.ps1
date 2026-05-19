$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$releaseRoot = Join-Path $root "release"
$packageRoot = Join-Path $releaseRoot "CodexUsageTool_$timestamp"
$distPath = Join-Path $packageRoot "dist"
$workPath = Join-Path $packageRoot "pyinstaller-work"
$specPath = Join-Path $packageRoot "pyinstaller-spec"
$friendlyZipName = "直接解压本压缩包即可使用-无脑使用版.zip"
$zipPath = Join-Path $packageRoot $friendlyZipName
$publicZipPath = Join-Path $releaseRoot $friendlyZipName
$releaseDirectoriesToKeep = 2
$appName = "CodexUsageTool"
$python = Join-Path $root ".venv\Scripts\python.exe"
$frontendDist = Join-Path $root "frontend\dist"
$entry = Join-Path $root "src\codex_usage_tool\__main__.py"
$iconPath = Join-Path $root "assets\app_icon.ico"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Command
}

function Compress-ReleasePackage {
    param(
        [string]$SourceDirectory,
        [string]$DestinationPath
    )

    $lastError = $null
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            if (Test-Path $DestinationPath) {
                Remove-Item -LiteralPath $DestinationPath -Force
            }
            Compress-Archive -Path (Join-Path $SourceDirectory "*") -DestinationPath $DestinationPath -Force
            return
        } catch {
            $lastError = $_
            Start-Sleep -Seconds 2
        }
    }
    throw $lastError
}

function Remove-OldReleaseDirectories {
    param(
        [string]$ReleaseDirectory,
        [int]$Keep
    )

    $releaseFullPath = [System.IO.Path]::GetFullPath($ReleaseDirectory).TrimEnd("\", "/")
    $oldDirectories = Get-ChildItem -LiteralPath $ReleaseDirectory -Directory -Force |
        Where-Object { $_.Name -like "CodexUsageTool_*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $Keep

    foreach ($directory in $oldDirectories) {
        $directoryFullPath = [System.IO.Path]::GetFullPath($directory.FullName).TrimEnd("\", "/")
        if (-not $directoryFullPath.StartsWith($releaseFullPath + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove path outside release directory: $directoryFullPath"
        }
        Remove-Item -LiteralPath $directoryFullPath -Recurse -Force
    }
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm not found. Install Node.js LTS before building the Windows package."
}

if (-not (Test-Path $python)) {
    Invoke-Step "Create local Python environment" {
        python -m venv (Join-Path $root ".venv")
    }
}

New-Item -ItemType Directory -Force -Path $packageRoot, $distPath, $workPath, $specPath | Out-Null

Invoke-Step "Install Python runtime dependencies" {
    & $python -m pip install -r (Join-Path $root "requirements.txt")
}

Invoke-Step "Install Python build dependencies" {
    & $python -m pip install -r (Join-Path $root "requirements-build.txt")
}

Invoke-Step "Install frontend dependencies" {
    if (Test-Path (Join-Path $root "frontend\package-lock.json")) {
        npm --prefix (Join-Path $root "frontend") install
    } else {
        npm --prefix (Join-Path $root "frontend") install
    }
}

Invoke-Step "Build frontend" {
    npm --prefix (Join-Path $root "frontend") run build
}

Invoke-Step "Run tests" {
    & $python -m compileall (Join-Path $root "src") (Join-Path $root "tests")
    & $python -m unittest discover -s (Join-Path $root "tests")
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "open_source_check.ps1")
}

if (-not (Test-Path (Join-Path $frontendDist "index.html"))) {
    throw "Frontend build output is missing: $frontendDist"
}
if (-not (Test-Path $iconPath)) {
    throw "Application icon is missing: $iconPath"
}

$addData = "$frontendDist;frontend\dist"
$addIconAssets = "$(Join-Path $root "assets");assets"
$hiddenImports = @(
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.lifespan.on"
)

$pyinstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--windowed",
    "--name", $appName,
    "--distpath", $distPath,
    "--workpath", $workPath,
    "--specpath", $specPath,
    "--paths", (Join-Path $root "src"),
    "--add-data", $addData,
    "--add-data", $addIconAssets,
    "--icon", $iconPath
)

foreach ($hiddenImport in $hiddenImports) {
    $pyinstallerArgs += @("--hidden-import", $hiddenImport)
}

$pyinstallerArgs += $entry

Invoke-Step "Build Windows executable" {
    & $python @pyinstallerArgs
}

$appDir = Join-Path $distPath $appName
$exePath = Join-Path $appDir "$appName.exe"
if (-not (Test-Path $exePath)) {
    throw "Build completed but executable was not found: $exePath"
}

Copy-Item -LiteralPath (Join-Path $root "README.md") -Destination (Join-Path $appDir "README.md") -Force
Copy-Item -LiteralPath (Join-Path $root "LICENSE") -Destination (Join-Path $appDir "LICENSE") -Force

$quickStart = @(
    "Codex Usage Tool",
    "",
    "Usage:",
    "1. Double-click CodexUsageTool.exe.",
    "2. The app scans the current Windows user's Codex logs.",
    "3. Close or minimize sends the app to the system tray.",
    "4. Right-click the tray icon to open the main window, show the widget, or quit.",
    "",
    "Local data directory:",
    "%LOCALAPPDATA%\CodexUsageTool",
    "",
    "The app does not upload logs and does not read .codex\auth.json."
) -join [Environment]::NewLine
$quickStart | Set-Content -Path (Join-Path $appDir "README_RELEASE.txt") -Encoding UTF8

Invoke-Step "Create release zip" {
    Compress-ReleasePackage -SourceDirectory $appDir -DestinationPath $zipPath
    Copy-Item -LiteralPath $zipPath -Destination $publicZipPath -Force
}

Invoke-Step "Clean old release directories" {
    Remove-OldReleaseDirectories -ReleaseDirectory $releaseRoot -Keep $releaseDirectoriesToKeep
}

Write-Host ""
Write-Host "Build finished." -ForegroundColor Green
Write-Host "App directory: $appDir"
Write-Host "Zip package: $zipPath"
Write-Host "User-facing zip package: $publicZipPath"
