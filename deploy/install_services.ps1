# Richtet die Windows-Dienste fuer den Notfallserver per NSSM ein (oder neu ein):
#   NotenAppServer  - die App (deploy\start_server.ps1, waitress)
#   NotenAppNgrok   - der ngrok-Tunnel (deploy\start_ngrok.ps1)
# Beide starten beim Hochfahren automatisch (verzoegert, ohne Anmeldung) und werden
# von NSSM nach einem Absturz neu gestartet.
#
# Als Administrator ausfuehren:
#   powershell -ExecutionPolicy Bypass -File deploy\install_services.ps1
#   ... -Nssm C:\Tools\nssm.exe    (falls nssm nicht im PATH liegt)
#   ... -OhneNgrok                 (nur die App)
param(
    [string]$Nssm = "nssm",
    [switch]$OhneNgrok
)
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $RepoRoot "deploy\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Get-Command $Nssm -ErrorAction SilentlyContinue)) {
    throw "NSSM nicht gefunden ('$Nssm'). Pfad mit -Nssm angeben."
}
if (-not (Test-Path (Join-Path $RepoRoot "deploy\server.env.ps1"))) {
    throw "Zuerst deploy\server.env.ps1 aus server.env.ps1.example anlegen."
}

function Install-Dienst([string]$Name, [string]$Skript, [string]$Log, [string]$Beschreibung) {
    if (Get-Service -Name $Name -ErrorAction SilentlyContinue) {
        Write-Output "Dienst '$Name' existiert - wird angehalten und neu eingestellt."
        & $Nssm stop $Name | Out-Null
    } else {
        & $Nssm install $Name "powershell.exe" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "nssm install $Name fehlgeschlagen" }
    }
    $logPfad = Join-Path $LogDir $Log
    $skriptPfad = Join-Path $RepoRoot $Skript
    $einstellungen = @(
        @("Application", "powershell.exe"),
        @("AppParameters", "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$skriptPfad`""),
        @("AppDirectory", $RepoRoot),
        @("DisplayName", $Name),
        @("Description", $Beschreibung),
        @("Start", "SERVICE_DELAYED_AUTO_START"),
        @("AppExit", "Default", "Restart"),
        @("AppRestartDelay", "10000"),
        @("AppStdout", $logPfad),
        @("AppStderr", $logPfad)
    )
    # Nicht jede NSSM-Version kennt diese Einstellungen; fehlen sie, gelten die NSSM-Standards
    # (Prozessbaum wird beim Stoppen ohnehin beendet, Protokoll waechst dann ohne Rotation).
    $optional = @(
        @("AppRotateFiles", "1"),
        @("AppRotateOnline", "1"),
        @("AppRotateBytes", "5242880"),
        @("AppKillProcessTree", "1")
    )
    foreach ($e in $einstellungen) {
        & $Nssm set $Name @e | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "nssm set $Name $($e[0]) fehlgeschlagen" }
    }
    foreach ($e in $optional) {
        & $Nssm set $Name @e 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Output "Hinweis: Diese NSSM-Version kennt '$($e[0])' nicht - uebersprungen." }
    }
    & $Nssm start $Name | Out-Null
    Start-Sleep -Seconds 3
    Write-Output "Dienst '$Name': $((Get-Service -Name $Name).Status)  (Protokoll: $logPfad)"
}

Install-Dienst "NotenAppServer" "deploy\start_server.ps1" "server.log" "NotenApp Notfallserver (waitress)"
if (-not $OhneNgrok) {
    Install-Dienst "NotenAppNgrok" "deploy\start_ngrok.ps1" "ngrok.log" "ngrok-Tunnel fuer den NotenApp Notfallserver"
}

Write-Output ""
Write-Output "Als Naechstes: deploy\install_update_task.ps1 (Auto-Update alle 5 Minuten)."
