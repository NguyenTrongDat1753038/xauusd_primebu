@echo off
REM File nay duoc goi boi VBScript de chay bot mot cach an danh.

REM %1 la duong dan den script Python (production/run_live.py)
REM %2 la ten file config (xauusd_prod)

REM Duong dan den thu muc project
set "PROJECT_PATH=d:\Code\XAU_Bot_Predict"

REM Kich hoat moi truong ao (virtual environment)
call "%PROJECT_PATH%\ta_env\Scripts\activate.bat"

REM Chay script Python voi tham so la ten file config
REM Su dung %~1 va %~2 de loai bo cac dau ngoac kep thua
python "%PROJECT_PATH%\%~1" "%~2"