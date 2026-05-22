-- =====================================================
-- XMPP Registration Datenbank Setup
-- =====================================================
-- Dieses Script erstellt alle benötigten Tabellen
-- Ausführen mit: psql -U postgres -f setup_database.sql
-- =====================================================

-- Datenbank erstellen (falls noch nicht vorhanden)
-- CREATE DATABASE xmpp_registration;

-- Mit Datenbank verbinden
\c xmpp_registration

-- Erweiterungen aktivieren
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- 1. HAUPTTABELLE: xmpp_users
-- =====================================================
-- Speichert alle registrierten XMPP-Accounts

CREATE TABLE IF NOT EXISTS xmpp_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    domain VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    registration_ip INET,
    email_verified BOOLEAN DEFAULT FALSE,
    
    -- Constraints
    CONSTRAINT unique_jid UNIQUE(username, domain),
    CONSTRAINT unique_email UNIQUE(email),
    CONSTRAINT valid_username CHECK (char_length(username) >= 3 AND char_length(username) <= 32)
);

-- Kommentare für Dokumentation
COMMENT ON TABLE xmpp_users IS 'Haupttabelle für alle registrierten XMPP-Accounts';
COMMENT ON COLUMN xmpp_users.username IS 'XMPP Username (vor dem @)';
COMMENT ON COLUMN xmpp_users.domain IS 'XMPP Domain (nach dem @)';
COMMENT ON COLUMN xmpp_users.password_hash IS 'Bcrypt-Hash des Passworts';
COMMENT ON COLUMN xmpp_users.email IS 'Optional: Email für Account-Wiederherstellung';
COMMENT ON COLUMN xmpp_users.registration_ip IS 'IP-Adresse bei Registrierung';

-- =====================================================
-- 2. TABELLE: email_verification
-- =====================================================
-- Tokens für Email-Verifikation

CREATE TABLE IF NOT EXISTS email_verification (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES xmpp_users(id) ON DELETE CASCADE,
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP,
    
    CONSTRAINT valid_token CHECK (char_length(token) >= 32)
);

COMMENT ON TABLE email_verification IS 'Verifikations-Tokens für Email-Bestätigung';
COMMENT ON COLUMN email_verification.token IS 'Einmaliger Verifikations-Token';
COMMENT ON COLUMN email_verification.expires_at IS 'Token läuft ab nach 24 Stunden';

-- =====================================================
-- 3. TABELLE: registration_logs
-- =====================================================
-- Logging aller Registrierungsaktivitäten

CREATE TABLE IF NOT EXISTS registration_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES xmpp_users(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL,
    ip_address INET NOT NULL,
    user_agent TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);

COMMENT ON TABLE registration_logs IS 'Log aller Registrierungs- und Login-Versuche';
COMMENT ON COLUMN registration_logs.action IS 'Art der Aktion: registration, login, password_reset, etc.';

-- =====================================================
-- 4. TABELLE: banned_ips (Optional: Anti-Spam)
-- =====================================================
-- IPs die wegen Missbrauch gesperrt wurden

CREATE TABLE IF NOT EXISTS banned_ips (
    id SERIAL PRIMARY KEY,
    ip_address INET UNIQUE NOT NULL,
    reason TEXT,
    banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    banned_until TIMESTAMP,
    permanent BOOLEAN DEFAULT FALSE
);

COMMENT ON TABLE banned_ips IS 'Gesperrte IP-Adressen (Anti-Spam)';

-- =====================================================
-- INDEXES für bessere Performance
-- =====================================================

-- Für schnelle Username-Suche
CREATE INDEX IF NOT EXISTS idx_username_domain ON xmpp_users(username, domain);

-- Für Email-Lookup
CREATE INDEX IF NOT EXISTS idx_email ON xmpp_users(email) WHERE email IS NOT NULL;

-- Für Registrierungs-Statistiken
CREATE INDEX IF NOT EXISTS idx_created_at ON xmpp_users(created_at);

-- Für Rate Limiting
CREATE INDEX IF NOT EXISTS idx_registration_ip_time ON registration_logs(ip_address, timestamp);

-- Für Token-Lookup
CREATE INDEX IF NOT EXISTS idx_verification_token ON email_verification(token) WHERE verified_at IS NULL;

-- =====================================================
-- VIEWS für einfachere Abfragen
-- =====================================================

-- Aktive User mit vollständiger JID
CREATE OR REPLACE VIEW active_users AS
SELECT 
    id,
    username || '@' || domain AS jid,
    email,
    created_at,
    last_login,
    email_verified
FROM xmpp_users
WHERE is_active = TRUE;

COMMENT ON VIEW active_users IS 'Übersicht aller aktiven User mit vollständiger JID';

-- Registrierungs-Statistiken
CREATE OR REPLACE VIEW registration_stats AS
SELECT 
    DATE(created_at) AS date,
    COUNT(*) AS registrations,
    COUNT(DISTINCT registration_ip) AS unique_ips
FROM xmpp_users
GROUP BY DATE(created_at)
ORDER BY date DESC;

COMMENT ON VIEW registration_stats IS 'Tägliche Registrierungs-Statistiken';

-- =====================================================
-- FUNKTIONEN für automatische Bereinigung
-- =====================================================

-- Abgelaufene Verifikations-Tokens löschen
CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS void AS $$
BEGIN
    DELETE FROM email_verification
    WHERE expires_at < CURRENT_TIMESTAMP
    AND verified_at IS NULL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_tokens IS 'Löscht abgelaufene, unverifizierte Email-Tokens';

-- =====================================================
-- TRIGGER für automatische Updates
-- =====================================================

-- Automatisches last_login Update
CREATE OR REPLACE FUNCTION update_last_login()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.last_login != OLD.last_login OR OLD.last_login IS NULL THEN
        NEW.last_login = CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger wird später bei Bedarf aktiviert
-- CREATE TRIGGER trigger_update_last_login
-- BEFORE UPDATE ON xmpp_users
-- FOR EACH ROW
-- EXECUTE FUNCTION update_last_login();

-- =====================================================
-- BEISPIEL-DATEN (Optional für Testing)
-- =====================================================

-- Testuser erstellen (nur für Entwicklung!)
-- INSERT INTO xmpp_users (username, domain, password_hash, email, is_active)
-- VALUES ('testuser', 'deine-domain.de', '$2b$12$...hash...', 'test@example.com', true);

-- =====================================================
-- BERECHTIGUNGEN setzen
-- =====================================================

-- Berechtigungen für xmpp_web User (Backend)
GRANT SELECT, INSERT, UPDATE ON xmpp_users TO xmpp_web;
GRANT SELECT, INSERT, UPDATE, DELETE ON email_verification TO xmpp_web;
GRANT SELECT, INSERT ON registration_logs TO xmpp_web;
GRANT SELECT ON banned_ips TO xmpp_web;

-- Sequenzen für Auto-Increment
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO xmpp_web;

-- Views
GRANT SELECT ON active_users TO xmpp_web;
GRANT SELECT ON registration_stats TO xmpp_web;

-- =====================================================
-- MAINTENANCE JOBS (Cron oder systemd timer)
-- =====================================================

-- Diese Befehle sollten regelmäßig ausgeführt werden:
-- 
-- 1. Alte Logs bereinigen (älter als 90 Tage):
--    DELETE FROM registration_logs WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '90 days';
--
-- 2. Abgelaufene Tokens löschen:
--    SELECT cleanup_expired_tokens();
--
-- 3. Inaktive, unverifizierte Accounts löschen (älter als 30 Tage):
--    DELETE FROM xmpp_users 
--    WHERE email_verified = FALSE 
--    AND created_at < CURRENT_TIMESTAMP - INTERVAL '30 days';

-- =====================================================
-- 5. TABELLE: password_reset_tokens
-- =====================================================
-- Tokens fuer Passwort-Reset (per Email-Link)

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES xmpp_users(id) ON DELETE CASCADE,
    token VARCHAR(128) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP,
    request_ip INET,
    CONSTRAINT valid_reset_token CHECK (char_length(token) >= 32)
);

CREATE INDEX IF NOT EXISTS idx_reset_token ON password_reset_tokens(token);
CREATE INDEX IF NOT EXISTS idx_reset_user ON password_reset_tokens(user_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_tokens TO xmpp_web;
GRANT USAGE, SELECT ON SEQUENCE password_reset_tokens_id_seq TO xmpp_web;

COMMENT ON TABLE password_reset_tokens IS 'Tokens fuer Passwort-Reset-Flow (1h Gueltigkeit)';

-- =====================================================
-- One-time-Nonces fuer das Mathe-Captcha (verhindert Token-Replay)
-- =====================================================
CREATE TABLE IF NOT EXISTS used_math_tokens (
    nonce TEXT PRIMARY KEY,
    used_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_used_math_tokens_used_at ON used_math_tokens(used_at);

GRANT SELECT, INSERT, DELETE ON used_math_tokens TO xmpp_web;

COMMENT ON TABLE used_math_tokens IS 'Verbrauchte Captcha-Nonces (Single-Use); alte Eintraege koennen periodisch geloescht werden';

-- =====================================================
-- Bot-Schutz-Gate (tdwall): protokolliert Splash-Durchgaenge
-- =====================================================
CREATE TABLE IF NOT EXISTS tdwall_events (
    id BIGSERIAL PRIMARY KEY,
    rayid TEXT NOT NULL,
    ip_address INET,
    path TEXT,
    user_agent TEXT,
    is_onion BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tdwall_created ON tdwall_events(created_at);
CREATE INDEX IF NOT EXISTS idx_tdwall_ip ON tdwall_events(ip_address);
CREATE INDEX IF NOT EXISTS idx_tdwall_rayid ON tdwall_events(rayid);

GRANT SELECT, INSERT, DELETE ON tdwall_events TO xmpp_web;
GRANT USAGE, SELECT ON SEQUENCE tdwall_events_id_seq TO xmpp_web;

COMMENT ON TABLE tdwall_events IS 'Logeintraege des Bot-Schutz-Gates (Splash) fuer Clearnet und Onion';

-- =====================================================
-- Setup abgeschlossen!
-- =====================================================

SELECT 'Datenbank-Setup erfolgreich abgeschlossen!' AS status;

-- Tabellen anzeigen
\dt

-- Zeige Statistiken
SELECT 
    'xmpp_users' as table_name,
    COUNT(*) as row_count
FROM xmpp_users
UNION ALL
SELECT 
    'registration_logs',
    COUNT(*)
FROM registration_logs;
