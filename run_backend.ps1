$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py = "$Root\.venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Virtual environment not found. Run .\setup_windows.ps1 first." }
Set-Location "$Root\backend"
& $Py -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
