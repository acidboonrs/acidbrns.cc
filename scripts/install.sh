#!/bin/bash
# =====================================================
# XMPP Registration System - Automatisches Setup
# Für Raspberry Pi 5 mit Ubuntu Server
# =====================================================

set -e  # Bei Fehler abbrechen

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logo
echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════╗"
echo "║   XMPP Registration System - Automatisches Setup   ║"
echo "║              für Raspberry Pi 5                    ║"
echo "╚════════════════════════════════════════════════════╝"
echo -e "${NC}"

# =====================================================
# Prüfungen
# =====================================================

# Root Check
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Dieses Script muss als root ausgeführt werden!${NC}"
    echo "Bitte verwende: sudo bash install.sh"
    exit 1
fi

# SUDO_USER prüfen (wer hat sudo aufgerufen?)
if [ -z "$SUDO_USER" ]; then
    echo -e "${RED}❌ SUDO_USER nicht gesetzt. Bitte mit 'sudo bash install.sh' ausführen.${NC}"
    exit 1
fi

PROJECT_DIR="/home/${SUDO_USER}/xmpp-acidbrns"

if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${RED}❌ Projektverzeichnis nicht gefunden: $PROJECT_DIR${NC}"
    exit 1
fi

# Betriebssystem Check
if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [[ "$ID" != "ubuntu" ]]; then
        echo -e "${YELLOW}⚠️  Warnung: Dieses Script wurde für Ubuntu entwickelt.${NC}"
        echo -e "${YELLOW}   Du verwendest: $PRETTY_NAME${NC}"
        read -p "Möchtest du trotzdem fortfahren? (j/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Jj]$ ]]; then
            exit 1
        fi
    fi
fi

# =====================================================
# Domain & Email abfragen
# =====================================================

echo -e "\n${BLUE}📝 Konfiguration${NC}"
echo "================================"

# Standard-Domain vorschlagen
DEFAULT_DOMAIN="acidbrns.cc"
read -p "Deine Domain [${DEFAULT_DOMAIN}]: " DOMAIN
DOMAIN=${DOMAIN:-$DEFAULT_DOMAIN}

if [ -z "$DOMAIN" ]; then
    echo -e "${RED}❌ Domain ist erforderlich!${NC}"
    exit 1
fi

read -p "Admin E-Mail (für Let's Encrypt): " ADMIN_EMAIL
if [ -z "$ADMIN_EMAIL" ]; then
    echo -e "${RED}❌ Admin E-Mail ist erforderlich!${NC}"
    exit 1
fi

echo -e "\n${GREEN}✓ Konfiguration:${NC}"
echo "  Domain: $DOMAIN"
echo "  Admin: $ADMIN_EMAIL"

# DNS Check
echo -e "\n${BLUE}🌐 DNS Check...${NC}"
if ping -c 1 "$DOMAIN" &> /dev/null; then
    echo -e "${GREEN}✓ Domain $DOMAIN ist erreichbar!${NC}"
else
    echo -e "${YELLOW}⚠️  Warnung: $DOMAIN ist nicht erreichbar!${NC}"
    echo "  Stelle sicher, dass:"
    echo "  1. DNS A-Record auf diesen Server zeigt"
    echo "  2. Port-Forwarding im Router konfiguriert ist"
    echo "  3. Cloudflare Proxy auf 'DNS only' steht (graue Cloud)"
    echo ""
    read -p "Trotzdem fortfahren? (j/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Jj]$ ]]; then
        exit 1
    fi
fi

read -p "Installation starten? (j/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Jj]$ ]]; then
    exit 1
fi

# =====================================================
# System Update
# =====================================================

echo -e "\n${BLUE}📦 System aktualisieren...${NC}"
apt update -qq
apt upgrade -y -qq

# =====================================================
# Pakete installieren
# =====================================================

echo -e "\n${BLUE}📦 Pakete installieren...${NC}"
echo "  - Nginx, PostgreSQL, Python3, Prosody, Certbot"

DEBIAN_FRONTEND=noninteractive apt install -y -qq \
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
    curl \
    ufw \
    fail2ban \
    htop

echo -e "${GREEN}✓ Pakete installiert${NC}"

# =====================================================
# Firewall konfigurieren
# =====================================================

echo -e "\n${BLUE}🔥 Firewall (UFW) konfigurieren...${NC}"

ufw --force enable
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw allow 5222/tcp comment 'XMPP Client'
ufw allow 5269/tcp comment 'XMPP Server'
ufw allow 5280/tcp comment 'XMPP HTTP Upload'

echo -e "${GREEN}✓ Firewall konfiguriert${NC}"

# =====================================================
# PostgreSQL Setup
# =====================================================

echo -e "\n${BLUE}🗄️  PostgreSQL konfigurieren...${NC}"

# Zufällige Passwörter generieren
DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
PROSODY_DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)

# Datenbanken und User erstellen (minimale Berechtigungen)
sudo -u postgres psql << EOF
-- Web Registration DB
CREATE DATABASE xmpp_registration;
CREATE USER xmpp_web WITH PASSWORD '$DB_PASSWORD';
GRANT CONNECT ON DATABASE xmpp_registration TO xmpp_web;

-- Prosody DB (optional, für später)
CREATE DATABASE prosody;
CREATE USER prosody_db WITH PASSWORD '$PROSODY_DB_PASSWORD';
GRANT CONNECT ON DATABASE prosody TO prosody_db;
EOF

# Datenbank-Schema anwenden (enthält die spezifischen Table/Sequence-Grants)
echo "  Erstelle Tabellen..."
sudo -u postgres psql -d xmpp_registration -f "$PROJECT_DIR/scripts/setup_database.sql" > /dev/null 2>&1

echo -e "${GREEN}✓ PostgreSQL konfiguriert${NC}"

# =====================================================
# Backend Setup
# =====================================================

echo -e "\n${BLUE}🐍 Python Backend einrichten...${NC}"

INSTALL_DIR="/var/www/xmpp-registration"
mkdir -p $INSTALL_DIR

# Backend kopieren
cp -r "$PROJECT_DIR/backend" $INSTALL_DIR/
cp -r "$PROJECT_DIR/frontend" $INSTALL_DIR/

# Virtual Environment erstellen
cd $INSTALL_DIR/backend
python3 -m venv venv
source venv/bin/activate

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# .env Datei erstellen
cat > .env << EOF
# Datenbank
DB_HOST=localhost
DB_NAME=xmpp_registration
DB_USER=xmpp_web
DB_PASSWORD=$DB_PASSWORD
DB_PORT=5432

# XMPP
XMPP_DOMAIN=$DOMAIN
PROSODY_PATH=/usr/bin/prosodyctl
PROSODY_ADMIN=/usr/local/sbin/xmpp-prosody-admin

# Flask
FLASK_DEBUG=False

# Signing-Secrets fuer den Bot-Schutz (Mathe-Captcha + Gate) - automatisch generiert
MATH_CAPTCHA_SECRET=$(openssl rand -hex 32)
TDWALL_SECRET=$(openssl rand -hex 32)
EOF

chmod 600 .env

deactivate

# Berechtigungen
chown -R www-data:www-data $INSTALL_DIR

echo -e "${GREEN}✓ Backend eingerichtet${NC}"

# =====================================================
# Validierter prosodyctl-Wrapper + Sudoers-Regel
# =====================================================

echo -e "\n${BLUE}🔑 Prosody-Wrapper + Sudoers-Regel einrichten...${NC}"

# Validierter Wrapper: erzwingt Username-Charset/-Laenge und feste Domain,
# sodass der www-data->prosody sudo-Zugriff auf genau einen Befehl beschraenkt ist.
install -o root -g root -m 0755 "$PROJECT_DIR/scripts/xmpp-prosody-admin" /usr/local/sbin/xmpp-prosody-admin
# Domain im Wrapper auf die echte Domain setzen
sed -i "s/^DOMAIN=.*/DOMAIN=\"$DOMAIN\"/" /usr/local/sbin/xmpp-prosody-admin

# www-data darf ausschliesslich den Wrapper als prosody-User ausfuehren
echo "www-data ALL=(prosody) NOPASSWD: /usr/local/sbin/xmpp-prosody-admin" \
    > /etc/sudoers.d/xmpp-registration
chmod 440 /etc/sudoers.d/xmpp-registration

# Syntax prüfen
if visudo -cf /etc/sudoers.d/xmpp-registration > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Wrapper + Sudoers-Regel erstellt${NC}"
else
    echo -e "${RED}❌ Sudoers-Regel fehlerhaft! Bitte manuell prüfen.${NC}"
    rm -f /etc/sudoers.d/xmpp-registration
    exit 1
fi

# =====================================================
# Systemd Service für Backend
# =====================================================

echo -e "\n${BLUE}⚙️  Systemd Service erstellen...${NC}"

cat > /etc/systemd/system/xmpp-backend.service << EOF
[Unit]
Description=XMPP Registration Backend
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$INSTALL_DIR/backend
Environment="PATH=$INSTALL_DIR/backend/venv/bin"
ExecStart=$INSTALL_DIR/backend/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 2 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xmpp-backend
systemctl start xmpp-backend

echo -e "${GREEN}✓ Backend Service gestartet${NC}"

# =====================================================
# Prosody konfigurieren
# =====================================================

echo -e "\n${BLUE}💬 Prosody XMPP Server konfigurieren...${NC}"

# Backup der Original-Config
cp /etc/prosody/prosody.cfg.lua /etc/prosody/prosody.cfg.lua.backup

# Neue Config kopieren und Domain ersetzen
sed "s/acidbrns.cc/$DOMAIN/g" "$PROJECT_DIR/config/prosody.cfg.lua" > /etc/prosody/prosody.cfg.lua

# HTTP Upload Verzeichnis erstellen
mkdir -p /var/lib/prosody/http_upload
chown prosody:prosody /var/lib/prosody/http_upload

echo -e "${GREEN}✓ Prosody konfiguriert (SSL-Zertifikate folgen)${NC}"

# =====================================================
# SSL-Zertifikate (Let's Encrypt) — VOR Nginx-SSL-Config
# =====================================================

echo -e "\n${BLUE}🔐 SSL-Zertifikate anfordern (Let's Encrypt)...${NC}"
echo -e "${YELLOW}⚠️  Stelle sicher, dass deine Domain auf diesen Server zeigt!${NC}"

read -p "DNS konfiguriert und bereit? (j/N): " -n 1 -r
echo

if [[ $REPLY =~ ^[Jj]$ ]]; then
    # Nginx kurz stoppen damit certbot Port 80 nutzen kann (standalone-Modus)
    # Verhindert das Problem: Nginx startet nicht wenn SSL-Zertifikate noch fehlen
    systemctl stop nginx 2>/dev/null || true

    certbot certonly --standalone \
        -d $DOMAIN \
        -d upload.$DOMAIN \
        --non-interactive \
        --agree-tos \
        --email $ADMIN_EMAIL

    echo -e "${GREEN}✓ SSL-Zertifikate erhalten${NC}"

    # Zertifikate für Prosody importieren
    prosodyctl cert import /etc/letsencrypt/live/$DOMAIN/

    # Jetzt Nginx mit voller SSL-Config starten
    sed "s/acidbrns.cc/$DOMAIN/g" "$PROJECT_DIR/config/nginx.conf" > /etc/nginx/sites-available/xmpp-registration

    ln -sf /etc/nginx/sites-available/xmpp-registration /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default

    # DH Parameters erstellen (2048 Bit für Pi, dauert ~2-5 Minuten)
    if [ ! -f /etc/nginx/dhparam.pem ]; then
        echo "  Erstelle DH Parameters (kann einige Minuten dauern)..."
        openssl dhparam -out /etc/nginx/dhparam.pem 2048
    fi

    # Domain in den statischen Frontend-Seiten eintragen
    # (Die dynamischen Seiten werden serverseitig gerendert und lesen XMPP_DOMAIN aus der .env)
    for f in datenschutz.html onion.html; do
        [ -f "$INSTALL_DIR/frontend/$f" ] && sed -i "s/acidbrns.cc/$DOMAIN/g" "$INSTALL_DIR/frontend/$f"
    done

    nginx -t && systemctl start nginx
    systemctl restart prosody

    echo -e "${GREEN}✓ Nginx und Prosody gestartet${NC}"
else
    echo -e "${YELLOW}⚠️  SSL-Zertifikate übersprungen${NC}"
    echo "   Später manuell ausführen:"
    echo "   sudo systemctl stop nginx"
    echo "   sudo certbot certonly --standalone -d $DOMAIN -d upload.$DOMAIN --email $ADMIN_EMAIL"
    echo "   sudo prosodyctl cert import /etc/letsencrypt/live/$DOMAIN/"
    echo "   sudo systemctl start nginx"
fi

# Auto-Renewal einrichten
systemctl enable certbot.timer 2>/dev/null || true

# =====================================================
# Admin-Account erstellen
# =====================================================

echo -e "\n${BLUE}👤 Admin-Account erstellen...${NC}"

read -p "Admin-Username: " ADMIN_USER
if [ ! -z "$ADMIN_USER" ]; then
    prosodyctl adduser $ADMIN_USER@$DOMAIN

    # In Prosody Config eintragen
    sed -i "s/admin@$DOMAIN/$ADMIN_USER@$DOMAIN/g" /etc/prosody/prosody.cfg.lua
    systemctl restart prosody

    echo -e "${GREEN}✓ Admin-Account erstellt${NC}"
fi

# =====================================================
# Fail2ban einrichten (Brute-Force Schutz)
# =====================================================

echo -e "\n${BLUE}🛡️  Fail2ban einrichten...${NC}"

cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5

[nginx-http-auth]
enabled = true

[nginx-limit-req]
enabled = true

[sshd]
enabled = true
EOF

systemctl enable fail2ban
systemctl restart fail2ban

echo -e "${GREEN}✓ Fail2ban konfiguriert${NC}"

# =====================================================
# Finale Checks
# =====================================================

echo -e "\n${BLUE}🔍 System-Checks...${NC}"

echo "  Prosody Status:"
prosodyctl check 2>&1 | head -n 5

echo ""
systemctl is-active --quiet nginx && echo -e "  ✓ Nginx läuft" || echo -e "  ✗ Nginx Problem"
systemctl is-active --quiet postgresql && echo -e "  ✓ PostgreSQL läuft" || echo -e "  ✗ PostgreSQL Problem"
systemctl is-active --quiet prosody && echo -e "  ✓ Prosody läuft" || echo -e "  ✗ Prosody Problem"
systemctl is-active --quiet xmpp-backend && echo -e "  ✓ Backend läuft" || echo -e "  ✗ Backend Problem"

# =====================================================
# Passwörter speichern (temporär!)
# =====================================================

CREDENTIALS_FILE="/root/xmpp-credentials.txt"
cat > $CREDENTIALS_FILE << EOF
XMPP Registration System - Zugangsdaten
========================================
Erstellt: $(date)

Domain: $DOMAIN
Admin E-Mail: $ADMIN_EMAIL

PostgreSQL:
-----------
Datenbank: xmpp_registration
User: xmpp_web
Password: $DB_PASSWORD

Prosody DB (optional):
----------------------
Datenbank: prosody
User: prosody_db
Password: $PROSODY_DB_PASSWORD

Backend:
--------
Pfad: $INSTALL_DIR/backend
Config: $INSTALL_DIR/backend/.env

Bot-Schutz: Mathe-Captcha + Honeypot, vollstaendig serverseitig.
Kein externer Dienst noetig; die Signing-Secrets wurden automatisch in
$INSTALL_DIR/backend/.env generiert.
EOF

chmod 600 $CREDENTIALS_FILE

# Datei nach 60 Sekunden automatisch löschen
echo -e "\n${YELLOW}⚠️  Zugangsdaten gespeichert in: $CREDENTIALS_FILE${NC}"
echo -e "${YELLOW}   Die Datei wird in 60 Sekunden automatisch gelöscht!${NC}"
(sleep 60 && rm -f "$CREDENTIALS_FILE" && echo -e "${GREEN}Credentials-Datei automatisch gelöscht.${NC}") &

# =====================================================
# Installation abgeschlossen!
# =====================================================

echo -e "\n${GREEN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║        ✅ Installation erfolgreich abgeschlossen!    ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"

echo -e "\n${BLUE}📋 Wichtige Informationen:${NC}"
echo "================================"
echo "🌐 Webseite:    https://$DOMAIN"
echo "💬 XMPP Domain: $DOMAIN"
echo "📧 Admin:       $ADMIN_EMAIL"
echo ""
echo "🔐 Zugangsdaten (60s bis Auto-Delete):"
echo "   cat $CREDENTIALS_FILE"
echo ""
echo -e "${GREEN}✓ Bot-Schutz (Mathe-Captcha + Honeypot) ist serverseitig aktiv — kein externer Dienst noetig.${NC}"
echo ""
echo "📖 Logs:"
echo "   Backend: journalctl -u xmpp-backend -f"
echo "   Nginx:   tail -f /var/log/nginx/xmpp-registration-error.log"
echo "   Prosody: tail -f /var/log/prosody/prosody.log"
echo ""
echo -e "${GREEN}Viel Erfolg mit deinem XMPP-Server! 🚀${NC}"
