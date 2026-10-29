<#
.SYNOPSIS
  Rozalt — local setup and launch (Windows PowerShell 5.1+).

.EXAMPLE
  .\run.ps1 -Setup        # first time: venv, Python + npm deps, DB migration, synthetic data, frontend build
  .\run.ps1               # start API (:8000) and web app (:3000) in two new windows
  .\run.ps1 -Dev          # start with hot reload (uvicorn --reload, next dev)
  .\run.ps1 -Test         # backend tests + frontend typecheck
  .\run.ps1 -Evaluate     # synthetic scenario evaluation report
#>
param([switch]$Setup, [switch]$Dev, [switch]$Test, [switch]$Evaluate)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Front = Join-Path $Root "frontend"

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

if ($Setup) {
    if (-not (Test-Path $Py)) { Step "Creating virtual environment"; python -m venv (Join-Path $Root ".venv") }
    Step "Installing Python dependencies"
    & $Py -m pip install --upgrade pip -q
    & $Py -m pip install -r (Join-Path $Root "backend\requirements.txt") -q
    if (-not (Test-Path (Join-Path $Root ".env"))) { Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env") }
    Step "Migrating database"
    Push-Location $Root; & $Py -m backend.cli init-db; Pop-Location
    Step "Loading synthetic dataset"
    Push-Location $Root; & $Py -m backend.cli load-synthetic | Out-Null; Pop-Location
    Step "Installing frontend dependencies"
    Push-Location $Front; npm install --no-fund --no-audit; Pop-Location
    Step "Building frontend"
    Push-Location $Front; npm run build; Pop-Location
    Write-Host "Setup complete. Start with: .\run.ps1" -ForegroundColor Green
    exit 0
}

if ($Test) {
    Push-Location $Root; & $Py -m pytest backend/tests -q -p no:warnings; $code = $LASTEXITCODE; Pop-Location
    Push-Location $Front; npx tsc --noEmit; if ($LASTEXITCODE -ne 0) { $code = 1 }; Pop-Location
    exit $code
}

if ($Evaluate) { Push-Location $Root; & $Py -m backend.evaluation.evaluate; Pop-Location; exit $LASTEXITCODE }

if (-not (Test-Path $Py)) { Write-Host "Run .\run.ps1 -Setup first." -ForegroundColor Yellow; exit 1 }

$apiArgs = "-m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"
if ($Dev) { $apiArgs += " --reload --reload-dir backend" }
Step "Starting API on http://127.0.0.1:8000 (docs: /docs)"
Start-Process -FilePath $Py -ArgumentList $apiArgs -WorkingDirectory $Root

$webCmd = if ($Dev) { "npm run dev" } else { "npm run start" }
if (-not $Dev -and -not (Test-Path (Join-Path $Front ".next\BUILD_ID"))) { $webCmd = "npm run build; npm run start" }
Step "Starting web app on http://localhost:3000"
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit", "-Command", $webCmd -WorkingDirectory $Front

Write-Host "Open http://localhost:3000  (close the two windows to stop)" -ForegroundColor Green
