# ============================================================
# rebuild_venvs.ps1
# Rebuild Virtual Environments for AI_Project
# ============================================================

$ErrorActionPreference = "Stop"

# Project paths
$projects = @(
    @{
        Name = "mellow_link"
        Path = "D:\AI_Project\mellow_link"
        VenvName = ".venv"
        Requirements = "requirements.txt"
    },
    @{
        Name = "Open-LLM-VTuber"
        Path = "D:\AI_Project\Open-LLM-VTuber"
        VenvName = ".venv"
        Requirements = "requirements.txt"
    }
)

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host " $Message" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Check Python installation
Write-Header "Checking Python Installation"
try {
    $pythonVersion = python --version 2>&1
    Write-Success "Python found: $pythonVersion"
} catch {
    Write-Error "Python is not installed or not in PATH!"
    exit 1
}

# Process each project
foreach ($project in $projects) {
    Write-Header "Processing: $($project.Name)"

    $projectPath = $project.Path
    $venvPath = Join-Path $projectPath $project.VenvName
    $requirementsPath = Join-Path $projectPath $project.Requirements

    # Check if project directory exists
    if (-not (Test-Path $projectPath)) {
        Write-Error "Project directory not found: $projectPath"
        continue
    }

    # Step 1: Force delete existing venv
    Write-Step "Deleting existing virtual environment..."
    if (Test-Path $venvPath) {
        try {
            Remove-Item -Path $venvPath -Recurse -Force -ErrorAction Stop
            Write-Success "Deleted: $venvPath"
        } catch {
            Write-Error "Failed to delete venv: $_"
            Write-Host "Trying alternative method..." -ForegroundColor Yellow
            cmd /c "rmdir /s /q `"$venvPath`"" 2>$null
            if (-not (Test-Path $venvPath)) {
                Write-Success "Deleted using alternative method"
            } else {
                Write-Error "Could not delete venv. Please close any programs using it and try again."
                continue
            }
        }
    } else {
        Write-Host "No existing venv found, skipping delete." -ForegroundColor Gray
    }

    # Step 2: Create new virtual environment
    Write-Step "Creating new virtual environment..."
    try {
        Push-Location $projectPath
        python -m venv $project.VenvName
        Pop-Location
        Write-Success "Created: $venvPath"
    } catch {
        Pop-Location
        Write-Error "Failed to create venv: $_"
        continue
    }

    # Step 3: Activate and install requirements
    Write-Step "Installing requirements..."
    $activateScript = Join-Path $venvPath "Scripts\Activate.ps1"

    if (-not (Test-Path $requirementsPath)) {
        Write-Error "requirements.txt not found: $requirementsPath"
        continue
    }

    try {
        # Upgrade pip first, then install requirements
        $pipPath = Join-Path $venvPath "Scripts\pip.exe"
        $pythonPath = Join-Path $venvPath "Scripts\python.exe"

        Write-Host "  Upgrading pip..." -ForegroundColor Gray
        & $pythonPath -m pip install --upgrade pip --quiet

        Write-Host "  Installing packages from requirements.txt..." -ForegroundColor Gray
        & $pipPath install -r $requirementsPath

        if ($LASTEXITCODE -eq 0) {
            Write-Success "Requirements installed successfully!"
        } else {
            Write-Error "Some packages may have failed to install."
        }
    } catch {
        Write-Error "Failed to install requirements: $_"
    }

    Write-Host ""
}

Write-Header "Rebuild Complete!"
Write-Host "Summary:" -ForegroundColor White
Write-Host "  - mellow_link: D:\AI_Project\mellow_link\.venv" -ForegroundColor Gray
Write-Host "  - Open-LLM-VTuber: D:\AI_Project\Open-LLM-VTuber\.venv" -ForegroundColor Gray
Write-Host ""
Write-Host "To activate virtual environments:" -ForegroundColor Yellow
Write-Host '  mellow_link:      D:\AI_Project\mellow_link\.venv\Scripts\Activate.ps1' -ForegroundColor Cyan
Write-Host '  Open-LLM-VTuber:  D:\AI_Project\Open-LLM-VTuber\.venv\Scripts\Activate.ps1' -ForegroundColor Cyan
Write-Host ""

# Pause at the end
Read-Host "Press Enter to exit"
