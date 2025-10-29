@echo off
REM File nay duoc goi boi VBScript de chay bot mot cach an danh.

REM Duong dan den thu muc project
set "PROJECT_PATH=d:\Code\XAU_Bot_Predict"

REM Kich hoat moi truong ao (virtual environment)
call "%PROJECT_PATH%\.venv\Scripts\activate.bat"

REM Chay script Python.
python "%PROJECT_PATH%\src\live_trader.py"