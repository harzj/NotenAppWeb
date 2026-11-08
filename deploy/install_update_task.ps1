# Legt die geplante Aufgabe fuer das Auto-Update an oder stellt sie neu ein.
# Als Administrator ausfuehren:
#   powershell -ExecutionPolicy Bypass -File deploy\install_update_task.ps1
#   ... -IntervalMinutes 10      (anderer Takt)
param(
    [int]$IntervalMinutes = 5,
    [string]$TaskName = "NotenAppUpdate"
)
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $RepoRoot "deploy\update_and_restart.ps1"
if (-not (Test-Path $Script)) { throw "Nicht gefunden: $Script" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Script`"" `
    -WorkingDirectory $RepoRoot

# Takt plus Ausloeser beim Hochfahren. RepetitionDuration ausdruecklich setzen: Bleibt sie leer,
# begrenzen manche Windows-Versionen die Wiederholung auf einen Tag. [TimeSpan]::MaxValue lehnen
# neuere Windows-Versionen ab ("ausserhalb des Bereichs") - 10 Jahre gehen ueberall.
$takt = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$beimStart = New-ScheduledTaskTrigger -AtStartup
$beimStart.Delay = "PT1M"

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Output "Aufgabe '$TaskName' existiert bereits - wird ersetzt."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action `
    -Trigger @($takt, $beimStart) -Principal $principal -Settings $settings `
    -Description "Prueft alle $IntervalMinutes Minuten auf neue Commits und startet den NotenApp-Notfallserver neu." | Out-Null

Write-Output "Aufgabe '$TaskName' eingerichtet: alle $IntervalMinutes Minuten und beim Systemstart."
Write-Output "Naechster Lauf: $((Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime)"
Write-Output ""
Write-Output "Sofort testen:  Start-ScheduledTask -TaskName $TaskName"
Write-Output "Protokoll:      Get-Content deploy\logs\update.log -Tail 30"
