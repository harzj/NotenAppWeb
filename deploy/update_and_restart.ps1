# Laeuft per geplanter Aufgabe alle 5 min (install_update_task.ps1). Tut nur etwas, wenn
# origin neue Commits auf dem verfolgten Branch (release-1.2) hat:
#   git pull --ff-only -> Sicherung -> pip install -> Dienst NotenAppServer neu starten.
# Nach dem Muster aus dem Lernbuch (interactive_book/deploy/update_and_restart.ps1).
#
#   powershell -ExecutionPolicy Bypass -File deploy\update_and_restart.ps1
#   ... -OhneNeustart     (zum Testen: alles ausser dem Dienst-Neustart)
param(
    [string]$ServiceName = "NotenAppServer",
    [string]$NgrokServiceName = "NotenAppNgrok",
    [switch]$OhneNeustart
)
# Bewusst nicht "Stop": git schreibt normale Statuszeilen nach stderr, die PowerShell 5.1
# sonst als Fehler behandelt. Exitcodes werden nach jedem Aufruf einzeln geprueft.
$ErrorActionPreference = "Continue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogFile = Join-Path $RepoRoot "deploy\logs\update.log"
New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

# Ein laufendes Update darf nicht doppelt starten (manueller Start neben der Aufgabe).
$LockFile = Join-Path $RepoRoot "deploy\logs\update.lock"
$StaleAfterMinutes = 30

function Log($msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" | Add-Content -Path $LogFile
}

# stdout/stderr ueber Dateien einsammeln, sonst verpackt PowerShell 5.1 jede stderr-Zeile
# in einen NativeCommandError.
function Invoke-Extern {
    param([string]$Datei, [string[]]$Argumente)
    $ausgabe = [System.IO.Path]::GetTempFileName()
    $fehler = [System.IO.Path]::GetTempFileName()
    try {
        $prozess = Start-Process -FilePath $Datei -ArgumentList $Argumente -NoNewWindow -Wait -PassThru `
            -WorkingDirectory $RepoRoot -RedirectStandardOutput $ausgabe -RedirectStandardError $fehler
        foreach ($quelle in @($ausgabe, $fehler)) {
            Get-Content $quelle -ErrorAction SilentlyContinue |
                Where-Object { $_.Trim() } |
                ForEach-Object { Log $_ }
        }
        return $prozess.ExitCode
    } finally {
        Remove-Item $ausgabe, $fehler -Force -ErrorAction SilentlyContinue
    }
}

if (Test-Path $LockFile) {
    $age = (Get-Date) - (Get-Item $LockFile).LastWriteTime
    if ($age.TotalMinutes -lt $StaleAfterMinutes) {
        Log "Ein Update laeuft bereits (seit $([int]$age.TotalMinutes) min), dieser Lauf wird uebersprungen."
        exit 0
    }
    Log "Verwaiste Sperrdatei von vor $([int]$age.TotalMinutes) min wird entfernt."
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}

$ngrokGestoppt = $false
try {
    Set-Location $RepoRoot

    # Unter SYSTEM gibt es keinen Desktop: eine Passwortabfrage wuerde ewig haengen.
    $env:GIT_TERMINAL_PROMPT = "0"
    # SYSTEM vertraut einem Repo, das einem anderen Benutzer gehoert, sonst nicht.
    $repoPfad = $RepoRoot -replace '\\', '/'
    $vertraut = @(git config --global --get-all safe.directory)
    if ($vertraut -notcontains $repoPfad) {
        git config --global --add safe.directory $repoPfad
    }

    $code = Invoke-Extern "git" @("fetch", "--quiet", "origin")
    if ($code -ne 0) { throw "git fetch fehlgeschlagen (Exit $code)" }

    $local = git rev-parse HEAD
    $remote = git rev-parse '@{u}'
    if (-not $remote) { throw "Kein Upstream-Branch eingestellt (git branch -u origin/release-1.2)." }
    if ($local -eq $remote) {
        # Kein Eintrag je Lauf - bei 5-min-Takt wuerde das Protokoll sonst zugemuellt.
        exit 0
    }

    Log "--- Update $($local.Substring(0,7)) -> $($remote.Substring(0,7)) ---"
    New-Item -ItemType File -Path $LockFile -Force | Out-Null

    # Eine laufende ngrok.exe ist gesperrt; nur wenn sie sich aendert, kurz anhalten.
    $geaendert = @(git diff --name-only HEAD '@{u}')
    if (($geaendert -contains "ngrok.exe") -and -not $OhneNeustart -and (Get-Service $NgrokServiceName -ErrorAction SilentlyContinue)) {
        Log "ngrok.exe aendert sich - Dienst $NgrokServiceName wird kurz angehalten."
        Stop-Service -Name $NgrokServiceName -Force
        $ngrokGestoppt = $true
    }

    $code = Invoke-Extern "git" @("pull", "--ff-only", "--quiet")
    if ($code -ne 0) { throw "git pull fehlgeschlagen (Exit $code)" }

    $EnvFile = Join-Path $RepoRoot "deploy\server.env.ps1"
    if (Test-Path $EnvFile) { . $EnvFile }

    $Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $Python)) { $Python = "python" }

    # Vor dem Neustart sichern; ohne Sicherung kein Neustart.
    $code = Invoke-Extern $Python @("deploy\sichern.py")
    if ($code -ne 0) { throw "Sicherung fehlgeschlagen (Exit $code), Neustart wird abgebrochen." }

    $code = Invoke-Extern $Python @("-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", "requirements.txt")
    if ($code -ne 0) { throw "pip install fehlgeschlagen (Exit $code)" }

    if ($OhneNeustart) {
        Log "Update eingespielt (ohne Neustart). Stand: $(git rev-parse --short HEAD)"
    } else {
        Restart-Service -Name $ServiceName -Force -ErrorAction Stop
        Log "Update fertig, $ServiceName neu gestartet. Stand: $(git rev-parse --short HEAD)"
    }
} catch {
    Log "FEHLER: $($_.Exception.Message)"
    exit 1
} finally {
    if ($ngrokGestoppt) {
        Start-Service -Name $NgrokServiceName -ErrorAction SilentlyContinue
        Log "Dienst $NgrokServiceName wieder gestartet."
    }
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
