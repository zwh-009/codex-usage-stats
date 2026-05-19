$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$usageTitle = -join @([char]0x7528, [char]0x91CF, [char]0x7EDF, [char]0x8BA1)
$shortcutTitle = "Codex " + $usageTitle
$shortcutPath = Join-Path $desktop ($shortcutTitle + ".lnk")
$launcher = Join-Path $projectRoot "run_app_silent.vbs"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:WINDIR "System32\wscript.exe"
$shortcut.Arguments = '"' + $launcher + '"'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = $shortcutTitle
$shortcut.IconLocation = (Join-Path $env:WINDIR "System32\imageres.dll") + ",109"
$shortcut.Save()

Write-Host "Created desktop shortcut: $shortcutPath"
