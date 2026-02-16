Set WshShell = CreateObject("WScript.Shell")

' Resolve the directory this script lives in
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

' Run run.bat silently (0 = hidden window, False = don't wait)
WshShell.Run Chr(34) & scriptDir & "\run.bat" & Chr(34), 0, False
