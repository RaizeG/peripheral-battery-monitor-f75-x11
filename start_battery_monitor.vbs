Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = baseDir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pythonw) Then
    pythonw = baseDir & "\..\aula-f75-battery\.venv\Scripts\pythonw.exe"
End If
If Not fso.FileExists(pythonw) Then
    pythonw = "pythonw.exe"
End If
scriptPath = baseDir & "\peripheral_battery.py"
WshShell.Run """" & pythonw & """ """ & scriptPath & """", 0, False
