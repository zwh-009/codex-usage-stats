$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$excludedDirectories = @(
    ".git",
    ".venv",
    "venv",
    "data",
    "node_modules",
    "dist",
    "build",
    "release",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache"
)

$excludedFilePatterns = @(
    "*.pyc",
    "*.pyo",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "*.csv",
    "*.xlsx",
    "*.log",
    "*.zip",
    "*.7z",
    "*.lnk"
)

$sensitivePatterns = @()
$userProfile = [Environment]::GetFolderPath("UserProfile")
if ($userProfile) {
    $sensitivePatterns += [regex]::Escape($userProfile)
}
$userName = [Environment]::UserName
if ($userName) {
    $sensitivePatterns += [regex]::Escape($userName)
}
$sensitivePatterns += [regex]::Escape($root)
$sensitivePatterns += "sk-[A-Za-z0-9_-]{20,}"
$sensitivePatterns += "api[_-]?key\s*[:=]\s*['""][^'""]+['""]"
$sensitivePatterns += "password\s*[:=]\s*['""][^'""]+['""]"
$sensitivePatterns += "secret\s*[:=]\s*['""][^'""]+['""]"

function Test-IsExcludedPath {
    param([string]$Path)

    $rootFull = [System.IO.Path]::GetFullPath($root).TrimEnd("\", "/")
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    if ($pathFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        $relative = $pathFull.Substring($rootFull.Length).TrimStart("\", "/")
    } else {
        $relative = $pathFull
    }
    $segments = $relative -split "[\\/]+"
    foreach ($segment in $segments) {
        if ($excludedDirectories -contains $segment) {
            return $true
        }
    }

    foreach ($pattern in $excludedFilePatterns) {
        if ([System.Management.Automation.WildcardPattern]::new($pattern, "IgnoreCase").IsMatch((Split-Path -Leaf $Path))) {
            return $true
        }
    }

    return $false
}

$files = Get-ChildItem -LiteralPath $root -Recurse -Force -File |
    Where-Object { -not (Test-IsExcludedPath $_.FullName) }

$matches = @()
foreach ($file in $files) {
    try {
        $found = Select-String -LiteralPath $file.FullName -Pattern $sensitivePatterns -CaseSensitive:$false
        if ($found) {
            $matches += $found
        }
    } catch {
        Write-Warning "Skipped unreadable file: $($file.FullName)"
    }
}

if ($matches.Count -gt 0) {
    Write-Host "Potential sensitive content found:" -ForegroundColor Red
    $matches | Select-Object Path, LineNumber, Line | Format-Table -AutoSize
    exit 1
}

Write-Host "Open-source check passed." -ForegroundColor Green
Write-Host "Scanned files: $($files.Count)"
