# 🚀 QUICK START für acidbrns.cc

## ⚡ Installation in 5 Schritten

### 1️⃣ Raspberry Pi IP herausfinden

```bash
# Auf dem Pi:
curl ifconfig.me
```

Notiere die IP! (z.B. `123.45.67.89`)

---

### 2️⃣ Cloudflare DNS konfigurieren

**Gehe zu**: https://dash.cloudflare.com → acidbrns.cc → DNS → Records

**Erstelle 2 A-Records:**

| Type | Name | IPv4 Address | Proxy Status |
|------|------|--------------|--------------|
| A | @ (oder acidbrns.cc) | DEINE-PI-IP | ☁️ DNS only (GRAU!) |
| A | upload | DEINE-PI-IP | ☁️ DNS only (GRAU!) |

**⚠️ WICHTIG**: Proxy-Status muss **OFF** sein (graue Cloud)!

---

### 3️⃣ Router Port-Forwarding

**In deinem Router-Admin-Panel** (meist http://192.168.1.1):

Ports freigeben zu deinem Raspberry Pi:

```
80   → Raspberry Pi IP
443  → Raspberry Pi IP
5222 → Raspberry Pi IP
5269 → Raspberry Pi IP
5280 → Raspberry Pi IP
```

---

### 4️⃣ DNS testen

**Warte 2-5 Minuten**, dann teste:

```bash
# Von einem anderen Computer/Handy:
ping acidbrns.cc
ping upload.acidbrns.cc

# Sollte deine Pi-IP zeigen!
```

---

### 5️⃣ Installation starten

**Auf dem Raspberry Pi:**

```bash
# Falls noch nicht kopiert: ZIP hochladen
scp xmpp-acidbrns.zip user@pi-ip:/home/user/
ssh user@pi-ip

# Entpacken
unzip xmpp-acidbrns.zip
cd xmpp-acidbrns/scripts

# Ausführbar machen
chmod +x install.sh

# Starten!
sudo bash install.sh
```

**Das Script fragt nach:**
- Domain (Enter drücken für acidbrns.cc)
- Admin E-Mail (für SSL-Zertifikate)

**Dann macht es alles automatisch!** ⏱️ Ca. 15-20 Minuten

---

## ✅ Nach der Installation

### Testen:

1. **Webseite öffnen**: https://acidbrns.cc
2. **Account erstellen**: Formular ausfüllen
3. **XMPP-Client** (z.B. Conversations) installieren:
   - JID: `deinname@acidbrns.cc`
   - Passwort: (dein gewähltes Passwort)
   - Server: acidbrns.cc

### OMEMO aktivieren:

In der App → Einstellungen → OMEMO aktivieren 🔒

---

## 🆘 Probleme?

### Website nicht erreichbar

```bash
# Services prüfen
sudo systemctl status nginx
sudo systemctl status xmpp-backend

# Firewall prüfen
sudo ufw status

# Nginx Logs
sudo tail -f /var/log/nginx/xmpp-registration-error.log
```

### SSL-Fehler

```bash
# Nochmal Zertifikate holen
sudo certbot certonly --nginx -d acidbrns.cc -d upload.acidbrns.cc --email deine@email.de
```

### XMPP funktioniert nicht

```bash
# Prosody prüfen
sudo systemctl status prosody
sudo prosodyctl check

# Logs ansehen
sudo tail -f /var/log/prosody/prosody.log
```

---

## 📚 Mehr Hilfe

- **CLOUDFLARE_SETUP.md** - Detaillierte Cloudflare-Anleitung
- **README.md** - Komplettes Handbuch
- **DATABASE_GUIDE.md** - Datenbank für Anfänger

---

## 🎯 Checkliste

- [ ] Pi IP notiert
- [ ] Cloudflare DNS konfiguriert (Proxy OFF!)
- [ ] Router Port-Forwarding eingerichtet
- [ ] `ping acidbrns.cc` funktioniert
- [ ] Installation ausgeführt
- [ ] Website erreichbar unter https://acidbrns.cc
- [ ] Test-Account erstellt
- [ ] XMPP-Client verbunden

---

**Viel Erfolg mit deinem XMPP-Server auf acidbrns.cc! 🎉**
