# NotenApp Deployment beim Landkreis

Dieses Dokument beschreibt die Vorbereitung für den Betrieb hinter einer extern verwalteten Adresse (Domain/Reverse Proxy), ohne den bisherigen lokalen/ngrok-Workflow zu verlieren.

## Zielbild

Die App läuft auf einem internen Port (Standard 5000). Der Landkreis stellt die externe Erreichbarkeit bereit, z. B. über Reverse Proxy und TLS.

## Bereits im Code vorbereitet

1. Environment-basierte Server-Konfiguration in app/config.py
2. Optionales Reverse-Proxy-Handling (ProxyFix) in app/__init__.py
3. Konfigurierbarer Host/Port im Startskript run.py
4. ngrok im Tray-Launcher als Feature-Flag steuerbar in tray.py

## Wichtige Umgebungsvariablen

### App-Betrieb

- FLASK_ENV: development oder production
- NOTENAPP_HOST: Standard 0.0.0.0
- NOTENAPP_PORT: Standard 5000
- SECRET_KEY: in Produktion setzen (lang, zufaellig)
- DATABASE_URL: z. B. postgresql://... oder sqlite:///...

### Reverse Proxy

- TRUST_PROXY: true wenn ein Reverse Proxy davor steht
- PROXY_FIX_X_FOR: Standard 1
- PROXY_FIX_X_PROTO: Standard 1
- PROXY_FIX_X_HOST: Standard 1
- PROXY_FIX_X_PORT: Standard 1
- PROXY_FIX_X_PREFIX: Standard 0
- PREFERRED_URL_SCHEME: in Produktion meist https

### Session/Cookies

- SESSION_COOKIE_NAME: Standard notenapp_session
- SESSION_COOKIE_DOMAIN: optional, z. B. noten.landkreis.de

### Tray/ngrok (lokaler Betrieb)

- NGROK_ENABLED: Standard true (nur im nicht-frozen Modus)
- NGROK_DOMAIN: bisherige ngrok Domain
- NGROK_EXE: optionaler Pfad zu ngrok.exe

## Empfohlene Einstellungen beim Landkreis

1. FLASK_ENV=production
2. TRUST_PROXY=true
3. PREFERRED_URL_SCHEME=https
4. SECRET_KEY als Secret verwalten
5. SESSION_COOKIE_DOMAIN auf die produktive Domain setzen
6. DATABASE_URL auf die zentrale Produktivdatenbank setzen
7. NGROK_ENABLED=false

## Update per Webhook: App neu starten

Nach jedem `git pull` muss die Python-App neu gestartet werden, sonst laeuft der alte Code mit neuen Templates weiter
(Fehler wie `BuildError: Could not build url for endpoint ...`). Unter Plesk/Passenger als zusaetzliche Bereitstellungsaktion:

```
mkdir -p tmp && touch tmp/restart.txt
```

## Anmelden mit Notendatei (Notfallserver)

Exportierte Notendateien (mit Passwort) enthalten einen signierten Zugriffsschluessel. Damit koennen sich Kollegen bei
einem Ausfall am Notfallserver (Notfall-exe) direkt mit ihrer Datei anmelden. Der Landkreis-Server schreibt den
Schluessel nur, er nimmt selbst keine Datei-Anmeldung an.

Einmalige Einrichtung:

1. Die Notfall-exe legt beim ersten Start selbst einen Schluessel an:
   `%LOCALAPPDATA%\NotenApp\dateilogin.key` (Tray-Menue "Datei-Login-Schluessel anzeigen").
   Alternativ selbst erzeugen mit `python -c "import secrets; print(secrets.token_urlsafe(48))"` und dort ablegen
   (auch `dateilogin.key.txt`, UTF-8 oder UTF-16 werden gelesen).
2. Diesen Wert beim Landkreis als Umgebungsvariable `FILE_LOGIN_KEY` setzen (und App neu starten).

Der Schluessel gehoert nicht ins Repository und nicht in die exe. Ein neuer Schluessel macht alle alten Dateien als
Anmeldung ungueltig (die Noten bleiben lesbar); so laesst sich der Zugang im Notfall fuer alle sperren.

## Zugangslinks (Einladung, Passwort neu setzen)

Im Admin-Menue erzeugt "Einladungslink erzeugen" einen Link, mit dem sich ein Kollege selbst ein Konto anlegt
(sofort freigeschaltet). Der Schluessel-Button je Benutzer erzeugt einen Link zum Neusetzen des Passworts.
Links sind 14 Tage gueltig und auf jedem Server nur einmal nutzbar (Tabelle `used_zugangslinks`, wird automatisch
angelegt). Ist `FILE_LOGIN_KEY` gesetzt, funktionieren die Links beim Landkreis und am Notfallserver.
Fuer korrekte Adressen im Link ggf. `PUBLIC_BASE_URL` setzen (die Notfall-exe nimmt automatisch die ngrok-Domain).

## Notfall-exe: Datenordner

Die exe legt Benutzerdatenbank, Sessions, `secret_key`, `admin_passwort.txt` und `dateilogin.key` in
`%LOCALAPPDATA%\NotenApp\` ab (abweichend per Umgebungsvariable `NOTENAPP_DATA_DIR`). Neue Builds in anderen
Ordnern finden die Benutzer dadurch wieder. Eine alte `instance/` neben der exe wird beim ersten Start einmalig
uebernommen. Auf einem frischen Datenordner bekommt der Admin ein zufaelliges Passwort (Tray-Menue
"Admin-Passwort anzeigen").

## Notfallserver mit Auto-Update (Windows-Dienst statt exe)

Der Notfallserver kann statt der Notfall-exe direkt aus dem Quellcode laufen (Branch `release-1.2`).
Eine geplante Aufgabe prueft alle 5 Minuten, ob es auf GitHub neue Commits gibt, holt sie, sichert die
Daten und startet die App neu. Die exe-Builds fuer Kolleginnen und Kollegen (`build.py`) bleiben davon
unberuehrt.

- `NOTENAPP_NOTFALL=1` schaltet im Quellcode-Betrieb dasselbe Verhalten ein wie die Notfall-exe:
  Datenordner aus `NOTENAPP_DATA_DIR`, eigener `secret_key`, `dateilogin.key`, zufaelliges Admin-Passwort,
  Anmelden mit Notendatei, kein Update-Hinweis, kein Debug-Modus.
- Dienst `NotenAppServer`: `deploy\start_server.ps1` -> `run_prod.py` (waitress), Protokoll `deploy\logs\server.log`.
  Zugangslinks zeigen auf `https://<NGROK_DOMAIN>` (oder `PUBLIC_BASE_URL`).
- Dienst `NotenAppNgrok`: `deploy\start_ngrok.ps1`, eigener Dienst, damit der Tunnel bei Updates stehen bleibt.
  Protokoll `deploy\logs\ngrok.log`.
- Beide Dienste starten beim Hochfahren automatisch (verzoegert, ohne Anmeldung); NSSM startet sie nach einem
  Absturz nach 10 s neu.
- Aufgabe `NotenAppUpdate` (SYSTEM, alle 5 min und beim Systemstart): `deploy\update_and_restart.ps1`.
  Protokoll `deploy\logs\update.log` (nur Laeufe mit Update oder Fehler).
- Vor jedem Neustart sichert `deploy\sichern.py` `app.db`, `secret_key` und `dateilogin.key` nach
  `<Datenordner>\backups\` (optional zusaetzlich nach `SICHERUNG_ZIEL`).

Alles, was auf `release-1.2` gepusht wird, ist also nach spaetestens 5 Minuten auf dem Notfallserver live.

### Einmalige Einrichtung auf dem Server (PowerShell als Administrator)

1. Bisherige Notfall-exe ueber das Tray-Menue beenden und aus dem Autostart nehmen.
2. Daten der exe uebernehmen (Benutzer und Schluessel bleiben gueltig). Als der Windows-Benutzer ausfuehren,
   unter dem die exe lief:
   ```powershell
   robocopy "$env:LOCALAPPDATA\NotenApp" C:\NotenAppDaten /E /XD sessions
   ```
   Die ngrok-Konfiguration mit Authtoken ebenfalls dorthin kopieren (`ngrok config check` zeigt den Pfad),
   z. B. nach `C:\NotenAppDaten\ngrok.yml` – der Dienst laeuft als SYSTEM und findet die Datei im
   Benutzerprofil nicht.
3. Repository und Python-Umgebung:
   ```powershell
   git clone -b release-1.2 https://github.com/harzj/NotenAppWeb C:\NotenAppWeb
   cd C:\NotenAppWeb
   py -3.10 -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   copy deploy\server.env.ps1.example deploy\server.env.ps1   # Pfade/Domain pruefen
   ```
4. Dienste und Auto-Update einrichten (NSSM muss installiert sein, sonst `-Nssm <Pfad>`):
   ```powershell
   powershell -ExecutionPolicy Bypass -File deploy\install_services.ps1
   powershell -ExecutionPolicy Bypass -File deploy\install_update_task.ps1
   ```
5. Pruefen: `Get-Service NotenApp*` zeigt beide als Running, `http://localhost:5000` und die ngrok-Adresse
   antworten. Einmal neu starten, ohne sich anzumelden – danach muss beides wieder erreichbar sein.

Fehlersuche: `Get-Content deploy\logs\server.log -Tail 50` (Tracebacks der App),
`Get-Content deploy\logs\update.log -Tail 30`, Update sofort ausloesen mit
`Start-ScheduledTask NotenAppUpdate`.

## Fragen an den Landkreis

1. Welches Hosting-Modell wird genutzt: VM, Container, Kubernetes, IIS, Nginx, Apache?
2. Wer terminiert TLS und verwaltet Zertifikate?
3. Welche feste externe Domain wird verwendet?
4. Werden die Header X-Forwarded-For, X-Forwarded-Proto, X-Forwarded-Host gesetzt?
5. Gibt es ein URL-Praefix hinter dem Proxy, z. B. /notenapp?
6. Welche Datenbank wird bereitgestellt und wie erfolgt Backup/Restore?
7. Wie werden Secrets gespeichert und rotiert?
8. Wie sehen Logging, Monitoring und Alarmierung aus?
9. Wer fuehrt Deployments und DB-Migrationen aus?
10. Welche Datenschutz- und Zugriffsvorgaben gelten (Rollen, Aufbewahrung, Loeschkonzept)?

## Nutzerverwaltung und Sicherheit

1. Nutzer liegen in der Tabelle users (SQLAlchemy-Modell app/models.py)
2. Passwoerter werden gehasht gespeichert (werkzeug.security), nicht im Klartext
3. Transportverschluesselung erfolgt ueber HTTPS am Proxy oder in der App
4. Datenverschluesselung im Ruhezustand ist Infrastruktur-/DB-Thema und sollte mit dem Landkreis abgestimmt werden

## GitHub und Datenbank

Ein Push nach GitHub erstellt keine Nutzerdatenbank.

- GitHub enthaelt den Code.
- Eine neue DB entsteht nur, wenn beim Deployment eine neue Datenbank instanziiert wird.
- Bestehende Nutzer bleiben nur erhalten, wenn die bisherige Datenbank migriert/uebernommen wird.

## Kurzer Go-Live-Check

1. App intern erreichbar auf NOTENAPP_HOST/NOTENAPP_PORT
2. Externe Domain zeigt auf Reverse Proxy
3. HTTPS aktiv
4. Login, Session, Dateiupload getestet
5. Backup und Restore-Test protokolliert
