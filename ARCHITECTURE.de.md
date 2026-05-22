# Architektur & Security-Design

🌐 [English](ARCHITECTURE.md) · **Deutsch**

Selbst gehostete XMPP-Account-Bereitstellung für **acidbrns.cc**. Nutzer
registrieren sich selbst über ein Web-Formular; das Backend legt jeden Account
atomar in PostgreSQL **und** im Prosody-XMPP-Server an. Das System ist
konsequent datenschutz- und sicherheitsorientiert gebaut.

> Dieses Dokument beschreibt das Design auf konzeptioneller Ebene. Konkrete
> Netzdetails (Adressen, Subnetze, Host-Spezifika) sind bewusst ausgelassen.

## Request-Flow (Überblick)

Ein gehärteter **Edge-Reverse-Proxy** terminiert TLS und leitet Anfragen über
einen **verschlüsselten Tunnel (WireGuard)** an ein isoliertes Backend weiter.
Der Backend-Origin ist nie direkt aus dem öffentlichen Internet erreichbar.

```
Client ──TLS──▶ Edge-Proxy (nginx) ──verschlüsselter Tunnel──▶ Backend
                                                               ├─ nginx
                                                               ├─ Flask-App (gunicorn, nur localhost)
                                                               ├─ PostgreSQL (nur localhost)
                                                               └─ Prosody (XMPP)
```

Dieselbe Anwendung ist zusätzlich als **Tor-Onion-Service** erreichbar — für
einen Zugang ohne Verbindungs-Metadaten.

## Komponenten

| Schicht | Aufgabe |
|---------|---------|
| Edge-Proxy | TLS-Terminierung, Security-Header, statische Dateien, echte Client-IP-Weitergabe |
| App | Flask, **serverseitig gerendert, JavaScript-frei**; läuft unter gunicorn, nur an localhost gebunden |
| Datenbank | PostgreSQL, nur localhost, **verschlüsselt im Ruhezustand** |
| XMPP | Prosody mit `internal_hashed`-Auth, erzwungene Verschlüsselung für c2s/s2s |

## Security-Design (Defense in Depth)

### Transport & Header
- Nur TLS 1.2/1.3; **HSTS mit Preload**.
- Strikte **Content-Security-Policy** (`default-src 'none'` in der App), dazu
  `X-Frame-Options`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`.
- Edge/Origin-Trennung — das Backend ist nicht direkt erreichbar.

### Bot-Schutz (selbst gehostet, ohne Drittanbieter)
- Server-signiertes, **einmalig nutzbares Mathe-Captcha** plus verstecktes **Honeypot**-Feld.
- Kein Cloudflare, kein Google, **kein JavaScript** — funktioniert in Text-Browsern
  und im „Safest"-Modus des Tor Browsers.
- Ein leichtgewichtiges Gate bremst automatisiertes Abklopfen, bevor das Formular erreicht wird.

### Anwendungssicherheit
- **Allowlist-Eingabevalidierung**; sämtliches SQL ist **parametrisiert** (keine String-Konkatenation).
- Passwörter mit **bcrypt** (Cost 12) gehasht; XMPP-seitig `internal_hashed`.
- **Fail-closed**-Captcha-Prüfung; **generische Antworten** gegen Username-/E-Mail-Enumeration.
- Passwort-Reset über **hochentropische Einmal-Tokens** mit kurzer Gültigkeit.

### Least Privilege
- Ein dedizierter, unprivilegierter Service-User betreibt die App.
- Privilegierte Account-Operationen (anlegen/passwd/löschen) laufen über einen
  **validierten Wrapper**: feste Domain, geprüfter Username-Zeichensatz/-Länge,
  keine Shell, keine Argument-Injection — freigegeben über genau eine eng
  gefasste `sudo`-Regel.
- Secrets liegen in einer Environment-Datei (`0600`, nie committet); Dotfiles und
  Backup-Dateien werden am Proxy blockiert.

### Missbrauchs-Handling & Monitoring
- **DB-basiertes Rate-Limiting und IP-Banning** (konsistent über alle Worker).
- `fail2ban` auf dem Host; **minimales Logging** mit kurzer Aufbewahrung.

### Daten im Ruhezustand & E-Mail
- Die Datenbank liegt auf einem **verschlüsselten Volume**, das nach dem Boot manuell entsperrt wird.
- Passwort-Reset-Mails gehen über authentifiziertes SMTP; die Domain ist per
  **SPF, DKIM und DMARC** abgesichert.

## Datenschutz-Haltung
- Keine Drittanbieter-Skripte, kein Analytics, keine Tracking-Cookies — nur ein
  einzelnes technisch notwendiges First-Party-Cookie für das Bot-Gate.
- Tor-Onion-Service; Nutzer werden ermutigt, über Tor zu verbinden, sodass
  serverseitig keine Verbindungs-Metadaten (IP, Standort, ISP) zurückbleiben.

## Threat-Model (Kurzfassung)
- **Im Scope:** Web-Missbrauch (Bots, Enumeration, Injection, XSS), Schutz der
  Zugangsdaten, Least-Privilege-Eindämmung, Transportsicherheit, Metadaten-Minimierung.
- **Außerhalb des Scopes / nicht beansprucht:** globale Traffic-Analyse-Angreifer,
  Kompromittierung des Endgeräts des Nutzers.
