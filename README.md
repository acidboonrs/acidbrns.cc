# XMPP Registration System for acidbrns.cc

A complete web-based user registration system for XMPP (Jabber) servers, built with Flask backend and vanilla JavaScript frontend.

## Features

- **Modern Web Interface**: Clean, responsive design for user registration
- **Secure Backend**: Flask API with bcrypt password hashing
- **Database Integration**: PostgreSQL for user management
- **XMPP Server Integration**: Direct integration with Prosody XMPP server
- **Real-time Validation**: Username availability checking and password strength indicator
- **Production Ready**: Includes Nginx configuration, systemd services, and SSL/TLS setup
- **Security Hardened**: Proper permissions, secure sudo configuration, and HTTPS enforcement

## System Requirements

- Ubuntu 20.04+ or Debian 11+ (tested on Ubuntu 24.04 LTS)
- 1GB+ RAM
- 10GB+ disk space
- Root or sudo access
- Domain name with DNS access

## Architecture

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTPS
       ▼
┌─────────────┐
│    Nginx    │ (Reverse Proxy + Static Files)
└──────┬──────┘
       │
       ▼
┌─────────────┐      ┌──────────────┐      ┌──────────────┐
│   Flask     │─────▶│  PostgreSQL  │      │   Prosody    │
│  (Gunicorn) │      │   Database   │      │ XMPP Server  │
└──────┬──────┘      └──────────────┘      └──────────────┘
       │                                           ▲
       └───────────────────────────────────────────┘
                  prosodyctl (subprocess)
```

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/acidboonrs/acidbrns.cc.git
cd acidbrns.cc
```

### 2. Run the Installation Script

```bash
sudo ./scripts/install.sh
```

The installation script will:
- Install all required packages (Prosody, PostgreSQL, Nginx, Python 3)
- Set up the database with secure credentials
- Configure the backend and frontend
- Set up systemd services
- Configure firewall rules
- Generate configuration files

### 3. Set Up SSL Certificates

```bash
# Stop nginx temporarily
sudo systemctl stop nginx

# Get Let's Encrypt certificates
sudo certbot certonly --standalone -d acidbrns.cc -d upload.acidbrns.cc

# Copy certificates for Prosody
sudo cp /etc/letsencrypt/live/acidbrns.cc/fullchain.pem /etc/prosody/certs/acidbrns.cc.crt
sudo cp /etc/letsencrypt/live/acidbrns.cc/privkey.pem /etc/prosody/certs/acidbrns.cc.key
sudo chown prosody:prosody /etc/prosody/certs/*
sudo chmod 640 /etc/prosody/certs/*

# Generate DH parameters
sudo openssl dhparam -out /etc/nginx/dhparam.pem 2048

# Start nginx
sudo systemctl start nginx
```

### 4. Configure DNS Records

Add the following DNS records for your domain:

```
# A Record
acidbrns.cc         IN A     your_server_ip
upload.acidbrns.cc  IN A     your_server_ip

# SRV Records for XMPP
_xmpp-client._tcp.acidbrns.cc. IN SRV 5 0 5222 acidbrns.cc.
_xmpp-server._tcp.acidbrns.cc. IN SRV 5 0 5269 acidbrns.cc.
```

### 5. Restart Services

```bash
sudo systemctl restart prosody
sudo systemctl restart nginx
sudo systemctl restart xmpp-backend
```

### 6. Test the System

Visit `https://acidbrns.cc` to access the registration page.

## Manual Installation

If you prefer to install manually or customize the setup, follow these detailed steps:

### Install Dependencies

```bash
sudo apt-get update
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    postgresql postgresql-contrib \
    nginx certbot python3-certbot-nginx \
    prosody lua5.4 git curl
```

### Set Up Backend

```bash
# Create directories
sudo mkdir -p /var/www/xmpp-registration/backend
sudo mkdir -p /var/log/xmpp-backend

# Copy backend files
sudo cp -r backend/* /var/www/xmpp-registration/backend/

# Create virtual environment
cd /var/www/xmpp-registration/backend
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt

# Create .env file
sudo cp .env.example .env
sudo nano .env  # Edit with your settings
```

### Set Up Database

```bash
# Create database and user
sudo -u postgres psql <<EOF
CREATE DATABASE xmpp_registration;
CREATE USER xmpp_web WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE xmpp_registration TO xmpp_web;
\c xmpp_registration
GRANT USAGE ON SCHEMA public TO xmpp_web;
EOF

# Import schema
sudo -u postgres psql -d xmpp_registration -f config/database-schema.sql
```

### Set Up Prosody

```bash
# Fix Prosody shebang
sudo sed -i '1s|^#!/usr/bin/env lua.*|#!/usr/bin/lua5.4|' /usr/bin/prosody
sudo sed -i '1s|^#!/usr/bin/env lua.*|#!/usr/bin/lua5.4|' /usr/bin/prosodyctl

# Copy configuration
sudo cp config/prosody.cfg.lua /etc/prosody/prosody.cfg.lua
sudo chown root:prosody /etc/prosody/prosody.cfg.lua
sudo chmod 640 /etc/prosody/prosody.cfg.lua

# Set up permissions
sudo chown -R prosody:prosody /var/lib/prosody
sudo chmod -R 770 /var/lib/prosody
```

### Set Up Nginx

```bash
# Copy configuration
sudo cp config/nginx-site.conf /etc/nginx/sites-available/xmpp-registration
sudo ln -s /etc/nginx/sites-available/xmpp-registration /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t
```

### Set Up Systemd Service

```bash
# Copy service file
sudo cp config/xmpp-backend.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable xmpp-backend
sudo systemctl start xmpp-backend
```

### Set Up Permissions Script

```bash
# Copy script
sudo cp scripts/fix-prosody-perms.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/fix-prosody-perms.sh

# Install sudoers configuration
sudo cp config/xmpp-backend-sudoers /etc/sudoers.d/xmpp-backend
sudo chmod 0440 /etc/sudoers.d/xmpp-backend

# Add www-data to prosody group
sudo usermod -a -G prosody www-data
```

## Configuration

### Backend Environment Variables

Edit `/var/www/xmpp-registration/backend/.env`:

```env
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=xmpp_registration
DB_USER=xmpp_web
DB_PASSWORD=your_secure_password

# XMPP Configuration
XMPP_DOMAIN=acidbrns.cc
PROSODY_PATH=/usr/bin/prosodyctl
FIX_PERMS_SCRIPT=/usr/local/bin/fix-prosody-perms.sh

# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=False
```

### Prosody Configuration

Main configuration file: `/etc/prosody/prosody.cfg.lua`

Key settings:
- Authentication: `internal_hashed`
- TLS/SSL: Required for all connections
- Modules: MUC, HTTP upload, MAM (message archiving)
- File upload size: 10MB per file, 50MB daily quota

### Nginx Configuration

Configuration file: `/etc/nginx/sites-available/xmpp-registration`

Features:
- HTTPS enforcement with SSL/TLS
- Reverse proxy to Flask backend on port 5000
- Static file serving for frontend
- Security headers (HSTS, X-Frame-Options, etc.)
- Gzip compression

## API Endpoints

### `POST /api/register`

Register a new XMPP account.

**Request:**
```json
{
  "username": "testuser",
  "email": "test@example.com",
  "password": "SecurePass123"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Account erfolgreich erstellt",
  "jid": "testuser@acidbrns.cc"
}
```

**Response (Error):**
```json
{
  "error": "Benutzername bereits vergeben"
}
```

### `POST /api/check-username`

Check if a username is available.

**Request:**
```json
{
  "username": "testuser"
}
```

**Response:**
```json
{
  "available": true,
  "message": "Benutzername verfügbar"
}
```

### `GET /api/health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "prosody": "available"
}
```

## Security Considerations

1. **Password Hashing**: Uses bcrypt with salt for secure password storage
2. **Input Validation**: Strict validation on username, email, and password formats
3. **HTTPS Only**: All traffic encrypted with TLS 1.2+
4. **SQL Injection**: Protected via parameterized queries
5. **Rate Limiting**: Nginx rate limiting to prevent abuse
6. **File Permissions**: Strict file ownership and permissions
7. **Sudo Access**: Limited sudo access for specific operations only

## Troubleshooting

### Check Service Status

```bash
sudo systemctl status prosody
sudo systemctl status nginx
sudo systemctl status xmpp-backend
sudo systemctl status postgresql
```

### View Logs

```bash
# Backend logs
sudo journalctl -u xmpp-backend -f

# Nginx logs
sudo tail -f /var/log/nginx/xmpp-registration-error.log

# Prosody logs
sudo tail -f /var/log/prosody/prosody.log
```

### Common Issues

#### 1. Backend fails to start

Check for database connection issues:
```bash
sudo journalctl -u xmpp-backend -n 50
```

Verify database credentials in `/var/www/xmpp-registration/backend/.env`

#### 2. Prosody account creation fails

Check Prosody permissions:
```bash
sudo ls -la /var/lib/prosody/
sudo chown -R prosody:prosody /var/lib/prosody/
sudo chmod -R 770 /var/lib/prosody/
```

#### 3. SSL certificate errors

Verify certificates exist:
```bash
sudo ls -la /etc/letsencrypt/live/acidbrns.cc/
sudo ls -la /etc/prosody/certs/
```

Renew certificates if expired:
```bash
sudo certbot renew
```

#### 4. Permission denied errors

Ensure www-data is in prosody group:
```bash
sudo usermod -a -G prosody www-data
sudo systemctl restart xmpp-backend
```

## Maintenance

### Backup Database

```bash
# Backup
sudo -u postgres pg_dump xmpp_registration > backup_$(date +%Y%m%d).sql

# Restore
sudo -u postgres psql xmpp_registration < backup_20240101.sql
```

### Update SSL Certificates

Let's Encrypt certificates auto-renew. To manually renew:

```bash
sudo certbot renew
sudo systemctl reload nginx
sudo systemctl restart prosody
```

### Clean Up Old Accounts

```bash
# Connect to database
sudo -u postgres psql xmpp_registration

# Delete inactive accounts (example)
DELETE FROM users WHERE is_active = false AND created_at < NOW() - INTERVAL '1 year';
```

## Development

### Running Locally

```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your settings
python app.py

# Frontend
cd frontend
python3 -m http.server 8000
# Visit http://localhost:8000
```

### Testing

```bash
# Test API health
curl http://localhost:5000/api/health

# Test registration
curl -X POST http://localhost:5000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"TestPass123"}'
```

## Project Structure

```
acidbrns.cc/
├── backend/
│   ├── app.py                 # Flask application
│   ├── requirements.txt       # Python dependencies
│   ├── .env.example          # Environment template
│   └── .gitignore
├── frontend/
│   ├── index.html            # Registration page
│   ├── style.css             # Styling
│   └── script.js             # Frontend logic
├── config/
│   ├── nginx-site.conf       # Nginx configuration
│   ├── prosody.cfg.lua       # Prosody configuration
│   ├── xmpp-backend.service  # Systemd service
│   ├── database-schema.sql   # Database schema
│   └── xmpp-backend-sudoers  # Sudo configuration
├── scripts/
│   ├── install.sh            # Installation script
│   └── fix-prosody-perms.sh  # Permission fix script
└── README.md                  # This file
```

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Authors

- **acidboonrs** - *Initial work* - [acidboonrs](https://github.com/acidboonrs)

## Acknowledgments

- [Prosody XMPP Server](https://prosody.im/)
- [Flask Web Framework](https://flask.palletsprojects.com/)
- [PostgreSQL Database](https://www.postgresql.org/)
- [Nginx Web Server](https://nginx.org/)
- [Let's Encrypt](https://letsencrypt.org/)

## Support

For issues, questions, or contributions, please open an issue on GitHub:
https://github.com/acidboonrs/acidbrns.cc/issues

## Changelog

### Version 1.0.0 (2026-01-07)

- Initial release
- Web-based XMPP registration system
- Flask backend with PostgreSQL
- Modern frontend with real-time validation
- Complete installation and deployment scripts
- Production-ready with SSL/TLS support
