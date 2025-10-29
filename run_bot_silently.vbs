' VBScript de chay file .bat mot cach an danh

Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c d:\Code\XAU_Bot_Predict\run_bot_internal.bat", 0, False
Set WshShell = Nothing