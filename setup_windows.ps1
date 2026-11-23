$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "== DilliFlow setup ==" -ForegroundColor Cyan

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
  throw "Python was not found. Install Python 3.11+ and reopen PowerShell."
}
$PythonVersionText = (& python --version 2>&1).ToString()
if ($PythonVersionText -notmatch 'Python\s+(\d+)\.(\d+)') {
  throw "Could not determine Python version: $PythonVersionText"
}
$PythonMajor = [int]$Matches[1]
$PythonMinor = [int]$Matches[2]
if (($PythonMajor -lt 3) -or ($PythonMajor -eq 3 -and $PythonMinor -lt 11)) {
  throw "DilliFlow requires Python 3.11 or newer. Found $PythonVersionText"
}

$Node = Get-Command node -ErrorAction SilentlyContinue
if (-not $Node) {
  throw "Node.js was not found. Install Node.js 20+ and reopen PowerShell."
}
$NodeVersionText = (& node --version).ToString().TrimStart('v')
$NodeVersion = [Version]$NodeVersionText
if ($NodeVersion.Major -lt 20) {
  throw "DilliFlow requires Node.js 20 or newer. Found v$NodeVersionText"
}

if (-not (Test-Path "$Root\.venv\Scripts\python.exe")) {
  python -m venv "$Root\.venv"
  if ($LASTEXITCODE -ne 0) { throw "Creating the Python virtual environment failed." }
}
$Py = "$Root\.venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Upgrading pip failed." }
& $Py -m pip install -r "$Root\backend\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw "Installing backend dependencies failed." }

if (-not (Test-Path "$Root\backend\.env")) {
  Copy-Item "$Root\backend\.env.example" "$Root\backend\.env"
  Write-Host "Created backend\.env. Add your Transport Stack API key there when ready." -ForegroundColor Yellow
}
if (-not (Test-Path "$Root\frontend\.env")) {
  Copy-Item "$Root\frontend\.env.example" "$Root\frontend\.env"
}

Set-Location "$Root\frontend"
npm install
if ($LASTEXITCODE -ne 0) { throw "Installing frontend dependencies failed." }
Set-Location $Root

Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next: run .\prepare_data.ps1 once, then .\run_dilliflow.ps1"
