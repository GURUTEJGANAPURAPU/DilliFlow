$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path "$Root\frontend\node_modules")) { throw "Frontend dependencies not found. Run .\setup_windows.ps1 first." }
Set-Location "$Root\frontend"
npm run dev
