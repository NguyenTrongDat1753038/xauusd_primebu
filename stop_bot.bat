@echo off
setlocal EnableDelayedExpansion
set "PROJECT_PATH=%~dp0"
chcp 65001 > nul

cls
echo === DUNG BOT TRADING ===
echo 1. Dung tat ca cac bot
echo 2. Dung bot BTCUSD (Moi)
echo 3. Dung bot XAUUSD
echo 4. Dung bot EURGBP
echo ======================
echo.

choice /c 1234 /n /m "Chon tuy chon (1-4): "

if errorlevel 4 (
    set "CONFIG_NAME=eurgbp_prod"
) else if errorlevel 3 (
    set "CONFIG_NAME=xauusd_prod"
) else if errorlevel 2 (
    set "CONFIG_NAME=btcusd_prod"
) else (
    set "CONFIG_NAME=all"
)

echo.
echo [ACTION] Gui tin hieu dung bot...
if "!CONFIG_NAME!" == "all" (
    echo [INFO] Gui tin hieu dung cho tat ca cac bot...
    type nul > "!PROJECT_PATH!stop_signal_btcusd_prod.txt"
    type nul > "!PROJECT_PATH!stop_signal_xauusd_prod.txt"
    type nul > "!PROJECT_PATH!stop_signal_eurgbp_prod.txt"
) else (
    echo [INFO] Gui tin hieu dung cho bot !CONFIG_NAME!...
    type nul > "!PROJECT_PATH!stop_signal_!CONFIG_NAME!.txt"
)

echo.
echo [INFO] Cho bot tu dong dung (toi da 60s)...
echo [INFO] Kiem tra tien trinh bot...

REM Doi bot tu dong dung (kiem tra moi 2 giay)
set MAX_WAIT=60
set ELAPSED=0

:WAIT_LOOP
if !ELAPSED! GEQ !MAX_WAIT! (
    echo [WARNING] Qua thoi gian cho. Kiem tra trang thai cuoi cung...
    goto CHECK_STATUS
)

REM Kiem tra xem con tien trinh bot nao dang chay khong
set BOT_RUNNING=0
if "!CONFIG_NAME!" == "all" (
    for %%C in (btcusd_prod xauusd_prod eurgbp_prod) do (
        wmic process where "commandline like '%%run_live.py%%' and commandline like '%%%%C%%'" get processid 2>nul | find /i "ProcessId" >nul
        if !ERRORLEVEL! EQU 0 (
            set BOT_RUNNING=1
        )
    )
) else (
    wmic process where "commandline like '%%run_live.py%%' and commandline like '%%!CONFIG_NAME!%%'" get processid 2>nul | find /i "ProcessId" >nul
    if !ERRORLEVEL! EQU 0 (
        set BOT_RUNNING=1
    )
)

if !BOT_RUNNING! EQU 0 (
    echo [SUCCESS] Bot da dung thanh cong!
    goto CLEANUP
)

echo [.] Dang cho bot dung... (!ELAPSED!s/!MAX_WAIT!s^)
timeout /t 2 /nobreak >nul
set /a ELAPSED+=2
goto WAIT_LOOP

:CHECK_STATUS
echo.
echo [DEBUG] Kiem tra trang thai cuoi cung:
if "!CONFIG_NAME!" == "all" (
    wmic process where "commandline like '%%run_live.py%%'" get processid,commandline 2>nul
) else (
    wmic process where "commandline like '%%run_live.py%%' and commandline like '%%!CONFIG_NAME!%%'" get processid,commandline 2>nul
)

:CLEANUP
echo.
echo [INFO] Xoa cac file tin hieu...
if "!CONFIG_NAME!" == "all" (
    del /q "!PROJECT_PATH!stop_signal_btcusd_prod.txt" 2>nul
    del /q "!PROJECT_PATH!stop_signal_xauusd_prod.txt" 2>nul
    del /q "!PROJECT_PATH!stop_signal_eurgbp_prod.txt" 2>nul
) else (
    del /q "!PROJECT_PATH!stop_signal_!CONFIG_NAME!.txt" 2>nul
)

echo.
echo [DONE] Hoan thanh!
pause