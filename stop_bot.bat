@echo off
echo --- DANG TIM VA DUNG BOT ---
REM Tim va dung tien trinh Python dang chay file "run_live.py"
wmic process where "name='python.exe' and commandline like '%%run_live.py%%'" call terminate
echo.
echo --- DA GUI LENH DUNG BOT. ---
pause