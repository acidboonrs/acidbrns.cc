#!/bin/bash
#
# XMPP Registration System - Installation Script
# For Ubuntu/Debian systems with Prosody, PostgreSQL, and Nginx
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run this script as root or with sudo"
    exit 1
fi

print_info "Starting XMPP Registration System installation..."

# Variables
INSTALL_DIR="/var/www/xmpp-registration"
BACKEND_DIR="$INSTALL_DIR/backend"
FRONTEND_DIR="$INSTALL_DIR/frontend"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOMAIN="${XMPP_DOMAIN:-acidbrns.cc}"
DB_NAME="xmpp_registration"
DB_USER="xmpp_web"
DB_PASSWORD=""

# Generate secure password for database
generate_password() {
    openssl rand -hex 32
}

# Step 1: Update system packages
print_info "Updating system packages..."
apt-get update
apt-get upgrade -y

# Step 2: Install required packages
print_info "Installing required packages..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    postgresql \
    postgresql-contrib \
    nginx \
    certbot \
    python3-certbot-nginx \
    prosody \
    lua5.4 \
    git \
    curl

# Step 3: Create installation directory
print_info "Creating installation directories..."
mkdir -p "$BACKEND_DIR"
mkdir -p "$FRONTEND_DIR"
mkdir -p /var/log/xmpp-backend

# Step 4: Copy files
print_info "Copying application files..."
cp -r "$PROJECT_ROOT/backend/"* "$BACKEND_DIR/"
cp -r "$PROJECT_ROOT/frontend/"* "$FRONTEND_DIR/"
cp "$PROJECT_ROOT/config/nginx-site.conf" /etc/nginx/sites-available/xmpp-registration
cp "$PROJECT_ROOT/config/xmpp-backend.service" /etc/systemd/system/xmpp-backend.service
cp "$PROJECT_ROOT/scripts/fix-prosody-perms.sh" /usr/local/bin/fix-prosody-perms.sh

# Step 5: Set up Python virtual environment
print_info "Setting up Python virtual environment..."
cd "$BACKEND_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# Step 6: Set up PostgreSQL database
print_info "Setting up PostgreSQL database..."
DB_PASSWORD=$(generate_password)

# Create database and user
sudo -u postgres psql <<EOF
-- Create database
CREATE DATABASE $DB_NAME;

-- Create user
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';

-- Grant privileges
GRANT CONNECT ON DATABASE $DB_NAME TO $DB_USER;

-- Connect to database and set up schema
\c $DB_NAME

GRANT USAGE ON SCHEMA public TO $DB_USER;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO $DB_USER;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO $DB_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO $DB_USER;
EOF

# Import database schema
sudo -u postgres psql -d $DB_NAME -f "$PROJECT_ROOT/config/database-schema.sql"

# Step 7: Create .env file
print_info "Creating backend configuration..."
cat > "$BACKEND_DIR/.env" <<EOF
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD

# XMPP Configuration
XMPP_DOMAIN=$DOMAIN
PROSODY_PATH=/usr/bin/prosodyctl
FIX_PERMS_SCRIPT=/usr/local/bin/fix-prosody-perms.sh

# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=False
EOF

chmod 600 "$BACKEND_DIR/.env"

# Step 8: Fix Prosody shebang lines
print_info "Fixing Prosody script shebangs..."
if [ -f /usr/bin/prosody ]; then
    sed -i '1s|^#!/usr/bin/env lua.*|#!/usr/bin/lua5.4|' /usr/bin/prosody
fi
if [ -f /usr/bin/prosodyctl ]; then
    sed -i '1s|^#!/usr/bin/env lua.*|#!/usr/bin/lua5.4|' /usr/bin/prosodyctl
fi

# Step 9: Set up Prosody
print_info "Configuring Prosody..."
cp "$PROJECT_ROOT/config/prosody.cfg.lua" /etc/prosody/prosody.cfg.lua
chmod 640 /etc/prosody/prosody.cfg.lua
chown root:prosody /etc/prosody/prosody.cfg.lua

# Create Prosody certificate directory
mkdir -p /etc/prosody/certs
chown prosody:prosody /etc/prosody/certs
chmod 750 /etc/prosody/certs

# Step 10: Set up file permissions
print_info "Setting up file permissions..."
chown -R www-data:www-data "$INSTALL_DIR"
chown -R www-data:www-data /var/log/xmpp-backend

# Add www-data to prosody group
usermod -a -G prosody www-data

# Set up Prosody data directory permissions
chown -R prosody:prosody /var/lib/prosody
chmod -R 770 /var/lib/prosody

# Set up permission fix script
chmod +x /usr/local/bin/fix-prosody-perms.sh
chown root:root /usr/local/bin/fix-prosody-perms.sh

# Install sudoers configuration
cp "$PROJECT_ROOT/config/xmpp-backend-sudoers" /etc/sudoers.d/xmpp-backend
chmod 0440 /etc/sudoers.d/xmpp-backend
chown root:root /etc/sudoers.d/xmpp-backend

# Step 11: Request SSL certificates
print_info "Setting up SSL certificates..."
if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    print_warn "SSL certificates not found. Please run:"
    print_warn "  sudo certbot certonly --standalone -d $DOMAIN -d upload.$DOMAIN"
    print_warn "  sudo openssl dhparam -out /etc/nginx/dhparam.pem 2048"
else
    print_info "SSL certificates already exist"
fi

# Create dhparam if it doesn't exist
if [ ! -f "/etc/nginx/dhparam.pem" ]; then
    print_info "Generating DH parameters (this may take a while)..."
    openssl dhparam -out /etc/nginx/dhparam.pem 2048
fi

# Step 12: Configure Nginx
print_info "Configuring Nginx..."
ln -sf /etc/nginx/sites-available/xmpp-registration /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
nginx -t

# Step 13: Configure firewall
print_info "Configuring firewall..."
if command -v ufw &> /dev/null; then
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw allow 5222/tcp
    ufw allow 5269/tcp
    ufw allow 5280/tcp
    ufw --force enable
else
    print_warn "UFW not installed. Please configure firewall manually."
fi

# Step 14: Enable and start services
print_info "Enabling and starting services..."
systemctl daemon-reload
systemctl enable postgresql
systemctl enable prosody
systemctl enable nginx
systemctl enable xmpp-backend

systemctl restart postgresql
systemctl restart prosody
systemctl restart nginx
systemctl restart xmpp-backend

# Step 15: Print summary
print_info "Installation complete!"
echo ""
echo "==================================================================="
echo "  XMPP Registration System Installation Summary"
echo "==================================================================="
echo ""
echo "Installation directory: $INSTALL_DIR"
echo "Database name: $DB_NAME"
echo "Database user: $DB_USER"
echo "Database password: $DB_PASSWORD"
echo ""
echo "IMPORTANT: Save the database password in a secure location!"
echo ""
echo "Next steps:"
echo "1. Set up SSL certificates if not done:"
echo "   sudo certbot certonly --standalone -d $DOMAIN -d upload.$DOMAIN"
echo ""
echo "2. Copy SSL certificates for Prosody:"
echo "   sudo cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem /etc/prosody/certs/$DOMAIN.crt"
echo "   sudo cp /etc/letsencrypt/live/$DOMAIN/privkey.pem /etc/prosody/certs/$DOMAIN.key"
echo "   sudo chown prosody:prosody /etc/prosody/certs/*"
echo "   sudo chmod 640 /etc/prosody/certs/*"
echo ""
echo "3. Configure DNS records:"
echo "   - A record: $DOMAIN -> your_server_ip"
echo "   - SRV record: _xmpp-client._tcp.$DOMAIN -> $DOMAIN:5222"
echo "   - SRV record: _xmpp-server._tcp.$DOMAIN -> $DOMAIN:5269"
echo ""
echo "4. Restart all services:"
echo "   sudo systemctl restart prosody nginx xmpp-backend"
echo ""
echo "5. Visit https://$DOMAIN to test registration"
echo ""
echo "==================================================================="
