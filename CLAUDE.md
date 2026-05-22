# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

XMPP account registration system for **acidbrns.cc** running on a Linux host. Users register via a web form; the backend creates accounts in both PostgreSQL and Prosody simultaneously.

## Architecture

```
Browser → Nginx (443) → Flask API (127.0.0.1:5000) → PostgreSQL
                                                     → prosodyctl (subprocess)
```

- **Frontend**: The registration/account/reset pages are server-side rendered by Flask (Jinja templates in `backend/templates/`), JavaScript-free. A small set of static files (`frontend/`: datenschutz.html, onion.html, style, favicon, PGP keys) is served by Nginx directly. There is a clearnet variant and an onion-mirror variant.
- **Backend** (`backend/app.py`): Flask app. Handles validation, a self-hosted bot protection (math captcha + honeypot, single-use signed tokens), DB-backed rate limiting + IP bans, registration, account management and password reset.
- **Dual write**: Every registration writes to both PostgreSQL (`xmpp_users` table) and Prosody via the validated wrapper (`sudo -u prosody /usr/local/sbin/xmpp-prosody-admin register <user>`). If Prosody creation fails, the DB insert is skipped.
- **Config** (`config/`): Nginx reverse proxy config and Prosody XMPP server config. Both use `deine-domain.de` as a placeholder replaced with the real domain during install.

## Key Files

| File | Purpose |
|------|---------|
| `backend/app.py` | Flask app — validation, bot protection, rate limiting, registration, account mgmt, reset |
| `backend/templates/` | Server-side-rendered Jinja pages (clearnet_* and onion_*) |
| `backend/.env` | Runtime secrets (copy from `.env.example`, never commit) |
| `scripts/install.sh` | Full automated install script (Nginx, PostgreSQL, Prosody, SSL) |
| `scripts/xmpp-prosody-admin` | Validated wrapper for prosodyctl account ops (install to /usr/local/sbin) |
| `scripts/sudoers-xmpp-registration` | Sudoers rule granting www-data only the wrapper |
| `scripts/setup_database.sql` | DB schema: `xmpp_users`, `registration_logs`, `banned_ips`, `email_verification`, `password_reset_tokens`, `used_math_tokens`, `tdwall_events` |
| `config/prosody.cfg.lua` | Prosody XMPP server config (OMEMO, MAM, HTTP upload) |
| `config/nginx.conf` | Nginx: serves static frontend, proxies `/api/` to Flask |

## Development

### Run backend locally

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in values
python app.py         # dev server on :5000
```

### Environment variables (`.env`)

```
DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT  # PostgreSQL
XMPP_DOMAIN          # e.g. acidbrns.cc
PROSODY_PATH         # /usr/bin/prosodyctl
PROSODY_ADMIN        # /usr/local/sbin/xmpp-prosody-admin (validated wrapper)
MATH_CAPTCHA_SECRET  # signs the math-captcha tokens (bot protection)
TDWALL_SECRET        # signs the bot-protection gate tokens/cookies
FLASK_DEBUG          # True for dev
# Optional SMTP for password reset: MAIL_SERVER, MAIL_PORT, MAIL_USERNAME,
# MAIL_PASSWORD, MAIL_USE_TLS, MAIL_FROM, APP_BASE_URL
```

### Routes

User-facing (server-side rendered, form POST, JavaScript-free):
- `GET  /` — registration page (behind the bot-protection gate)
- `POST /register` — create account (honeypot + math captcha)
- `GET/POST /account`, `/account/change-password`, `/account/delete`
- `GET/POST /reset`, `/reset/request`, `/reset/confirm`
- Onion mirror serves the equivalent under `/api/onion/*`

JSON helper endpoints (read-only):
- `GET  /api/status` — health check (DB connectivity)
- `GET  /api/check-username/<username>` — availability check
- `GET  /api/stats` — public user count

## Production Services

```bash
# Check service status
sudo systemctl status xmpp-backend nginx prosody postgresql

# View logs
sudo journalctl -u xmpp-backend -f
sudo tail -f /var/log/prosody/prosody.log
sudo tail -f /var/log/nginx/xmpp-registration-error.log

# Restart after code changes
sudo systemctl restart xmpp-backend

# Prosody config check
sudo prosodyctl check
```

Production runs gunicorn: `gunicorn --bind 127.0.0.1:5000 --workers 4 app:app` under `www-data` user. The `www-data` user needs a sudoers rule to call `prosodyctl` as the `prosody` user.

## Database

```bash
sudo -u postgres psql -d xmpp_registration
```

Useful queries:
```sql
SELECT username, domain, email, created_at FROM xmpp_users;
SELECT * FROM active_users;        -- view: active users with full JID
SELECT * FROM registration_stats;  -- view: daily registration counts
```

## Required Ports

`80`, `443` (web), `5222` (XMPP client), `5269` (XMPP federation), `5280` (HTTP upload)

## Cloudflare DNS Note

DNS proxy must be **disabled** (grey cloud) for XMPP ports to work — only HTTP/HTTPS can go through Cloudflare's proxy.
