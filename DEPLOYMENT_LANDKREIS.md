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
