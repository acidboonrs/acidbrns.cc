#!/usr/bin/env python3
"""
XMPP Account Registration Backend
Flask API for creating XMPP accounts via web interface
"""

import os
import re
import subprocess
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2 import sql
import bcrypt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration from environment variables
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'xmpp_registration')
DB_USER = os.getenv('DB_USER', 'xmpp_web')
DB_PASSWORD = os.getenv('DB_PASSWORD')
XMPP_DOMAIN = os.getenv('XMPP_DOMAIN', 'acidbrns.cc')
PROSODY_PATH = os.getenv('PROSODY_PATH', '/usr/bin/prosodyctl')
FIX_PERMS_SCRIPT = os.getenv('FIX_PERMS_SCRIPT', '/usr/local/bin/fix-prosody-perms.sh')

def get_db_connection():
    """Create and return a database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        app.logger.error(f"Database connection error: {str(e)}")
        raise

def validate_username(username):
    """Validate username format"""
    # Username must be 3-32 characters, alphanumeric + underscore/hyphen
    if not re.match(r'^[a-z0-9_-]{3,32}$', username, re.IGNORECASE):
        return False, "Benutzername muss 3-32 Zeichen lang sein und darf nur Buchstaben, Zahlen, - und _ enthalten"
    return True, None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Passwort muss mindestens 8 Zeichen lang sein"
    if len(password) > 128:
        return False, "Passwort darf maximal 128 Zeichen lang sein"
    # Check for at least one letter and one number
    if not re.search(r'[a-zA-Z]', password) or not re.search(r'[0-9]', password):
        return False, "Passwort muss mindestens einen Buchstaben und eine Zahl enthalten"
    return True, None

def validate_email(email):
    """Validate email format"""
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        return False, "Ungültige E-Mail-Adresse"
    if len(email) > 254:
        return False, "E-Mail-Adresse zu lang"
    return True, None

def create_prosody_account(username, password):
    """Create account in Prosody XMPP server"""
    try:
        jid = f"{username}@{XMPP_DOMAIN}"

        # Call prosodyctl to create the account
        process = subprocess.Popen(
            [PROSODY_PATH, 'adduser', jid],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False
        )

        # Send password twice (for confirmation)
        password_input = f"{password}\n{password}\n".encode('utf-8')
        stdout, stderr = process.communicate(input=password_input, timeout=10)

        if process.returncode == 0:
            # Fix file permissions after account creation
            try:
                subprocess.run(
                    ['sudo', FIX_PERMS_SCRIPT],
                    timeout=5,
                    check=False,
                    capture_output=True
                )
            except Exception as e:
                app.logger.warning(f"Could not fix permissions: {str(e)}")

            return True, "Account erfolgreich erstellt"
        else:
            error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Unbekannter Fehler"
            app.logger.error(f"Prosody error: {error_msg}")
            return False, f"Prosody Fehler: {error_msg}"

    except subprocess.TimeoutExpired:
        app.logger.error("Prosodyctl timeout")
        return False, "Timeout bei Account-Erstellung"
    except Exception as e:
        app.logger.error(f"Exception creating Prosody account: {str(e)}")
        return False, f"Fehler bei Account-Erstellung: {str(e)}"

def delete_prosody_account(username):
    """Delete account from Prosody XMPP server (rollback)"""
    try:
        jid = f"{username}@{XMPP_DOMAIN}"

        # Call prosodyctl to delete the account
        process = subprocess.run(
            [PROSODY_PATH, 'deluser', jid],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10
        )

        if process.returncode == 0:
            app.logger.info(f"Successfully rolled back Prosody account: {jid}")
            return True, "Account gelöscht"
        else:
            error_msg = process.stderr.decode('utf-8', errors='ignore') if process.stderr else "Unbekannter Fehler"
            app.logger.error(f"Prosody delete error: {error_msg}")
            return False, f"Prosody Löschfehler: {error_msg}"

    except subprocess.TimeoutExpired:
        app.logger.error(f"Prosodyctl delete timeout for {username}")
        return False, "Timeout bei Account-Löschung"
    except Exception as e:
        app.logger.error(f"Exception deleting Prosody account: {str(e)}")
        return False, f"Fehler bei Account-Löschung: {str(e)}"

def create_database_account(username, email, password):
    """Create account record in PostgreSQL database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Hash password with bcrypt
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        # Insert user record
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, created_at)
            VALUES (%s, %s, %s, NOW())
            RETURNING id
            """,
            (username, email, password_hash.decode('utf-8'))
        )

        user_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        return True, user_id

    except psycopg2.IntegrityError as e:
        app.logger.error(f"Database integrity error: {str(e)}")
        if 'username' in str(e):
            return False, "Benutzername bereits vergeben"
        elif 'email' in str(e):
            return False, "E-Mail-Adresse bereits registriert"
        return False, "Benutzer existiert bereits"
    except Exception as e:
        app.logger.error(f"Database error: {str(e)}")
        return False, f"Datenbankfehler: {str(e)}"

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check database connection
        conn = get_db_connection()
        conn.close()

        # Check if prosodyctl is accessible
        result = subprocess.run(
            [PROSODY_PATH, 'about'],
            capture_output=True,
            timeout=5
        )

        prosody_ok = result.returncode == 0

        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'prosody': 'available' if prosody_ok else 'unavailable'
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503

@app.route('/api/register', methods=['POST'])
def register():
    """Register a new XMPP account"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Keine Daten empfangen'}), 400

        username = data.get('username', '').strip().lower()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        # Validate input
        if not username or not email or not password:
            return jsonify({'error': 'Alle Felder sind erforderlich'}), 400

        # Validate username
        valid, error = validate_username(username)
        if not valid:
            return jsonify({'error': error}), 400

        # Validate email
        valid, error = validate_email(email)
        if not valid:
            return jsonify({'error': error}), 400

        # Validate password
        valid, error = validate_password(password)
        if not valid:
            return jsonify({'error': error}), 400

        # Create Prosody account first
        success, message = create_prosody_account(username, password)
        if not success:
            app.logger.error(f"Failed to create Prosody account for {username}: {message}")
            return jsonify({'error': f'XMPP-Account konnte nicht erstellt werden: {message}'}), 500

        # Create database record
        success, result = create_database_account(username, email, password)
        if not success:
            app.logger.error(f"Failed to create database record for {username}: {result}")
            # Rollback Prosody account creation
            rollback_success, rollback_msg = delete_prosody_account(username)
            if not rollback_success:
                app.logger.error(f"Failed to rollback Prosody account for {username}: {rollback_msg}")
            return jsonify({'error': f'Datenbank-Eintrag konnte nicht erstellt werden: {result}'}), 500

        jid = f"{username}@{XMPP_DOMAIN}"
        app.logger.info(f"Successfully registered account: {jid}")

        return jsonify({
            'success': True,
            'message': 'Account erfolgreich erstellt',
            'jid': jid
        }), 201

    except Exception as e:
        app.logger.error(f"Registration error: {str(e)}")
        return jsonify({'error': 'Interner Serverfehler'}), 500

@app.route('/api/check-username', methods=['POST'])
def check_username():
    """Check if username is available"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip().lower()

        if not username:
            return jsonify({'available': False, 'error': 'Kein Benutzername angegeben'}), 400

        # Validate format
        valid, error = validate_username(username)
        if not valid:
            return jsonify({'available': False, 'error': error}), 400

        # Check database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        available = count == 0

        return jsonify({
            'available': available,
            'message': 'Benutzername verfügbar' if available else 'Benutzername bereits vergeben'
        }), 200

    except Exception as e:
        app.logger.error(f"Username check error: {str(e)}")
        return jsonify({'error': 'Fehler bei der Überprüfung'}), 500

if __name__ == '__main__':
    # Development server - use gunicorn in production
    app.run(host='127.0.0.1', port=5000, debug=False)
