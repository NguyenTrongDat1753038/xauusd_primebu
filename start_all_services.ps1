# TradeBot Hub - Start All Services (PowerShell Version)
# More robust than .bat, works better on modern Windows

param(
    [switch]$SkipRedis,
    [switch]$NoHealthCheck,
    [switch]$Background
)

# Colors for output
$SUCCESS = "Green"
$WARNING = "Yellow"
$ERROR_COLOR = "Red"
$INFO = "Cyan"

function Write-Success { param([string]$Message) Write-Host "[OK] $Message" -ForegroundColor $SUCCESS }
function Write-Warning { param([string]$Message) Write-Host "[WARN] $Message" -ForegroundColor $WARNING }
function Write-ErrorMsg { param([string]$Message) Write-Host "[FAIL] $Message" -ForegroundColor $ERROR_COLOR }
function Write-Info { param([string]$Message) Write-Host "[INFO] $Message" -ForegroundColor $INFO }

# Clear screen
Clear-Host

# Header
Write-Host "`n=============================================================" -ForegroundColor Cyan
Write-Host "          TRADEBOT HUB - COMPLETE STARTUP (PowerShell)         " -ForegroundColor Cyan
Write-Host "      (Backend + Celery + Frontend + Redis Check)             " -ForegroundColor Cyan
Write-Host "=============================================================`n" -ForegroundColor Cyan

$CurrentDir = Get-Location

# ===== STEP 1: CHECK REDIS =====
Write-Info "STEP 1/4 Checking Redis..."
Write-Host ""

$RedisRunning = $false
$RedisWarning = $false

try {
    $result = & redis-cli ping 2>$null
    if ($result -eq "PONG") {
        Write-Success "Redis is already running on localhost:6379"
        $RedisRunning = $true
    }
} catch {
    # Redis CLI not found or Redis not running
}

if (-not $RedisRunning -and -not $SkipRedis) {
    Write-Warning "Redis not responding"
    Write-Host ""
    
    # Try to start via WSL
    $wslExists = Test-Path "C:\Program Files\WSL\wsl.exe"
    $dockerExists = $null -ne (Get-Command docker -ErrorAction SilentlyContinue)
    
    if ($dockerExists) {
        Write-Info "Attempting to start Redis via Docker..."
        # Check if a container with the same name exists and is stopped
        $existingContainer = docker ps -a --filter "name=redis-tradebot" --format "{{.ID}}"
        if ($existingContainer) {
            Write-Info "Found existing 'redis-tradebot' container. Removing it first..."
            docker rm -f redis-tradebot | Out-Null
        }

        try {
            # Run with a specific name to avoid conflicts and capture output
            $dockerOutput = docker run --name redis-tradebot -d -p 6379:6379 redis:latest 2>&1
            if ($?) {
                Start-Sleep -Seconds 3 # Give Redis more time to start
                try {
                    $result = & redis-cli ping 2>$null
                    if ($result -eq "PONG") {
                        Write-Success "Redis started successfully via Docker"
                        $RedisRunning = $true
                    }
                } catch {
                    # redis-cli might not be in PATH, but container is running.
                }
            }
        } catch {
            $RedisWarning = $true
        }
    } elseif ($wslExists) {
        Write-Info "Attempting to start Redis via WSL..."
        try {
            $null = Start-Process -FilePath "wsl" -ArgumentList "redis-server" -WindowStyle Normal
            Start-Sleep -Seconds 3
            $result = & redis-cli ping 2>$null
            if ($result -eq "PONG") {
                Write-Success "Redis started via WSL"
                $RedisRunning = $true
            }
        } catch {
            $RedisWarning = $true
        }
    } else {
        Write-ErrorMsg "Redis not found. Install via:"
        Write-Host "  * Docker: docker run -d -p 6379:6379 redis:latest"
        Write-Host "  * WSL: wsl redis-server"
        Write-Host "  * Windows: https://github.com/microsoftarchive/redis/releases"
        Write-Host ""
        $RedisWarning = $true
    }
}

if ($RedisWarning) {
    Write-Warning "Redis may not be available. Bot management features may not work."
}

Write-Host ""

# ===== STEP 2: ACTIVATE VENV =====
Write-Info "STEP 2/4 Activating Python environment..."

$venvPath = Join-Path $CurrentDir "ta_env\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    & $venvPath
    Write-Success "Virtual environment activated"
} else {
    Write-ErrorMsg "Virtual environment not found at $venvPath"
    exit 1
}

Write-Host ""

# ===== STEP 3: START SERVICES =====
Write-Info "STEP 3/4 Starting services in separate windows..."
Write-Host ""

if ($RedisWarning) {
    Write-Warning "Redis status uncertain - bot management may not work fully"
    Write-Host ""
}

# Check if services are already running
$processes = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "(uvicorn|celery)" }
$npmProcess = Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "npm" }

# Start FastAPI if not running
if (-not ($processes | Where-Object { $_.CommandLine -match "uvicorn" })) {
    Write-Info "Launching Backend (FastAPI on port 8001)..."
    $backendCmd = "& `'$venvPath`'; `$env:PYTHONUTF8='1'; python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001"
    if ($Background) {
        Start-Process -FilePath "powershell.exe" -ArgumentList @("-Command", $backendCmd) -WindowStyle Hidden
    } else {
        Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-Command", $backendCmd) -WorkingDirectory $CurrentDir -WindowStyle Normal
    }
    Start-Sleep -Seconds 2
} else {
    Write-Success "FastAPI already running"
}

# Start Celery Worker if not running
if (-not ($processes | Where-Object { $_.CommandLine -match "celery" })) {
    Write-Info "Launching Celery Worker..."
    $celeryCmd = "& `'$venvPath`'; `$env:PYTHONUTF8='1'; python -m celery -A tasks.celery_worker worker --loglevel=info -P solo"
    if ($Background) {
        Start-Process -FilePath "powershell.exe" -ArgumentList @("-Command", $celeryCmd) -WindowStyle Hidden
    } else {
        Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-Command", $celeryCmd) -WorkingDirectory $CurrentDir -WindowStyle Normal
    }
    Start-Sleep -Seconds 2
} else {
    Write-Success "Celery Worker already running"
}

# Start Frontend if not running
if (-not $npmProcess) {
    Write-Info "Launching Frontend (Express on port 3001)..."
    $frontendPath = Join-Path $CurrentDir "frontend"
    if (-not (Test-Path $frontendPath)) {
        Write-Warning "Frontend folder not found at $frontendPath. Skipping frontend startup."
    } else {
        $nodeModules = Join-Path $frontendPath "node_modules"
        $installCmd = "cd '$frontendPath'; if (-not (Test-Path 'node_modules')) { npm install --no-fund --no-audit }; npm start"
        Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-Command", $installCmd) -WindowStyle Normal
        Start-Sleep -Seconds 2
    }
} else {
    Write-Success "Frontend already running"
}

Write-Host ""

# ===== STEP 4: HEALTH CHECKS =====
if (-not $NoHealthCheck) {
    Write-Info "STEP 4/4 Performing health checks..."
    Write-Host ""
    
    $checks = @{
        "FastAPI" = "http://localhost:8001/docs"
        "Frontend" = "http://localhost:3001"
    }
    
    foreach ($check in $checks.GetEnumerator()) {
        $name = $check.Name
        $url = $check.Value
        $found = $false
        
        for ($i = 0; $i -lt 5; $i++) {
            try {
                $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($response.StatusCode -eq 200) {
                    Write-Success "$name ($url) is responding"
                    $found = $true
                    break
                }
            } catch {
                Start-Sleep -Seconds 1
            }
        }
        
        if (-not $found) {
            Write-Warning "$name ($url) not responding yet (may still be starting)"
        }
    }
    
    # Check Redis
    Write-Host ""
    try {
        $result = & redis-cli ping 2>$null
        if ($result -eq "PONG") {
            Write-Success "Redis is responding on port 6379"
        } else {
            # Fallback TCP probe if redis-cli exists but didn't return PONG
            $tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -InformationLevel Quiet
            if ($tcp) { Write-Success "Redis port 6379 is open (no redis-cli)" } else { Write-Warning "Redis not responding" }
        }
    } catch {
        # If redis-cli is not installed, fallback to TCP probe
        try {
            $tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -InformationLevel Quiet
            if ($tcp) { Write-Success "Redis port 6379 is open (no redis-cli)" } else { Write-Warning "Redis not responding" }
        } catch { Write-Warning "Redis not responding" }
    }
}

# ===== SUMMARY =====
Write-Host "`n=============================================================" -ForegroundColor Green
Write-Host "                   STARTUP COMPLETE                            " -ForegroundColor Green
Write-Host "=============================================================`n" -ForegroundColor Green

if ($RedisWarning) {
    Write-Host "`n"
    Write-Warning "Redis may not be properly configured"
    Write-Host "Bot management features require Redis. To set up:"
    Write-Host "  - Use Docker:  docker run -d -p 6379:6379 redis:7-alpine"
    Write-Host "  - Or use WSL:  wsl redis-server"
    Write-Host ""
}

Write-Host "NEXT STEPS:" -ForegroundColor Cyan
Write-Host "  1. Open http://localhost:3001 in your browser"
Write-Host "  2. Click 'Start' on a bot card to begin trading"
Write-Host "  3. View logs in the new terminal windows"
Write-Host "  4. Use Telegram channel or Backend API to verify bot is running"
Write-Host ""
if ($Background) {
    Write-Host "IMPORTANT:" -ForegroundColor Yellow
    Write-Host "  * Services are running in the background."
    Write-Host "  * To stop them, use Task Manager to end 'python.exe' and 'node.exe' processes,"
    Write-Host "    or run the following command in PowerShell:"
    Write-Host "    Get-Process -Name 'python', 'node' | Where-Object { `$_.CommandLine -match '(uvicorn|celery|npm)' } | Stop-Process -Force"
    Write-Host ""
} else {
    Write-Host "IMPORTANT:" -ForegroundColor Yellow
    Write-Host "  * Keep all new terminal windows open"
    Write-Host "  * Close any window to stop that service"
    Write-Host "  * Use Ctrl+C in any window to gracefully stop"
    Write-Host ""
}

Write-Host "For more help, see: QUICK_START.md" -ForegroundColor Cyan
Write-Host ""
