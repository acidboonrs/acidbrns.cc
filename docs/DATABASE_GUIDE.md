# 📚 Datenbank-Guide für Anfänger

Dieser Guide erklärt dir, wie PostgreSQL in diesem Projekt funktioniert und wie du damit arbeitest.

## 🤔 Was ist eine Datenbank?

Eine Datenbank ist wie ein intelligenter Aktenschrank, der:
- Daten strukturiert speichert (in Tabellen wie Excel)
- Schnellen Zugriff ermöglicht
- Mehrere Benutzer gleichzeitig bedient
- Daten sicher verwahrt

**PostgreSQL** ist eine professionelle, kostenlose Datenbank-Software.

## 📊 Unsere Datenbank-Struktur

### Haupttabelle: `xmpp_users`

Hier werden alle XMPP-Accounts gespeichert:

```
┌─────┬──────────┬────────────┬───────────────┬─────────────┬─────────────┐
│ id  │ username │   domain   │ password_hash │    email    │ created_at  │
├─────┼──────────┼────────────┼───────────────┼─────────────┼─────────────┤
│ 1   │ max      │ xmpp.de    │ $2b$12$...   │ max@web.de  │ 2025-01-07  │
│ 2   │ anna     │ xmpp.de    │ $2b$12$...   │ null        │ 2025-01-07  │
└─────┴──────────┴────────────┴───────────────┴─────────────┴─────────────┘
```

**Wichtige Spalten**:
- `id`: Einzigartige Nummer für jeden User (Auto-Increment)
- `username`: Der Username vor dem @ (z.B. "max")
- `domain`: Die Domain nach dem @ (z.B. "xmpp.de")
- `password_hash`: Verschlüsseltes Passwort (NICHT das Original!)
- `email`: Optional, für Account-Wiederherstellung
- `created_at`: Wann wurde der Account erstellt?

### Weitere Tabellen

**`email_verification`** - Für E-Mail-Bestätigung
```
Token wird generiert → User klickt Link → Account aktiviert
```

**`registration_logs`** - Wer hat wann was gemacht?
```
Jede Registrierung wird geloggt (IP, Zeitpunkt, User-Agent)
```

**`banned_ips`** - Spam-Schutz
```
IPs die zu oft versuchen zu registrieren → blockiert
```

## 🔑 PostgreSQL-Zugriff

### Als Root in die Datenbank

```bash
# PostgreSQL-User werden
sudo -u postgres psql

# Zu unserer Datenbank wechseln
\c xmpp_registration

# Liste aller Tabellen
\dt

# Struktur einer Tabelle ansehen
\d xmpp_users

# Verlassen
\q
```

### Direkt in Datenbank

```bash
sudo -u postgres psql -d xmpp_registration
```

## 📖 SQL-Befehle für Anfänger

### Daten ANZEIGEN (SELECT)

```sql
-- Alle User anzeigen
SELECT * FROM xmpp_users;

-- Nur bestimmte Spalten
SELECT username, email, created_at FROM xmpp_users;

-- Nur aktive User
SELECT * FROM xmpp_users WHERE is_active = TRUE;

-- Sortiert nach Datum
SELECT username, created_at FROM xmpp_users 
ORDER BY created_at DESC;

-- Anzahl User
SELECT COUNT(*) FROM xmpp_users;

-- User von heute
SELECT COUNT(*) FROM xmpp_users 
WHERE DATE(created_at) = CURRENT_DATE;
```

### Daten ÄNDERN (UPDATE)

```sql
-- Email für einen User setzen
UPDATE xmpp_users 
SET email = 'neue@email.de' 
WHERE username = 'max';

-- User deaktivieren
UPDATE xmpp_users 
SET is_active = FALSE 
WHERE username = 'spammer';

-- Email verifizieren
UPDATE xmpp_users 
SET email_verified = TRUE 
WHERE username = 'anna';
```

### Daten LÖSCHEN (DELETE)

```sql
-- Einzelnen User löschen
DELETE FROM xmpp_users 
WHERE username = 'testuser';

-- Alte, unverifizierte Accounts (älter als 30 Tage)
DELETE FROM xmpp_users 
WHERE email_verified = FALSE 
AND created_at < CURRENT_TIMESTAMP - INTERVAL '30 days';

-- Alte Logs löschen
DELETE FROM registration_logs 
WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '90 days';
```

### Daten HINZUFÜGEN (INSERT)

**ACHTUNG**: Normalerweise macht das die Web-Registrierung!
Nur für Tests:

```sql
-- Test-User erstellen (mit gehashtem Passwort!)
INSERT INTO xmpp_users (username, domain, password_hash, email, is_active)
VALUES ('testuser', 'deine-domain.de', '$2b$12$dummyhash...', 'test@example.com', true);
```

## 🔍 Nützliche Abfragen

### Statistiken

```sql
-- Registrierungen pro Tag (letzte 7 Tage)
SELECT 
    DATE(created_at) as datum,
    COUNT(*) as registrierungen
FROM xmpp_users
WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY datum DESC;

-- Aktive vs Inaktive User
SELECT 
    is_active,
    COUNT(*) as anzahl
FROM xmpp_users
GROUP BY is_active;

-- User ohne E-Mail
SELECT COUNT(*) 
FROM xmpp_users 
WHERE email IS NULL;
```

### Spam-Erkennung

```sql
-- Mehrfach-Registrierungen von gleicher IP
SELECT 
    registration_ip,
    COUNT(*) as anzahl
FROM xmpp_users
GROUP BY registration_ip
HAVING COUNT(*) > 3
ORDER BY anzahl DESC;

-- Verdächtige Registrierungs-Muster
SELECT 
    DATE(created_at) as datum,
    COUNT(*) as anzahl,
    COUNT(DISTINCT registration_ip) as unique_ips
FROM xmpp_users
GROUP BY DATE(created_at)
ORDER BY datum DESC;
```

### Account-Suche

```sql
-- User suchen (partial match)
SELECT username, email, created_at 
FROM xmpp_users 
WHERE username LIKE '%anna%';

-- User nach E-Mail finden
SELECT username, domain, created_at 
FROM xmpp_users 
WHERE email = 'max@example.com';
```

## 🛠️ Wartung & Backup

### Datenbank sichern

```bash
# Komplettes Backup
sudo -u postgres pg_dump xmpp_registration > backup_$(date +%Y%m%d).sql

# Nur Schema (Struktur, keine Daten)
sudo -u postgres pg_dump --schema-only xmpp_registration > schema.sql

# Nur Daten
sudo -u postgres pg_dump --data-only xmpp_registration > data.sql

# Komprimiertes Backup
sudo -u postgres pg_dump xmpp_registration | gzip > backup.sql.gz
```

### Backup wiederherstellen

```bash
# Datenbank neu erstellen (ACHTUNG: löscht alte Daten!)
sudo -u postgres dropdb xmpp_registration
sudo -u postgres createdb xmpp_registration

# Backup einspielen
sudo -u postgres psql xmpp_registration < backup_20250107.sql

# Komprimiertes Backup
gunzip -c backup.sql.gz | sudo -u postgres psql xmpp_registration
```

### Automatisches Backup (Cronjob)

```bash
# Crontab editieren
sudo crontab -e

# Jeden Tag um 3 Uhr morgens
0 3 * * * /usr/bin/pg_dump -U postgres xmpp_registration | gzip > /root/backups/xmpp_$(date +\%Y\%m\%d).sql.gz

# Alte Backups löschen (älter als 30 Tage)
0 4 * * * find /root/backups/ -name "xmpp_*.sql.gz" -mtime +30 -delete
```

### Datenbank optimieren

```bash
# Als postgres User
sudo -u postgres psql -d xmpp_registration

-- Statistiken aktualisieren (macht DB schneller)
ANALYZE;

-- Speicherplatz zurückgewinnen
VACUUM;

-- Beides zusammen
VACUUM ANALYZE;
```

## 🔐 Sicherheit

### Berechtigungen prüfen

```sql
-- Welche User haben Zugriff?
\du

-- Berechtigungen für Tabellen
\dp xmpp_users
```

### Passwort ändern

```bash
sudo -u postgres psql

-- PostgreSQL User-Passwort ändern
ALTER USER xmpp_web WITH PASSWORD 'neues-passwort';

# WICHTIG: Auch in .env Datei ändern!
sudo nano /var/www/xmpp-registration/backend/.env
```

### Connections überwachen

```sql
-- Aktive Verbindungen
SELECT * FROM pg_stat_activity;

-- Nur für unsere Datenbank
SELECT * FROM pg_stat_activity 
WHERE datname = 'xmpp_registration';
```

## 🆘 Problemlösung

### "Verbindung fehlgeschlagen"

```bash
# PostgreSQL läuft?
sudo systemctl status postgresql

# Starten falls nicht
sudo systemctl start postgresql

# Logs prüfen
sudo tail -f /var/log/postgresql/postgresql-*.log
```

### "Authentifizierung fehlgeschlagen"

```bash
# .env Datei prüfen
sudo cat /var/www/xmpp-registration/backend/.env

# Passwort in Datenbank testen
sudo -u postgres psql -d xmpp_registration -U xmpp_web -h localhost
# (Passwort aus .env eingeben)
```

### "Tabelle existiert nicht"

```bash
# Schema nochmal importieren
sudo -u postgres psql -d xmpp_registration -f ~/xmpp-project/scripts/setup_database.sql
```

### "Speicherplatz voll"

```sql
-- Datenbankgröße prüfen
SELECT pg_size_pretty(pg_database_size('xmpp_registration'));

-- Tabellen-Größen
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Alte Daten löschen
DELETE FROM registration_logs WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '90 days';
VACUUM;
```

## 💡 Tipps & Tricks

### Views (gespeicherte Abfragen)

```sql
-- Schon vorhanden: active_users
SELECT * FROM active_users;

-- Eigene View erstellen
CREATE VIEW neue_user AS
SELECT username, email, created_at
FROM xmpp_users
WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '7 days';

-- Verwenden
SELECT * FROM neue_user;
```

### Temporäre Tabellen

```sql
-- Für Tests/Analysen
CREATE TEMP TABLE temp_stats AS
SELECT DATE(created_at) as datum, COUNT(*) as anzahl
FROM xmpp_users
GROUP BY DATE(created_at);

-- Verwenden
SELECT * FROM temp_stats WHERE anzahl > 10;

-- Löscht sich automatisch am Ende der Session
```

### Transaktionen (alles oder nichts)

```sql
-- Transaktion starten
BEGIN;

-- Mehrere Befehle
UPDATE xmpp_users SET is_active = FALSE WHERE username = 'test1';
DELETE FROM xmpp_users WHERE username = 'test2';

-- Prüfen
SELECT * FROM xmpp_users WHERE username IN ('test1', 'test2');

-- Zurückrollen (rückgängig machen)
ROLLBACK;

-- ODER: Bestätigen
-- COMMIT;
```

## 📚 Weiterführende Ressourcen

- [PostgreSQL Tutorial](https://www.postgresql.org/docs/current/tutorial.html)
- [SQL Cheat Sheet](https://www.postgresqltutorial.com/postgresql-cheat-sheet/)
- [PostgreSQL Best Practices](https://wiki.postgresql.org/wiki/Don%27t_Do_This)

## ✅ Checkliste für Wartung

**Täglich**:
- [ ] Backend-Logs prüfen: `journalctl -u xmpp-backend --since today`

**Wöchentlich**:
- [ ] Statistiken ansehen: `SELECT * FROM registration_stats LIMIT 7;`
- [ ] Backup erstellen (wenn nicht automatisiert)

**Monatlich**:
- [ ] Alte Logs löschen (>90 Tage)
- [ ] Inaktive Accounts prüfen
- [ ] Datenbank optimieren: `VACUUM ANALYZE;`

**Bei Problemen**:
- [ ] Logs prüfen
- [ ] Datenbankverbindung testen
- [ ] Berechtigungen prüfen
- [ ] Backups prüfen

---

**Fragen?** Lies zuerst die FAQ im README.md oder schau in die PostgreSQL-Dokumentation!
