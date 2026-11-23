$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py = "$Root\.venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Virtual environment not found. Run .\setup_windows.ps1 first." }
Set-Location "$Root\backend"
& $Py -m app.ingest
if ($LASTEXITCODE -ne 0) { throw "Data ingestion failed with exit code $LASTEXITCODE" }
Write-Host "DilliFlow database is ready." -ForegroundColor Green
