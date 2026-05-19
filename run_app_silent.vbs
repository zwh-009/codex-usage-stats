Option Explicit

Dim fso
Dim shell
Dim projectRoot
Dim launcher

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

projectRoot = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = fso.BuildPath(projectRoot, "run_app.bat")

shell.CurrentDirectory = projectRoot
shell.Run """" & launcher & """", 0, False
