$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path "$Root\.venv\Scripts\python.exe")) { throw "Run .\setup_windows.ps1 first." }
if (-not (Test-Path "$Root\frontend\node_modules")) { throw "Run .\setup_windows.ps1 first." }
$BackendScript = Join-Path $Root 'run_backend.ps1'
$FrontendScript = Join-Path $Root 'run_frontend.ps1'
Start-Process powershell -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-File', $BackendScript)
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-File', $FrontendScript)
Start-Sleep -Seconds 3
Start-Process 'http://localhost:5173'
Write-Host 'DilliFlow started. Backend docs: http://localhost:8000/docs' -ForegroundColor Green
