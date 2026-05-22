-- =====================================================
-- PROSODY XMPP SERVER KONFIGURATION
-- Mit OMEMO und allen modernen Sicherheits-Features
-- =====================================================
-- Pfad: /etc/prosody/prosody.cfg.lua
-- Nach Änderungen: sudo systemctl restart prosody
-- =====================================================

-- =====================================================
-- ADMIN EINSTELLUNGEN
-- =====================================================
-- WICHTIG: Hier deine Admin-JID eintragen!
admins = { "admin@acidbrns.cc" }

-- =====================================================
-- MODUL-PFADE
-- =====================================================
plugin_paths = { "/usr/lib/prosody/modules" }

-- =====================================================
-- MODULE AKTIVIEREN
-- =====================================================
-- Alle modernen XMPP-Features + Sicherheit
modules_enabled = {
    -- Basis-Module (RFC 6120/6121)
    "roster";              -- Kontaktliste
    "saslauth";            -- Authentifizierung
    "tls";                 -- TLS/SSL Verschlüsselung
    "dialback";            -- Server-zu-Server Authentifizierung
    "disco";               -- Service Discovery
    "posix";               -- POSIX-Funktionen (Daemonize)
    
    -- Erweiterte Features (XEPs)
    "carbons";             -- Message Carbons (XEP-0280) - Sync zwischen Geräten
    "mam";                 -- Message Archive Management (XEP-0313) - Nachrichten-Archiv
    "csi_simple";          -- Client State Indication (XEP-0352) - Stromsparen
    "cloud_notify";        -- Push-Benachrichtigungen (XEP-0357)
    "smacks";              -- Stream Management (XEP-0198) - Verbindungs-Stabilität
    "blocklist";           -- Blockieren von Kontakten (XEP-0191)
    "bookmarks";           -- Bookmarks (XEP-0402)
    "vcard4";              -- vCard4 (XEP-0292) - Benutzerprofile
    "vcard_legacy";        -- vCard Legacy Support
    
    -- HTTP & Uploads
    "http";                -- HTTP Server
    "http_files";          -- Datei-Server
    "http_upload";         -- HTTP File Upload (XEP-0363) - Dateien senden
    
    -- Verschlüsselung & Sicherheit
    "pep";                 -- Personal Eventing Protocol - Basis für OMEMO!
    "pubsub";              -- Publish-Subscribe - Auch für OMEMO wichtig
    
    -- Spam & Sicherheit
    "limits";              -- Rate Limiting gegen Spam
    "watchregistrations";  -- Benachrichtigung bei neuen Registrierungen
    -- "admin_telnet";      -- Admin-Konsole (deaktiviert: unnötiges Angriffsziel)

    -- Optional: Weitere nützliche Module
    "ping";                -- XMPP Ping (XEP-0199)
    "register";            -- In-Band Registration - DEAKTIVIERT (Web-Reg!)
    "time";                -- Entity Time (XEP-0202)
    "uptime";              -- Server Uptime
    "version";             -- Software Version
    "admin_adhoc";         -- Admin-Befehle via XMPP
}

-- =====================================================
-- MODULE DEAKTIVIEREN
-- =====================================================
modules_disabled = {
    "s2s";                 -- Server-to-Server (falls nur lokaler Server gewünscht)
                           -- WICHTIG: Für Federation MIT anderen Servern: auskommentieren!
}

-- =====================================================
-- REGISTRIERUNG
-- =====================================================
-- Registrierung NUR über Web-Interface erlauben!
allow_registration = false

-- Registrierungen von diesen IPs erlauben (nur localhost für prosodyctl)
registration_whitelist = { "127.0.0.1", "::1" }

-- =====================================================
-- TLS/SSL KONFIGURATION
-- =====================================================
-- Moderne, sichere TLS-Einstellungen

-- TLS erzwingen (nur verschlüsselte Verbindungen)
c2s_require_encryption = true      -- Client-zu-Server
s2s_require_encryption = true      -- Server-zu-Server
s2s_secure_auth = true             -- Nur verifizierte Server

-- TLS-Protokoll Versionen (nur sichere!)
ssl = {
    protocol = "tlsv1_2+";         -- Mindestens TLS 1.2, besser 1.3
    
    -- Sichere Cipher Suites (moderne, starke Verschlüsselung)
    ciphers = "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384";
    
    -- Optionen für maximale Sicherheit
    options = {
        "no_sslv2", "no_sslv3",    -- Alte SSL-Versionen deaktivieren
        "no_tlsv1", "no_tlsv1_1",  -- Alte TLS-Versionen deaktivieren
        "no_ticket",               -- Session Tickets aus
        "no_compression",          -- Kompression aus (gegen CRIME)
        "cipher_server_preference", -- Server bestimmt Cipher
        "single_dh_use",           -- Neuer DH-Key pro Session
        "single_ecdh_use"          -- Neuer ECDH-Key pro Session
    };
}

-- =====================================================
-- PORTS
-- =====================================================
-- Standard XMPP Ports
c2s_ports = { 5222 }               -- Client Connections
s2s_ports = { 5269 }               -- Server-to-Server
http_ports = { 5280 }              -- HTTP (für File Upload)
https_ports = { 5281 }             -- HTTPS

-- Legacy SSL Ports (falls benötigt)
legacy_ssl_ports = { }             -- Leer = deaktiviert

-- =====================================================
-- HTTP FILE UPLOAD
-- =====================================================
-- Damit User Dateien/Bilder senden können

http_upload_file_size_limit = 10485760  -- 10 MB
http_upload_expire_after = 60 * 60 * 24 * 7  -- 7 Tage

http_upload_path = "/var/lib/prosody/http_upload"
http_upload_external_base_url = "https://upload.acidbrns.cc/upload/"

-- =====================================================
-- MESSAGE ARCHIVE MANAGEMENT (MAM)
-- =====================================================
-- Nachrichten-Archiv für Offline-Nachrichten und Sync

archive_expires_after = "1w"       -- Nachrichten nach 1 Woche löschen
                                    -- Alternativen: "1d", "1m", "1y", "never"

max_archive_query_results = 50     -- Max Nachrichten pro Abfrage
default_archive_policy = "roster"  -- Nur Kontakte archivieren
                                    -- Alternativen: "always", "never"

-- =====================================================
-- RATE LIMITING (Anti-Spam)
-- =====================================================
limits = {
    c2s = {
        rate = "10kb/s";           -- Max 10 KB/s pro Client
        burst = "2s";              -- 2 Sekunden Burst
    };
    s2s = {
        rate = "30kb/s";
        burst = "2s";
    };
}

-- =====================================================
-- STORAGE BACKEND
-- =====================================================
-- PostgreSQL für Prosody-interne Daten (optional aber empfohlen!)

storage = "internal"               -- Standard: internes Storage
-- Für PostgreSQL (benötigt prosody-modules):
-- storage = "sql"
-- sql = {
--     driver = "PostgreSQL";
--     database = "prosody";
--     username = "prosody";
--     password = "prosody-db-password";
--     host = "localhost";
-- }

-- =====================================================
-- LOGS
-- =====================================================
log = {
    info = "/var/log/prosody/prosody.log";
    error = "/var/log/prosody/prosody.err";
    -- Für Debugging:
    -- debug = "/var/log/prosody/prosody.debug";
}

-- =====================================================
-- VIRTUAL HOST (DEINE DOMAIN)
-- =====================================================
-- WICHTIG: Hier deine Domain eintragen!

VirtualHost "acidbrns.cc"
    enabled = true
    
    -- SSL-Zertifikate (Let's Encrypt!)
    ssl = {
        key = "/etc/prosody/certs/acidbrns.cc.key";
        certificate = "/etc/prosody/certs/acidbrns.cc.crt";
    }
    
    -- Erlaubte Authentication
    authentication = "internal_hashed"  -- Sichere Hashed Passwords
    
    -- HTTP Upload für diese Domain
    http_host = "acidbrns.cc"

-- =====================================================
-- KOMPONENTEN
-- =====================================================

-- Multi-User-Chat (MUC) - Gruppen-Chats
Component "conference.acidbrns.cc" "muc"
    name = "Chatrooms"
    restrict_room_creation = false
    max_history_messages = 50
    
    modules_enabled = {
        "muc_mam";                 -- Archiv für Gruppenchats
    }

-- File Proxy für HTTP Upload
Component "upload.acidbrns.cc" "http_upload"

-- =====================================================
-- OMEMO HINWEISE
-- =====================================================
--[[
OMEMO (OMEMO Multi-End Message and Object Encryption) ist End-to-End
Verschlüsselung für XMPP. Es ist CLIENT-SEITIG implementiert!

Der Server (Prosody) muss dafür NUR sicherstellen, dass:
1. ✅ PEP aktiviert ist (oben in modules_enabled)
2. ✅ PubSub aktiviert ist (oben in modules_enabled)

Die eigentliche OMEMO-Verschlüsselung macht der XMPP-Client!

Empfohlene Clients mit OMEMO:
- Gajim (Desktop: Windows, Linux, Mac)
- Conversations (Android)
- Siskin IM (iOS)
- Dino (Linux)
- Monal (iOS, macOS)
]]--

-- =====================================================
-- ZUSÄTZLICHE SICHERHEIT
-- =====================================================

-- Account-Inaktivität
-- Inaktive Accounts nach X Tagen löschen (optional)
-- account_purge_after = 90 * 24 * 60 * 60  -- 90 Tage

-- Hostname
daemonize = true
pidfile = "/var/run/prosody/prosody.pid"

-- Statistiken (optional)
-- statistics = "internal"

-- =====================================================
-- ENDE DER KONFIGURATION
-- =====================================================

--[[
WICHTIGE NÄCHSTE SCHRITTE:

1. Domain ersetzen:
   sed -i 's/acidbrns.cc/ECHTE-DOMAIN.de/g' /etc/prosody/prosody.cfg.lua

2. Admin-JID setzen:
   Zeile 12: admins = { "dein-admin@ECHTE-DOMAIN.de" }

3. SSL-Zertifikate mit Let's Encrypt holen:
   sudo certbot certonly --nginx -d ECHTE-DOMAIN.de
   sudo prosodyctl cert import /etc/letsencrypt/live/

4. HTTP Upload Ordner erstellen:
   sudo mkdir -p /var/lib/prosody/http_upload
   sudo chown prosody:prosody /var/lib/prosody/http_upload

5. Prosody starten:
   sudo systemctl restart prosody
   sudo systemctl status prosody

6. Testen:
   sudo prosodyctl check
   sudo prosodyctl about

7. Admin-Account erstellen:
   sudo prosodyctl adduser admin@ECHTE-DOMAIN.de
]]
