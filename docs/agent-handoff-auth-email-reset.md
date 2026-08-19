# Agent Handoff: Auth mit Mail-Bestaetigung und Passwort-Reset

## Zielbild
Login ist nur erlaubt, wenn beide Bedingungen erfuellt sind:
1. E-Mail-Adresse bestaetigt
2. Admin-Freigabe aktiv

Zusatz:
- Sicherer Passwort-Reset per Mail-Link

## Festgelegte Entscheidungen
- Admin-Freigabe bleibt Pflicht.
- E-Mail-Bestaetigung ist zusaetzlich Pflicht.
- Login-Identifier bleibt Benutzername.
- Erlaubte Dienstmailstruktur: <kuerzel>@schule.saarland

## Umsetzung in Reihenfolge

### 1) Datenmodell erweitern
Datei: app/models.py
- Feld `email_verified_at` (nullable DateTime) in `User` aufnehmen.
- Optional: `verification_sent_at`, `password_reset_requested_at`.

Migration:
- Da kein Alembic vorhanden ist: idempotentes SQL/Update-Skript fuer bestehende DB vorsehen.

### 2) Config fuer Mail und Token
Datei: app/config.py
- Neue Variablen:
  - MAIL_HOST
  - MAIL_PORT
  - MAIL_USE_TLS
  - MAIL_USERNAME
  - MAIL_PASSWORD
  - MAIL_FROM
  - MAIL_REPLY_TO
  - MAIL_SUPPRESS_SEND
  - EMAIL_VERIFY_TOKEN_TTL_SECONDS (Empfehlung 86400)
  - PASSWORD_RESET_TOKEN_TTL_SECONDS (Empfehlung 1800-3600)
  - ALLOWED_EMAIL_PATTERN (z. B. `^[^@\\s]+@schule\\.saarland$`)

### 3) Mail- und Token-Helper
Neue Datei(n), z. B.:
- app/auth/tokens.py
- app/auth/mailer.py

Vorgaben:
- Signierte Tokens mit Zweckbindung (separate salts):
  - verify-email
  - reset-password
- Robust gegen abgelaufene/ungueltige Tokens.
- Keine Tokens im Log ausgeben.
- Absolute URLs mit PUBLIC_BASE_URL / PREFERRED_URL_SCHEME erzeugen.

### 4) Auth-Routen erweitern
Datei: app/auth/routes.py

Registrierung:
- Dienstmail validieren.
- User mit `is_approved=False`, `email_verified_at=None` anlegen.
- Verifikationsmail senden.
- Erfolgstext: erst Mail bestaetigen, dann Admin-Freigabe.

Neue Routen:
- GET /auth/verify-email/<token>
  - Token pruefen, `email_verified_at` setzen, sinnvolle Flash-Meldung.
- POST /auth/resend-verification
  - Fuer noch unbestaetigte Konten, mit Rate-Limit.
- GET/POST /auth/forgot-password
  - Immer neutrale Rueckmeldung (keine User-Enumeration).
- GET/POST /auth/reset-password/<token>
  - Token pruefen, neues Passwort setzen.

Login:
- Vor `login_user` pruefen:
  - wenn `email_verified_at is None`: blocken + Hinweis
  - wenn `not is_approved`: blocken + Hinweis

### 5) Formulare erweitern
Datei: app/auth/forms.py
- ForgotPasswordForm (EmailField)
- ResetPasswordForm (new_password, new_password2)
- Optional ResendVerificationForm (EmailField)
- E-Mail-Validator fuer Dienstmailregel.

### 6) Templates anpassen
Dateien:
- app/templates/auth/login.html
- app/templates/auth/register.html
- app/templates/auth/admin_users.html

Anpassungen:
- Login: Link "Passwort vergessen".
- Optional Link "Verifikationsmail erneut senden".
- Register: Hinweise auf 2-stufige Freigabe.
- Admin-Users: Mail-Statusspalte (bestaetigt/ausstehend + Zeitstempel).

### 7) Missbrauchsschutz
Datei: app/auth/routes.py
- Rate-Limits fuer:
  - register
  - resend-verification
  - forgot-password
  - reset-password

### 8) Deployment-Doku erweitern
Datei: DEPLOYMENT_LANDKREIS.md
- SMTP-Parameter und notwendige Landkreis-Inputs dokumentieren.
- Secrets-Handling und externe URL fuer Mail-Links aufnehmen.

## Akzeptanzkriterien (Definition of Done)
1. Registrierung mit gueltiger Dienstmail sendet Verifikationsmail.
2. Login vor Mail-Bestaetigung ist gesperrt.
3. Login nach Mail-Bestaetigung, aber ohne Admin-Freigabe ist gesperrt.
4. Login nach Mail-Bestaetigung und Admin-Freigabe ist moeglich.
5. Registrierung mit Nicht-Dienstmail wird abgelehnt.
6. Verifikationsmail kann erneut gesendet werden (rate-limitiert).
7. Forgot-Password liefert fuer existierende/nicht-existierende Mail gleiche Antwort.
8. Reset funktioniert nur mit gueltigem, nicht abgelaufenem Token.

## Externe Abhaengigkeiten (Landkreis)
1. Technische Absenderadresse fuer App bereitstellen.
2. SMTP-Endpunkt + TLS/Auth + Netzfreigabe bereitstellen.
3. Produktive externe URL festlegen (fuer absolute Links).
4. SPF/DKIM/DMARC fuer Absenderdomain absichern.
5. Secrets sicher verwalten (`SECRET_KEY`, SMTP-Credentials).

## Out of Scope
- SSO/LDAP/AD
- Rollenmodell-Umbau
- Vollstaendige Auth-Neuentwicklung
