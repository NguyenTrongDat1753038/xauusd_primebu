@echo off
TITLE Multi-Bot Launcher

echo.
echo Starting XAUUSD Bot...
call start_xauusd_bot.bat

echo.
echo Starting EURGBP Bot...
call start_eurgbp_bot.bat

echo.
echo Starting BTCUSD Bot...
call start_btcusd_bot.bat

echo.
echo All bots have been launched in the background.