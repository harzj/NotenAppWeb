# NotenApp

## Lokale Version zum Herunterladen (Windows)

**[NotenApp.exe herunterladen (Version 1.2.2, lokal)](https://github.com/harzj/NotenAppWeb/raw/main/dist/NotenApp_Lokal_v1.2.2/NotenApp.exe)**

Diese Version läuft nur auf Ihrem eigenen PC. Sie braucht keinen Server und keine Installation.
Ihre Daten bleiben auf Ihrem Rechner.

### Starten

1. `NotenApp.exe` herunterladen und in einen beliebigen Ordner legen (z. B. `Dokumente\NotenApp`).
2. Doppelklick auf `NotenApp.exe`.
   - Windows zeigt eventuell „Der Computer wurde durch Windows geschützt“. Dann auf
     **Weitere Informationen → Trotzdem ausführen** klicken. Die Datei ist nicht signiert.
   - Fragt die Windows-Firewall nach Netzwerkzugriff, können Sie **Abbrechen** wählen.
     Die App funktioniert trotzdem auf diesem PC.
3. Nach ein paar Sekunden öffnet sich der Browser mit `http://localhost:5000`.
4. Unten rechts in der Taskleiste erscheint ein NotenApp-Symbol. Über dessen Menü können Sie:
   - die App erneut im Browser öffnen,
   - das **Admin-Passwort anzeigen** (für die erste Anmeldung),
   - den Datenordner öffnen,
   - die App beenden.

### Wo liegen die Daten?

Benutzer, Klassen und Noten speichert die App in `%LOCALAPPDATA%\NotenApp`
(z. B. `C:\Users\<Name>\AppData\Local\NotenApp`). Eine neuere `NotenApp.exe` findet diese
Daten wieder. Für eine Sicherung diesen Ordner kopieren.

### Hinweise

- Die App läuft nur, solange das Taskleisten-Symbol aktiv ist. Zum Beenden: Rechtsklick auf das
  Symbol → **Beenden**.
- Ist Port 5000 schon von einem anderen Programm belegt, funktioniert die App nicht. Dann dieses Programm schließen oder den
  Port über die Umgebungsvariable `NOTENAPP_PORT` ändern.
- Die lokale Version enthält keinen ngrok-Tunnel. Andere Personen können also nicht über das
  Internet darauf zugreifen.
