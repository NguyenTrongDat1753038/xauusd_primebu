# TradeBot Hub - Shutdown All Services (PowerShell Version)

param(
    [switch]$SkipRedis
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
Write-Host "          TRADEBOT HUB - COMPLETE SHUTDOWN (PowerShell)        " -ForegroundColor Cyan
Write-Host "=============================================================`n" -ForegroundColor Cyan

# Function to find and stop processes
function Stop-ServiceProcess {
    param(
        [string]$ProcessName,
        [string]$CommandLineKeyword,
        [string]$ServiceDescription
    )

    Write-Info "Attempting to stop $ServiceDescription..."
    
    try {
        # We need to get the command line, which requires a more detailed process query
        $processes = Get-CimInstance Win32_Process -Filter "Name = '$ProcessName.exe'" | Where-Object { $_.CommandLine -match $CommandLineKeyword }
        
        if ($processes) {
            foreach ($proc in $processes) {
                Write-Host "  - Found process with PID $($proc.ProcessId) matching '$CommandLineKeyword'. Stopping..."
                Stop-Process -Id $proc.ProcessId -Force
            }
            Write-Success "$ServiceDescription stopped."
        } else {
            Write-Warning "$ServiceDescription process not found."
        }
    } catch {
        Write-ErrorMsg "An error occurred while trying to stop ${ServiceDescription}: $_"
    }
    Write-Host ""
}

# ===== STEP 1: STOP MAIN SERVICES =====
Write-Info "STEP 1/2 Stopping main application services..."
Write-Host ""

# Stop FastAPI Backend (uvicorn)
Stop-ServiceProcess -ProcessName "python" -CommandLineKeyword "uvicorn" -ServiceDescription "Backend (FastAPI)"

# Stop Celery Worker
Stop-ServiceProcess -ProcessName "python" -CommandLineKeyword "celery" -ServiceDescription "Celery Worker"

# Stop Frontend (Express server)
Stop-ServiceProcess -ProcessName "node" -CommandLineKeyword "server\.js" -ServiceDescription "Frontend (Express)"

# ===== STEP 2: STOP REDIS (IF APPLICABLE) =====
if (-not $SkipRedis) {
    Write-Info "STEP 2/2 Checking for Redis Docker container..."
    Write-Host ""
    
    $dockerExists = $null -ne (Get-Command docker -ErrorAction SilentlyContinue)
    if ($dockerExists) {
        try {
            # Find container running the official redis image
            $containerId = docker ps -q --filter "ancestor=redis" --format "{{.ID}}"
            if ($containerId) {
                Write-Info "Found Redis container with ID $containerId. Stopping and removing..."
                docker stop $containerId | Out-Null
                docker rm $containerId | Out-Null
                Write-Success "Redis Docker container stopped and removed."
            } else {
                Write-Warning "No running Redis container found."
            }
        } catch {
            Write-ErrorMsg "An error occurred while trying to stop Redis container: $_"
        }
    } else {
        Write-Warning "Docker command not found. Cannot check for Redis container."
        Write-Host "If you started Redis via WSL or as a Windows service, you need to stop it manually."
    }
} else {
    Write-Info "STEP 2/2 Skipping Redis shutdown as requested."
}

# ===== SUMMARY =====
Write-Host "`n=============================================================" -ForegroundColor Green
Write-Host "                   SHUTDOWN COMPLETE                           " -ForegroundColor Green
Write-Host "=============================================================`n" -ForegroundColor Green
Write-Host "All targeted services have been shut down."