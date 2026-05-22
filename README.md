# 🚀 XMPP Registration System für acidbrns.cc

Komplettes System zur Erstellung und Verwaltung von XMPP-Accounts mit moderner Web-Oberfläche.

**✨ Speziell konfiguriert für: acidbrns.cc mit Cloudflare DNS**

> 🏛️ **Architektur & Security-Design:** [English](ARCHITECTURE.md) · [Deutsch](ARCHITECTURE.de.md)
> — Defense-in-Depth, Edge-Proxy + verschlüsselter Tunnel, self-hosted Bot-Schutz,
> JavaScript-freies, datenschutzfokussiertes Design.

## 🎯 Quick Start

**Lies QUICKSTART.md für die 5-Schritte-Anleitung!**

Oder für Cloudflare-Details: **docs/CLOUDFLARE_SETUP.md**

## 📋 Features

- ✅ Moderne Web-Registrierung in Lemon-Blau/Dunkel Design
- ✅ PostgreSQL Datenbank-Integration
- ✅ Prosody XMPP-Server mit OMEMO-Support
- ✅ Ende-zu-Ende Verschlüsselung (OMEMO)
- ✅ HTTP File Upload (Bilder/Dateien senden)
- ✅ Message Archive Management (MAM)
- ✅ Multi-Device Sync (Carbons)
- ✅ Push-Benachrichtigungen
- ✅ Rate Limiting & Spam-Schutz
- ✅ SSL/TLS mit Let's Encrypt
- ✅ Automatisches Installations-Script

## 🖥️ Systemanforderungen

- **Hardware**: beliebiger Linux-Server (ab ~2 GB RAM)
- **Betriebssystem**: Ubuntu Server 22.04/24.04 LTS
- **Domain**: Eigene Domain mit DNS-Zugriff
- **Ports**: 80, 443, 5222, 5269, 5280 müssen erreichbar sein

## 🎯 Für Anfänger: Was wird installiert?

1. **Nginx** - Webserver für die Registrierungs-Seite
2. **PostgreSQL** - Datenbank für User-Accounts
3. **Python Flask** - Backend-API für Registrierung
4. **Prosody** - XMPP-Server (das Herzstück!)
5. **Let's Encrypt** - Kostenlose SSL-Zertifikate

## 📦 Schnell-Installation (empfohlen)

### Schritt 1: Domain vorbereiten

**Wichtig**: Bevor du installierst, stelle sicher, dass deine Domain auf deinen Server zeigt!

Bei deinem Domain-Anbieter (z.B. Cloudflare, Namecheap):
```
A-Record:     deine-domain.de  →  123.456.789.012 (deine IP)
A-Record:     upload.deine-domain.de  →  123.456.789.012
```

**Deine IP herausfinden**:
```bash
curl ifconfig.me
```

### Schritt 2: Dateien hochladen

Alle Projekt-Dateien auf deinen Server kopieren:
```bash
# Auf deinem Computer: Dateien per SCP hochladen
scp -r xmpp-project/ benutzer@dein-pi:/home/benutzer/

# Oder auf dem Pi: Git Clone (falls auf GitHub)
# git clone https://github.com/dein-repo/xmpp-project.git
```

### Schritt 3: Installation starten

```bash
# Auf dem Server einloggen
ssh benutzer@dein-pi

# Zum Projekt-Ordner wechseln
cd ~/xmpp-project/scripts

# Script ausführbar machen
chmod +x install.sh

# Installation starten (als root!)
sudo bash install.sh
```

Das Script fragt dich nach:
- Deiner Domain (z.B. `meinexmpp.de`)
- Admin E-Mail (für SSL-Zertifikate)

**Dann macht es automatisch**:
- System-Update
- Installation aller Pakete
- Datenbank-Setup
- Backend-Konfiguration
- SSL-Zertifikate anfordern
- Services starten

**Dauer**: Ca. 15-20 Minuten

### Schritt 4: Fertig! 🎉

Öffne im Browser: `https://deine-domain.de`

## 📖 Manuelle Installation (für Lernzwecke)

<details>
<summary>Klicke hier für detaillierte manuelle Schritte</summary>

### 1. System vorbereiten

```bash
# System aktualisieren
sudo apt update && sudo apt upgrade -y

# Pakete installieren
sudo apt install -y \
    nginx \
    postgresql \
    postgresql-contrib \
    python3 \
    python3-pip \
    python3-venv \
    prosody \
    prosody-modules \
    certbot \
    python3-certbot-nginx \
    git \
    curl
```

### 2. PostgreSQL einrichten

```bash
# PostgreSQL-User werden
sudo -u postgres psql

# In der PostgreSQL-Console:
CREATE DATABASE xmpp_registration;
CREATE USER xmpp_web WITH PASSWORD 'dein-sicheres-passwort';
GRANT ALL PRIVILEGES ON DATABASE xmpp_registration TO xmpp_web;
\q

# Datenbank-Schema importieren
sudo -u postgres psql -d xmpp_registration -f scripts/setup_database.sql
```

### 3. Backend installieren

```bash
# Verzeichnis erstellen
sudo mkdir -p /var/www/xmpp-registration
sudo cp -r backend frontend /var/www/xmpp-registration/

# Zum Backend wechseln
cd /var/www/xmpp-registration/backend

# Virtual Environment
python3 -m venv venv
source venv/bin/activate

# Dependencies installieren
pip install -r requirements.txt

# .env Datei erstellen
cp .env.example .env
nano .env  # Hier deine Werte eintragen!

# Berechtigungen
sudo chown -R www-data:www-data /var/www/xmpp-registration
```

### 4. Systemd Service

```bash
# Service-Datei erstellen
sudo nano /etc/systemd/system/xmpp-backend.service
```

Inhalt:
```ini
[Unit]
Description=XMPP Registration Backend
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/xmpp-registration/backend
Environment="PATH=/var/www/xmpp-registration/backend/venv/bin"
ExecStart=/var/www/xmpp-registration/backend/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 4 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Service starten
sudo systemctl daemon-reload
sudo systemctl enable xmpp-backend
sudo systemctl start xmpp-backend
```

### 5. Prosody konfigurieren

```bash
# Backup der Original-Config
sudo cp /etc/prosody/prosody.cfg.lua /etc/prosody/prosody.cfg.lua.backup

# Unsere Config kopieren
sudo cp config/prosody.cfg.lua /etc/prosody/

# Domain ersetzen
sudo sed -i 's/deine-domain.de/ECHTE-DOMAIN.de/g' /etc/prosody/prosody.cfg.lua

# HTTP Upload Ordner
sudo mkdir -p /var/lib/prosody/http_upload
sudo chown prosody:prosody /var/lib/prosody/http_upload
```

### 6. Nginx einrichten

```bash
# DH Parameters erstellen (dauert!)
sudo openssl dhparam -out /etc/nginx/dhparam.pem 2048

# Config kopieren
sudo cp config/nginx.conf /etc/nginx/sites-available/xmpp-registration

# Domain ersetzen
sudo sed -i 's/deine-domain.de/ECHTE-DOMAIN.de/g' /etc/nginx/sites-available/xmpp-registration

# Aktivieren
sudo ln -s /etc/nginx/sites-available/xmpp-registration /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

# Nginx testen
sudo nginx -t
```

### 7. SSL-Zertifikate

```bash
# Certbot ausführen
sudo certbot certonly --nginx \
    -d deine-domain.de \
    -d upload.deine-domain.de \
    --email deine@email.de

# Für Prosody importieren
sudo prosodyctl cert import /etc/letsencrypt/live/deine-domain.de/

# Services neu starten
sudo systemctl restart nginx
sudo systemctl restart prosody
```

### 8. Admin-Account erstellen

```bash
sudo prosodyctl adduser admin@deine-domain.de
# Passwort eingeben wenn gefragt
```

</details>

## 🔧 Nach der Installation

### Services überprüfen

```bash
# Backend Status
sudo systemctl status xmpp-backend

# Prosody Status
sudo systemctl status prosody

# Nginx Status
sudo systemctl status nginx

# PostgreSQL Status
sudo systemctl status postgresql

# Prosody-Check
sudo prosodyctl check
```

### Logs ansehen

```bash
# Backend Logs
sudo journalctl -u xmpp-backend -f

# Prosody Logs
sudo tail -f /var/log/prosody/prosody.log

# Nginx Logs
sudo tail -f /var/log/nginx/xmpp-registration-error.log
```

### Test-Account erstellen

1. Öffne `https://deine-domain.de`
2. Fülle das Formular aus
3. Account wird erstellt!

### XMPP-Client einrichten

**Empfohlene Clients**:
- **Android**: [Conversations](https://conversations.im) (beste OMEMO-Unterstützung!)
- **iOS**: [Siskin IM](https://siskin.im) oder [Monal](https://monal.im)
- **Desktop**: [Gajim](https://gajim.org) (Windows/Linux/Mac)
- **Linux**: [Dino](https://dino.im)

**Account-Einstellungen**:
```
JID: deinname@deine-domain.de
Passwort: (dein Passwort)
Server: deine-domain.de
Port: 5222
Verschlüsselung: STARTTLS oder Direct TLS
```

**OMEMO aktivieren**:
- In den Chat-Einstellungen oder Profil
- "OMEMO-Verschlüsselung" aktivieren
- Fertig! Alle Nachrichten sind jetzt Ende-zu-Ende verschlüsselt 🔒

## 🛡️ Sicherheit

### Firewall (UFW)

```bash
# Firewall Status
sudo ufw status

# Standard-Ports sollten offen sein:
# 22 (SSH), 80/443 (Web), 5222/5269 (XMPP), 5280 (Upload)
```

### Fail2ban

Automatischer Schutz gegen Brute-Force:
```bash
sudo systemctl status fail2ban
sudo fail2ban-client status
```

### SSL-Zertifikate erneuern

Certbot erneuert automatisch! Manueller Test:
```bash
sudo certbot renew --dry-run
```

## 📊 Datenbank-Verwaltung

### PostgreSQL Console

```bash
sudo -u postgres psql -d xmpp_registration
```

Nützliche Befehle:
```sql
-- Alle User anzeigen
SELECT username, domain, email, created_at FROM xmpp_users;

-- Anzahl User
SELECT COUNT(*) FROM xmpp_users;

-- Registrierungen heute
SELECT COUNT(*) FROM xmpp_users 
WHERE DATE(created_at) = CURRENT_DATE;

-- Inaktive User löschen (älter als 90 Tage, nicht verifiziert)
DELETE FROM xmpp_users 
WHERE email_verified = FALSE 
AND created_at < CURRENT_TIMESTAMP - INTERVAL '90 days';
```

## 🔄 Updates & Wartung

### Backend updaten

```bash
cd /var/www/xmpp-registration/backend
source venv/bin/activate
pip install --upgrade -r requirements.txt
sudo systemctl restart xmpp-backend
```

### Prosody updaten

```bash
sudo apt update
sudo apt upgrade prosody
sudo systemctl restart prosody
```

### Alte Logs bereinigen

```bash
# Alte Registration-Logs (älter als 90 Tage)
sudo -u postgres psql -d xmpp_registration << EOF
DELETE FROM registration_logs 
WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '90 days';
EOF
```

## 🐛 Problemlösung

### Backend startet nicht

```bash
# Logs prüfen
sudo journalctl -u xmpp-backend -n 50

# Manuell starten zum Testen
cd /var/www/xmpp-registration/backend
source venv/bin/activate
python app.py
```

### Prosody Probleme

```bash
# Config prüfen
sudo prosodyctl check

# Logs ansehen
sudo tail -n 100 /var/log/prosody/prosody.err

# Neu starten
sudo systemctl restart prosody
```

### Datenbank-Verbindung

```bash
# Testen
sudo -u postgres psql -d xmpp_registration -c "SELECT 1;"

# .env Datei prüfen
sudo cat /var/www/xmpp-registration/backend/.env
```

### SSL-Zertifikat Fehler

```bash
# Zertifikat prüfen
sudo certbot certificates

# Manuell erneuern
sudo certbot renew

# Für Prosody neu importieren
sudo prosodyctl cert import /etc/letsencrypt/live/DOMAIN/
```

## 📚 Weitere Ressourcen

- [Prosody Dokumentation](https://prosody.im/doc/)
- [XMPP Standards](https://xmpp.org/extensions/)
- [OMEMO Spezifikation](https://conversations.im/omemo/)
- [PostgreSQL Docs](https://www.postgresql.org/docs/)
- [Flask Dokumentation](https://flask.palletsprojects.com/)

## ❓ FAQ

**Q: Kann ich mehrere Domains hosten?**
A: Ja! Füge weitere `VirtualHost` Einträge in prosody.cfg.lua hinzu.

**Q: Wie viele User kann mein Server verkraften?**
A: Locker 100-500 aktive User, je nach Nutzung.

**Q: Funktioniert OMEMO out-of-the-box?**
A: Ja! Die Prosody-Config hat PEP und PubSub aktiviert. Clients müssen nur OMEMO aktivieren.

**Q: Wo sind die Nachrichten gespeichert?**
A: OMEMO-verschlüsselt in Prosody's MAM (Message Archive). Nur der Empfänger kann sie lesen!

**Q: Kann ich mit anderen XMPP-Servern kommunizieren?**
A: Ja! Das ist der Vorteil von XMPP - dezentral wie E-Mail.

## 📝 Lizenz

MIT License - siehe LICENSE Datei

## 🤝 Support

Bei Fragen oder Problemen:
1. Logs prüfen (siehe Problemlösung)
2. Prosody Check: `sudo prosodyctl check`
3. Issue auf GitHub erstellen

---

**Viel Erfolg mit deinem XMPP-Server! 🚀**

Erstellt mit ❤️ und Lemon-Blau 🔵
