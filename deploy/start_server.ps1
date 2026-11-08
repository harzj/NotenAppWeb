# Wird vom NSSM-Dienst "NotenAppServer" gestartet; Konfiguration steht in server.env.ps1.
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$EnvFile = Join-Path $RepoRoot "deploy\server.env.ps1"
if (-not (Test-Path $EnvFile)) { throw "Fehlt: $EnvFile (Vorlage: deploy\server.env.ps1.example)" }
. $EnvFile

# Ohne Datenordner wuerde die App still in instance\ im Repo schreiben.
if (-not $env:NOTENAPP_NOTFALL -or -not $env:NOTENAPP_DATA_DIR) {
    throw "NOTENAPP_NOTFALL und NOTENAPP_DATA_DIR muessen in server.env.ps1 gesetzt sein."
}

# Zugangslinks sollen auf die oeffentliche ngrok-Adresse zeigen (wie bisher in tray.py).
if (-not $env:PUBLIC_BASE_URL -and $env:NGROK_DOMAIN) {
    $env:PUBLIC_BASE_URL = "https://$($env:NGROK_DOMAIN)"
}

# Ausgaben sofort ins Dienstprotokoll schreiben (Tracebacks nicht im Puffer verlieren)
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

& $Python run_prod.py
exit $LASTEXITCODE
