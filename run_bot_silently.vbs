' VBScript to activate a Python virtual environment and run a script with arguments in a hidden window.
Set objArgs = WScript.Arguments

If objArgs.Count < 3 Then
    ' Expects 3 arguments: 
    ' 1. Path to the project root
    ' 2. Path to the Python script to run (relative to project root)
    ' 3. The config name for the Python script
    WScript.Quit
End If

' Build the full command string for cmd.exe
' Example: cmd.exe /c ""d:\path\to\project\ta_env\Scripts\activate.bat" && python "d:\path\to\project\production\run_live.py" "xauusd_prod""
Dim projectPath, pythonScript, configName, activatePath, fullPythonPath, command
projectPath = objArgs(0)
pythonScript = objArgs(1)
configName = objArgs(2)

command = "cmd.exe /c """"" & projectPath & "\ta_env\Scripts\activate.bat"" && python """ & projectPath & "\" & pythonScript & """ """ & configName & """"""

Set WshShell = CreateObject("WScript.Shell")
WshShell.Run command, 0, False ' 0 = hidden window, False = don't wait for it to finish