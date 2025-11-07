' VBScript de chay file .bat mot cach an danh

Set WshShell = CreateObject("WScript.Shell")
' Chay file run_bot_internal.bat o thu muc goc
WshShell.Run "cmd /c d:\Code\XAU_Bot_Predict\run_bot_internal.bat", 0, False
Set WshShell = Nothing