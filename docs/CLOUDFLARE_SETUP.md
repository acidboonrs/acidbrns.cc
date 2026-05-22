# ☁️ Cloudflare DNS Setup für acidbrns.cc

## 🎯 WICHTIG: DNS-Einstellungen BEVOR du installierst!

### Schritt 1: Deine Raspberry Pi IP herausfinden

Auf deinem Raspberry Pi:
```bash
curl ifconfig.me
```

Notiere dir diese IP-Adresse! (z.B. `123.45.67.89`)

---

## 🌐 Schritt 2: Cloudflare DNS konfigurieren

Gehe zu: https://dash.cloudflare.com

### A) Haupt-Domain: acidbrns.cc

1. Wähle `acidbrns.cc` aus deinen Domains
2. Klicke auf **DNS** → **Records**
3. Klicke **Add record**

**Einstellungen:**
```
Type:       A
Name:       @  (oder acidbrns.cc)
IPv4:       DEINE-RASPBERRY-PI-IP (z.B. 123.45.67.89)
TTL:        Auto
Proxy:      🔴 DNS only (grauer Cloud-Symbol - SEHR WICHTIG!)
```

**⚠️ KRITISCH: Proxy-Status**
- **Proxy OFF** (graue Cloud ☁️) = DNS only
- **NICHT** Orange Cloud verwenden! ❌
- Warum? Let's Encrypt braucht direkten Zugriff zu deinem Pi

### B) Subdomain für Upload: upload.acidbrns.cc

Noch ein Record hinzufügen:

**Einstellungen:**
```
Type:       A
Name:       upload
IPv4:       DEINE-RASPBERRY-PI-IP (gleiche wie oben!)
TTL:        Auto
Proxy:      🔴 DNS only (grauer Cloud-Symbol)
```

### C) Optional: XMPP Service Records (für Federation)

Wenn du möchtest, dass andere XMPP-Server dich finden:

```
Type:       SRV
Name:       _xmpp-client._tcp
Service:    _xmpp-client
Protocol:   TCP
TTL:        Auto
Priority:   0
Weight:     5
Port:       5222
Target:     acidbrns.cc
```

```
Type:       SRV
Name:       _xmpp-server._tcp
Service:    _xmpp-server
Protocol:   TCP
TTL:        Auto
Priority:   0
Weight:     5
Port:       5269
Target:     acidbrns.cc
```

---

## ✅ Schritt 3: DNS-Propagation prüfen

Nach dem Speichern, warte 2-5 Minuten, dann teste:

```bash
# Von deinem Computer oder einem anderen Gerät:
ping acidbrns.cc
ping upload.acidbrns.cc

# Sollte deine Raspberry Pi IP zeigen!
```

Oder online prüfen:
- https://dnschecker.org/#A/acidbrns.cc
- https://dnschecker.org/#A/upload.acidbrns.cc

---

## 🚀 Schritt 4: Installation starten

**ERST WENN** DNS propagiert ist (ping funktioniert):

```bash
cd ~/xmpp-acidbrns/scripts
sudo bash install.sh
```

Das Script verwendet automatisch **acidbrns.cc** als Domain!

---

## 🔐 SSL/TLS mit Cloudflare Free

### Option 1: Let's Encrypt (Empfohlen) ✅

**Bereits in install.sh enthalten!**

- Proxy: **OFF** (graue Cloud)
- Certbot holt Zertifikate direkt vom Pi
- Funktioniert perfekt mit Free-Plan

### Option 2: Cloudflare Origin Certificate

Falls du Proxy nutzen willst (orange Cloud):

1. Cloudflare Dashboard → SSL/TLS → Origin Server
2. Create Certificate
3. Zertifikat & Key auf Pi speichern
4. Nginx & Prosody Config anpassen

**Aber**: Komplizierter und nicht nötig für dein Setup!

---

## 🛡️ Cloudflare Firewall-Regeln (Optional)

Wenn du zusätzlichen Schutz willst:

**Security → WAF → Create rule:**

```
Rule name: Allow XMPP Ports
Expression: (ip.src eq DEINE-IP) or (cf.threat_score lt 10)
Action: Allow
```

Aber: Nicht nötig für Start! Erstmal grundlegendes Setup testen.

---

## 📊 Cloudflare Analytics

Nach Installation kannst du Traffic überwachen:
- Analytics → Traffic
- Siehst du Besucher auf acidbrns.cc

---

## 🐛 Problemlösung

### "DNS_PROBE_FINISHED_NXDOMAIN"

❌ **Problem**: Domain nicht erreichbar
✅ **Lösung**: 
- DNS-Einträge prüfen (sind sie gespeichert?)
- 10-15 Minuten warten
- `ping acidbrns.cc` testen

### "Certificate Error" bei HTTPS

❌ **Problem**: SSL-Zertifikat fehlt
✅ **Lösung**:
- Proxy auf **DNS only** setzen
- Let's Encrypt nochmal ausführen:
```bash
sudo certbot certonly --nginx -d acidbrns.cc -d upload.acidbrns.cc
```

### "Connection Refused" Port 5222

❌ **Problem**: Firewall blockiert XMPP
✅ **Lösung**:
```bash
# Auf dem Pi
sudo ufw allow 5222/tcp
sudo ufw allow 5269/tcp
```

### Cloudflare zeigt "Offline"

❌ **Problem**: Proxy ist AN, aber Server nicht erreichbar
✅ **Lösung**:
- Proxy auf **DNS only** umstellen
- Nginx/Prosody Status prüfen:
```bash
sudo systemctl status nginx
sudo systemctl status prosody
```

---

## 📋 Checkliste vor Installation

- [ ] Raspberry Pi hat feste IP-Adresse (statisch oder DHCP-Reservierung)
- [ ] Port-Forwarding im Router konfiguriert (siehe unten)
- [ ] DNS-Einträge in Cloudflare gesetzt (Proxy OFF!)
- [ ] `ping acidbrns.cc` funktioniert
- [ ] `ping upload.acidbrns.cc` funktioniert

---

## 🏠 Router Port-Forwarding

**SEHR WICHTIG**: Ports im Router freigeben!

In deinem Router-Admin-Panel:

```
Externe Ports    →    Interne IP         →    Interne Ports
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
80               →    RASPBERRY-PI-IP    →    80
443              →    RASPBERRY-PI-IP    →    443
5222             →    RASPBERRY-PI-IP    →    5222
5269             →    RASPBERRY-PI-IP    →    5269
5280             →    RASPBERRY-PI-IP    →    5280
```

**Router-Zugriff**:
- Meist über: http://192.168.1.1 oder http://192.168.0.1
- Login: Steht auf Rückseite des Routers
- Suche nach: "Port Forwarding", "NAT", "Virtual Server"

**Tipp**: Google nach: "DEIN-ROUTER-MODELL port forwarding anleitung"

---

## ✅ DNS Setup komplett!

Wenn du bis hier alles gemacht hast:

1. ✅ DNS-Einträge in Cloudflare (Proxy OFF)
2. ✅ Port-Forwarding im Router
3. ✅ Ping funktioniert

**Dann kannst du installieren!** 🚀

```bash
cd ~/xmpp-acidbrns/scripts
sudo bash install.sh
```

Die Domain **acidbrns.cc** wird automatisch verwendet!

---

## 🎉 Nach erfolgreicher Installation

Teste deine Seite:
- https://acidbrns.cc (Registrierungs-Formular)
- XMPP mit Client verbinden: `username@acidbrns.cc`

**Cloudflare Analytics** zeigt dir dann auch Traffic an!

---

## 💡 Cloudflare Free Plan - Perfekt für XMPP!

**Inkludiert**:
- ✅ DNS Management (was wir nutzen)
- ✅ Basic DDoS Protection
- ✅ SSL/TLS (wenn Proxy AN)
- ✅ Analytics

**Wir nutzen**:
- Nur DNS (Proxy OFF)
- Let's Encrypt für SSL
- Direkter Traffic zum Pi

**Warum Proxy OFF?**
- Let's Encrypt braucht direkten Zugriff
- XMPP-Ports (5222, 5269) können nicht geproxyt werden
- Einfacher & funktioniert garantiert!

---

Bei Fragen: Logs prüfen oder im README nachschauen! 📚
