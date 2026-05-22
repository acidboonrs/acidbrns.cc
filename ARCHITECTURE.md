# Architecture & Security Design

🌐 **English** · [Deutsch](ARCHITECTURE.de.md)

Self-hosted XMPP account provisioning for **acidbrns.cc**. Users self-register
through a web form; the backend provisions each account atomically in PostgreSQL
**and** the Prosody XMPP server. The system is built privacy- and security-first.

> This document describes the design at a conceptual level. Concrete network
> details (addresses, subnets, host specifics) are intentionally omitted.

## Request flow (high level)

A hardened **edge reverse proxy** terminates TLS and forwards requests over an
**encrypted tunnel (WireGuard)** to an isolated application backend. The backend
origin is never exposed directly to the public internet.

```
Client ──TLS──▶ Edge proxy (nginx) ──encrypted tunnel──▶ Backend
                                                          ├─ nginx
                                                          ├─ Flask app (gunicorn, localhost-only)
                                                          ├─ PostgreSQL (localhost-only)
                                                          └─ Prosody (XMPP)
```

The same application is also reachable as a **Tor onion service** for
metadata-free access.

## Components

| Layer | Role |
|-------|------|
| Edge proxy | TLS termination, security headers, static assets, real-client-IP propagation |
| App | Flask, **server-side rendered, JavaScript-free**; runs under gunicorn, bound to localhost |
| Database | PostgreSQL, bound to localhost, **encrypted at rest** |
| XMPP | Prosody with `internal_hashed` auth, encryption enforced for c2s/s2s |

## Security design (defense in depth)

### Transport & headers
- TLS 1.2/1.3 only; **HSTS with preload**.
- Strict **Content-Security-Policy** (`default-src 'none'` on the app), plus
  `X-Frame-Options`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`.
- Edge/origin separation — the backend origin is not directly reachable.

### Bot protection (self-hosted, zero third parties)
- A server-signed, **single-use math captcha** plus a hidden **honeypot** field.
- No Cloudflare, no Google, **no JavaScript** — works in text browsers and in the
  Tor Browser's "safest" mode.
- A lightweight gate throttles automated probing before the form is reached.

### Application security
- **Allowlist input validation**; all SQL is **parametrized** (no string-built queries).
- Passwords hashed with **bcrypt** (cost 12); the XMPP side uses `internal_hashed`.
- **Fail-closed** captcha verification; **generic responses** to prevent username/email enumeration.
- Password reset uses **high-entropy, single-use tokens** with a short TTL.

### Least privilege
- A dedicated, unprivileged service user runs the app.
- Privileged account operations (create/passwd/delete) go through a **validated
  wrapper**: fixed domain, charset/length-checked username, no shell, no argument
  injection surface — exposed via a single, tightly-scoped `sudo` rule.
- Secrets live in an environment file (`0600`, never committed); dotfiles and
  backup files are blocked at the proxy.

### Abuse handling & monitoring
- **DB-backed rate limiting and IP banning** (consistent across all workers).
- `fail2ban` on the host; **minimal logging** with short retention.

### Data at rest & email
- The database lives on an **encrypted volume**, unlocked manually after boot.
- Password-reset email is sent over authenticated SMTP; the domain is protected
  by **SPF, DKIM and DMARC**.

## Privacy posture
- No third-party scripts, no analytics, no tracking cookies — only a single
  first-party technical cookie for the bot gate.
- Tor onion service; users are encouraged to connect over Tor so that no
  connection metadata (IP, location, ISP) is retained server-side.

## Threat model (summary)
- **In scope:** web abuse (bots, enumeration, injection, XSS), credential safety,
  least-privilege containment, transport security, metadata minimization.
- **Out of scope / not claimed:** global traffic-analysis adversaries, compromise
  of the user's own device.
