# Wird vom NSSM-Dienst "NotenAppNgrok" gestartet. Eigener Dienst, damit der Tunnel
# bei App-Updates (Neustart von NotenAppServer) stehen bleibt.
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$EnvFile = Join-Path $RepoRoot "deploy\server.env.ps1"
if (-not (Test-Path $EnvFile)) { throw "Fehlt: $EnvFile (Vorlage: deploy\server.env.ps1.example)" }
. $EnvFile

$Ngrok = if ($env:NGROK_EXE) { $env:NGROK_EXE } else { Join-Path $RepoRoot "ngrok.exe" }
$Port = if ($env:NOTENAPP_PORT) { $env:NOTENAPP_PORT } else { "5000" }
if (-not $env:NGROK_DOMAIN) { throw "NGROK_DOMAIN fehlt in server.env.ps1." }

$Argumente = @("http", "--domain=$($env:NGROK_DOMAIN)", "--log=stdout", $Port)
if ($env:NGROK_CONFIG) {
    if (-not (Test-Path $env:NGROK_CONFIG)) { throw "ngrok-Konfiguration nicht gefunden: $($env:NGROK_CONFIG)" }
    $Argumente += "--config=$($env:NGROK_CONFIG)"
}

# Beendet sich ngrok (z. B. kein Netz direkt nach dem Hochfahren), startet NSSM es neu.
& $Ngrok @Argumente
exit $LASTEXITCODE
