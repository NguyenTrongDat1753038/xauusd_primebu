@echo off
chcp 65001 > nul
echo === KIEM TRA TRANG THAI BOT ===
echo.

REM Kiểm tra tất cả các bot đang chạy
echo [INFO] Cac bot dang chay:
wmic process where "commandline like '%%run_live.py%%'" get processid,commandline 2>nul | findstr /i "run_live"

if errorlevel 1 (
    echo [INFO] Khong co bot nao dang chay.
) else (
    echo.
    echo [INFO] Danh sach chi tiet:
    wmic process where "commandline like '%%run_live.py%%'" get processid,commandline
)

echo.
echo === KET THUC ===
pause