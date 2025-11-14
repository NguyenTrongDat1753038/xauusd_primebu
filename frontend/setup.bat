@echo off
REM TradeBot Hub Frontend - Development Setup Script (Windows)
REM Run this script to set up the development environment

setlocal enabledelayedexpansion

REM Colors (Windows 10+)
set "BLUE=[94m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "NC=[0m"

cls

echo %BLUE%
echo ============================================================
echo   TradeBot Hub Frontend - Development Setup
echo.
echo   This script will set up your development environment
echo ============================================================
echo %NC%
echo.

REM Check prerequisites
echo %BLUE%Check Prerequisites%NC%
echo ============================================================

REM Check Node.js
where /q node
if errorlevel 1 (
    echo %RED%X Node.js is not installed%NC%
    echo   Download from: https://nodejs.org/
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version') do set "NODE_VERSION=%%i"
echo %GREEN%+ Node.js %NODE_VERSION%%NC%

REM Check npm
where /q npm
if errorlevel 1 (
    echo %RED%X npm is not installed%NC%
    exit /b 1
)
for /f "tokens=*" %%i in ('npm --version') do set "NPM_VERSION=%%i"
echo %GREEN%+ npm %NPM_VERSION%%NC%

REM Check FastAPI backend
echo %BLUE%i Checking FastAPI backend...%NC%
powershell -Command "try { $null = Invoke-WebRequest -Uri 'http://localhost:8000/docs' -UseBasicParsing -TimeoutSec 2; Write-Host '%GREEN%+ FastAPI backend is running%NC%' } catch { Write-Host '%YELLOW%! FastAPI backend is not running on http://localhost:8000%NC%'; Write-Host '%BLUE%i Start it with: python -m uvicorn app.main:app --reload%NC%' }"

echo.
echo.

REM Install dependencies
echo %BLUE%Installing Dependencies%NC%
echo ============================================================

if not exist "node_modules" (
    echo %BLUE%i Running npm install...%NC%
    call npm install
    if errorlevel 1 (
        echo %RED%X npm install failed%NC%
        exit /b 1
    )
    echo %GREEN%+ Dependencies installed%NC%
) else (
    echo %BLUE%i node_modules already exists%NC%
    echo %BLUE%i Running npm ci to ensure consistency...%NC%
    call npm ci
)

echo.
echo.

REM Setup environment
echo %BLUE%Setting Up Environment%NC%
echo ============================================================

if not exist ".env" (
    if exist ".env.example" (
        echo %BLUE%i Creating .env from .env.example...%NC%
        copy .env.example .env > nul
        echo %GREEN%+ .env created%NC%
        echo %YELLOW%! Please review and update .env with your settings%NC%
    )
) else (
    echo %BLUE%i .env already exists%NC%
)

echo.
echo.

REM Create directories
echo %BLUE%Creating Directories%NC%
echo ============================================================

setlocal enabledelayedexpansion
set "dirs=logs public public\icons public\screenshots reports"
for %%d in (!dirs!) do (
    if not exist "%%d" (
        mkdir "%%d"
        echo %GREEN%+ Created %%d\%NC%
    ) else (
        echo %BLUE%i %%d\ already exists%NC%
    )
)
endlocal

echo.
echo.

REM Test installation
echo %BLUE%Testing Installation%NC%
echo ============================================================

echo %BLUE%i Checking Node.js modules...%NC%
node -e "require('express'); console.log('  %GREEN%+%NC% express')" || goto test_failed
node -e "require('ws'); console.log('  %GREEN%+%NC% ws')" || goto test_failed
node -e "require('puppeteer'); console.log('  %GREEN%+%NC% puppeteer')" || goto test_failed

echo %GREEN%+ All modules loaded successfully%NC%
echo.
echo.

goto success

:test_failed
echo %RED%X Module test failed%NC%
exit /b 1

:success
REM Display next steps
echo %BLUE%Next Steps%NC%
echo ============================================================
echo.
echo 1. Start the frontend server:
echo    %YELLOW%npm start%NC%
echo.
echo 2. Open in browser:
echo    %YELLOW%http://localhost:3000%NC%
echo.
echo 3. Or access via local IP (find with "ipconfig"):
echo    %YELLOW%http://192.168.x.x:3000%NC%
echo.
echo Optional: Install as PWA
echo   - Open http://localhost:3000 in Chrome/Edge
echo   - Click 'Install' button in address bar
echo.
echo For more information, see:
echo   - README.md - Full documentation
echo   - QUICKSTART.md - Quick start guide
echo   - config.js - Configuration options
echo.
echo.
echo %BLUE%============================================================%NC%
echo %GREEN%Setup Complete!%NC%
echo %BLUE%============================================================%NC%
echo.
echo %GREEN%+ Your development environment is ready!%NC%
echo.

endlocal
