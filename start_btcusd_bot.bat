@echo off
echo Starting BTCUSD Bot in the background...

REM %~dp0 la duong dan den thu muc chua file .bat nay (thu muc goc du an)
cscript //nologo run_bot_silently.vbs "%~dp0" "production\run_live.py" "btcusd_prod"
echo BTCUSD Bot has been launched.