$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvPath = Join-Path $ProjectRoot 'backend\.env'
$ExamplePath = Join-Path $ProjectRoot 'backend\.env.example'

if (-not (Test-Path (Split-Path -Parent $EnvPath))) {
    throw "Backend folder not found: $(Split-Path -Parent $EnvPath)"
}

if (-not (Test-Path $EnvPath)) {
    if (Test-Path $ExamplePath) {
        Copy-Item $ExamplePath $EnvPath
    } else {
        New-Item -ItemType File -Path $EnvPath | Out-Null
    }
}

function Set-EnvValue([string]$Key, [string]$Value) {
    $lines = @()
    if (Test-Path $EnvPath) {
        $lines = @(Get-Content -Path $EnvPath)
    }
    $escapedKey = [regex]::Escape($Key)
    $found = $false
    $updated = foreach ($line in $lines) {
        if ($line -match "^\s*$escapedKey\s*=") {
            $found = $true
            "$Key=$Value"
        } else {
            $line
        }
    }
    if (-not $found) { $updated += "$Key=$Value" }
    # Windows PowerShell 5's Set-Content -Encoding UTF8 adds a BOM, which can
    # prevent python-dotenv from recognising the first existing key. Write UTF-8
    # without BOM so the Transport Stack API key on the first line remains readable.
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllLines($EnvPath, [string[]]$updated, $utf8NoBom)
}

Write-Host "`nDilliFlow Operator Workspace Setup" -ForegroundColor Cyan
Write-Host "This configures a separate operator login. Commuter pages stay public." -ForegroundColor Gray

$operatorId = Read-Host "Choose an operator ID"
if ($operatorId -notmatch '^[A-Za-z0-9_.-]{3,64}$') { throw 'Operator ID must be 3–64 characters using letters, numbers, dot, underscore or hyphen.' }

$securePassword = Read-Host "Choose a strong operator password" -AsSecureString
$plainPassword = [System.Net.NetworkCredential]::new('', $securePassword).Password
$confirmSecurePassword = Read-Host "Confirm operator password" -AsSecureString
$confirmPassword = [System.Net.NetworkCredential]::new('', $confirmSecurePassword).Password
if ([string]::IsNullOrWhiteSpace($plainPassword) -or $plainPassword.Length -lt 12) {
    throw 'Use an operator password with at least 12 characters.'
}
if ($plainPassword -cne $confirmPassword) { throw 'The passwords did not match. No credentials were written.' }
# Quote and escape values so spaces, # and quotes remain valid in dotenv.
$escapedPassword = $plainPassword.Replace('\', '\\').Replace('"', '\"')
$passwordValue = '"' + $escapedPassword + '"'

$secretBytes = New-Object byte[] 48
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($secretBytes) } finally { $rng.Dispose() }
$tokenSecret = [Convert]::ToBase64String($secretBytes)

Set-EnvValue 'OPERATOR_ID' $operatorId
Set-EnvValue 'OPERATOR_PASSWORD' $passwordValue
Set-EnvValue 'OPERATOR_TOKEN_SECRET' $tokenSecret
Set-EnvValue 'OPERATOR_TOKEN_TTL_SECONDS' '28800'

Write-Host "`nOperator login configured." -ForegroundColor Green
Write-Host "Operator ID: $operatorId"
Write-Host 'Password: saved locally (not displayed)'
Write-Host 'Token signing secret: generated locally (not displayed)'
Write-Host "Environment file: $EnvPath"
Write-Host "`nRestart FastAPI to activate the login." -ForegroundColor Yellow
