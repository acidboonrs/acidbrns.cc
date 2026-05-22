#!/usr/bin/env python3
"""
XMPP Registration Backend
Flask-App für Account-Registrierung mit PostgreSQL-Integration
Inkl. selbst gehostetem Bot-Schutz (Mathe-Captcha + Honeypot), serverseitig gerendert
"""

from flask import Flask, request, jsonify, Blueprint, render_template, abort, make_response
from flask_cors import CORS
from psycopg2 import pool as pg_pool
from psycopg2.extras import RealDictCursor
import bcrypt
import re
import os
import secrets
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.utils import formataddr
import subprocess
import random
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
# CORS nur für die eigene Domain erlauben (nicht wildcard!)
CORS(app, origins=[
    f"https://{os.getenv('XMPP_DOMAIN', 'acidbrns.cc')}"
])

# Konfiguration aus Umgebungsvariablen
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'xmpp_registration'),
    'user': os.getenv('DB_USER', 'xmpp_web'),
    'password': os.getenv('DB_PASSWORD', 'change-me'),
    'port': os.getenv('DB_PORT', '5432')
}

XMPP_DOMAIN = os.getenv('XMPP_DOMAIN', 'deine-domain.de')
PROSODY_PATH = os.getenv('PROSODY_PATH', '/usr/bin/prosodyctl')
# Validated wrapper for account ops: enforces username charset/length and a fixed
# domain, so the www-data->prosody sudo grant stays tightly scoped to one command.
PROSODY_ADMIN = os.getenv('PROSODY_ADMIN', '/usr/local/sbin/xmpp-prosody-admin')


# SMTP (Proton Mail) fuer Account-Recovery
MAIL_SERVER = os.getenv('MAIL_SERVER', '')
MAIL_PORT = int(os.getenv('MAIL_PORT', '587'))
MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
MAIL_FROM = os.getenv('MAIL_FROM', MAIL_USERNAME)
MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True') == 'True'
APP_BASE_URL = os.getenv('APP_BASE_URL', 'https://acidbrns.cc').rstrip('/')

RESET_TOKEN_TTL_MINUTES = 5

# In-Process Cache fuer /api/stats (pro gunicorn-Worker)
STATS_CACHE_TTL_SECONDS = 60
_stats_cache = {'data': None, 'expires_at': 0.0}

# DB Connection Pool
connection_pool = None


def init_pool():
    """Initialisiert den Datenbank-Connection-Pool"""
    global connection_pool
    try:
        connection_pool = pg_pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            **DB_CONFIG
        )
        print("Datenbank-Pool initialisiert")
    except Exception as e:
        print(f"Pool-Initialisierung fehlgeschlagen: {e}")


# =====================================================
# HELPER FUNCTIONS
# =====================================================

def get_db_connection():
    """Holt eine Verbindung aus dem Pool"""
    try:
        if connection_pool is None:
            init_pool()
        return connection_pool.getconn()
    except Exception as e:
        print(f"Datenbankfehler: {e}")
        return None


def release_db_connection(conn):
    """Gibt eine Verbindung an den Pool zurück"""
    if conn and connection_pool:
        connection_pool.putconn(conn)


def validate_username(username):
    """
    Validiert Username nach XMPP-Standards
    - 3-32 Zeichen
    - Nur Kleinbuchstaben, Zahlen, Bindestrich, Unterstrich
    """
    if not username or len(username) < 3 or len(username) > 32:
        return False, "Username muss zwischen 3 und 32 Zeichen lang sein"

    if not re.match(r'^[a-z0-9_-]+$', username):
        return False, "Username darf nur Kleinbuchstaben, Zahlen, - und _ enthalten"

    # Verbotene Usernames
    forbidden = ['admin', 'root', 'system', 'prosody', 'xmpp', 'support',
                 'postmaster', 'hostmaster', 'webmaster', 'abuse', 'noc',
                 'security', 'info', 'contact', 'help', 'mailer-daemon']
    if username in forbidden:
        return False, "Dieser Username ist reserviert"

    return True, "OK"


def validate_password(password):
    """
    Validiert Passwort-Stärke
    - Mindestens 12 Zeichen
    - Mindestens 1 Großbuchstabe, 1 Kleinbuchstabe, 1 Zahl, 1 Sonderzeichen
    """
    if not password or len(password) < 12:
        return False, "Passwort muss mindestens 12 Zeichen lang sein"

    if len(password) > 128:
        return False, "Passwort darf maximal 128 Zeichen lang sein"

    if not re.search(r'[A-Z]', password):
        return False, "Passwort muss mindestens einen Großbuchstaben enthalten"

    if not re.search(r'[a-z]', password):
        return False, "Passwort muss mindestens einen Kleinbuchstaben enthalten"

    if not re.search(r'[0-9]', password):
        return False, "Passwort muss mindestens eine Zahl enthalten"

    if not re.search(r'[^a-zA-Z0-9]', password):
        return False, "Passwort muss mindestens ein Sonderzeichen enthalten"

    return True, "OK"


def validate_email(email):
    """Validiert Email-Format"""
    if not email:
        return True, "OK"  # Email ist optional

    if len(email) > 254:
        return False, "Email-Adresse zu lang"

    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Ungültiges Email-Format"

    return True, "OK"


def check_rate_limit(ip_address):
    """
    Prueft Rate Limiting anhand der Datenbank (funktioniert ueber alle gunicorn-Worker).
    Zaehlt ALLE Registrierungs-Versuche pro IP (auch fehlgeschlagene), max. 5 / 24h.
    """
    conn = get_db_connection()
    if not conn:
        # Bei DB-Fehler: Registrierung erlauben, nicht blockieren
        return True, "OK"

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM registration_logs
            WHERE ip_address = %s
            AND action = 'registration_attempt'
            AND timestamp > NOW() - INTERVAL '24 hours'
        """, (ip_address,))
        count = cursor.fetchone()[0]
        cursor.close()

        if count >= 5:
            return False, "Zu viele Registrierungsversuche. Bitte versuche es in 24 Stunden erneut."
        return True, "OK"

    except Exception as e:
        print(f"Rate-Limit-Check fehlgeschlagen: {e}")
        return True, "OK"
    finally:
        release_db_connection(conn)




def check_onion_register_rate_limit():
    """
    Strikteres Rate-Limit fuer Registrierungen ueber den Onion-Mirror.
    Zaehlt Eintraege mit ip_address='onion' der letzten Stunde, max 3.
    Der Onion-Pfad hat keine echte Client-IP, daher dieses zusaetzliche
    globale Limit gegen Bot-Spam.
    """
    conn = get_db_connection()
    if not conn:
        return True, "OK"
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM registration_logs
            WHERE ip_address = '0.0.0.0'::inet
            AND action IN ('registration_attempt', 'onion_registration_attempt')
            AND timestamp > NOW() - INTERVAL '1 hour'
        """)
        count = cursor.fetchone()[0]
        cursor.close()
        if count >= 3:
            return False, "Zu viele Registrierungen ueber den Onion-Mirror in der letzten Stunde."
        return True, "OK"
    except Exception as e:
        print(f"Onion-Rate-Limit-Check fehlgeschlagen: {e}")
        return True, "OK"
    finally:
        release_db_connection(conn)

def check_ip_banned(ip_address):
    """Prüft ob eine IP gesperrt ist"""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM banned_ips
            WHERE ip_address = %s
            AND (permanent = TRUE OR banned_until > NOW())
        """, (ip_address,))
        count = cursor.fetchone()[0]
        cursor.close()
        return count > 0
    except Exception:
        return False
    finally:
        release_db_connection(conn)


def hash_password(password):
    """Erstellt bcrypt Hash vom Passwort"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def create_prosody_account(username, password):
    """
    Erstellt Account mit prosodyctl via sudo (als prosody-User).
    Passwort wird über stdin übergeben, nicht als Kommandozeilen-Argument,
    um Exposition in der Prozessliste (ps aux) zu vermeiden.
    """
    try:
        # Sicherheits-Check: Username nochmal validieren gegen Command Injection
        if not re.match(r'^[a-z0-9_-]+$', username):
            return False, "Ungültiger Username"

        # Account erstellen via sudo als prosody-User
        # Passwort via stdin, NICHT als CLI-Argument (wäre in ps aux sichtbar)
        result = subprocess.run(
            ['/usr/bin/sudo', '-u', 'prosody', PROSODY_ADMIN, 'register', username],
            input=f"{password}\n{password}\n",
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
            # Keine internen Pfade oder Details an den User leaken
            if "exists" in error_msg.lower() or "already" in error_msg.lower():
                return False, "Account existiert bereits in Prosody"
            return False, "Prosody-Account konnte nicht erstellt werden"

        return True, "Account erfolgreich erstellt"

    except subprocess.TimeoutExpired:
        return False, "Prosody-Timeout bei Account-Erstellung"
    except Exception as e:
        # Keine internen Fehlerdetails leaken
        print(f"Prosody Account-Erstellung fehlgeschlagen: {e}")
        return False, "Interner Fehler bei Account-Erstellung"


def prosody_change_password(username, new_password):
    """Aendert das Prosody-Passwort. Passwort via stdin."""
    if not re.match(r'^[a-z0-9_-]+$', username):
        return False, "Ungueltiger Username"
    try:
        result = subprocess.run(
            ['/usr/bin/sudo', '-u', 'prosody', PROSODY_ADMIN, 'passwd', username],
            input=f"{new_password}\n{new_password}\n",
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(f"prosodyctl passwd fehlgeschlagen: {result.stderr or result.stdout}")
            return False, "Passwort-Aenderung in Prosody fehlgeschlagen"
        return True, "OK"
    except subprocess.TimeoutExpired:
        return False, "Prosody-Timeout"
    except Exception as e:
        print(f"prosodyctl passwd Exception: {e}")
        return False, "Interner Fehler"


def prosody_delete_account(username):
    """Loescht den Prosody-Account."""
    if not re.match(r'^[a-z0-9_-]+$', username):
        return False, "Ungueltiger Username"
    try:
        result = subprocess.run(
            ['/usr/bin/sudo', '-u', 'prosody', PROSODY_ADMIN, 'deluser', username],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout).lower()
            # Wenn der Account in Prosody nicht (mehr) existiert: trotzdem als Erfolg behandeln,
            # damit die DB-Loeschung weiterlaufen kann.
            if 'not exist' in err or 'no such' in err:
                return True, "OK"
            print(f"prosodyctl deluser fehlgeschlagen: {result.stderr or result.stdout}")
            return False, "Account-Loeschung in Prosody fehlgeschlagen"
        return True, "OK"
    except subprocess.TimeoutExpired:
        return False, "Prosody-Timeout"
    except Exception as e:
        print(f"prosodyctl deluser Exception: {e}")
        return False, "Interner Fehler"


def verify_account_password(username, password):
    """Prueft Username+Passwort gegen den bcrypt-Hash in der DB.
    Gibt (user_dict | None, error_message) zurueck.
    """
    conn = get_db_connection()
    if not conn:
        return None, "Datenbankfehler"
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT id, username, email, password_hash, is_active
            FROM xmpp_users
            WHERE username = %s AND domain = %s
        """, (username, XMPP_DOMAIN))
        user = cursor.fetchone()
        cursor.close()
        if not user or not user['is_active']:
            return None, "Ungueltige Anmeldedaten"
        if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            return None, "Ungueltige Anmeldedaten"
        return dict(user), "OK"
    except Exception as e:
        print(f"verify_account_password: {e}")
        return None, "Pruefung fehlgeschlagen"
    finally:
        release_db_connection(conn)


def send_email(to_address, subject, body_text):
    """Versendet eine Plain-Text-Email via Proton-SMTP (STARTTLS).
    Gibt (success: bool, error: str) zurueck.
    """
    if not MAIL_SERVER or not MAIL_USERNAME or not MAIL_PASSWORD:
        print("WARNUNG: SMTP nicht konfiguriert - Mail wird nicht versendet")
        return False, "SMTP nicht konfiguriert"

    msg = MIMEText(body_text, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = formataddr(('acidbrns.cc', MAIL_FROM))
    msg['To'] = to_address

    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=15) as smtp:
            smtp.ehlo()
            if MAIL_USE_TLS:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(MAIL_USERNAME, MAIL_PASSWORD)
            smtp.sendmail(MAIL_FROM, [to_address], msg.as_string())
        return True, "OK"
    except Exception as e:
        print(f"SMTP-Fehler: {e}")
        return False, "Mail-Versand fehlgeschlagen"


def check_account_rate_limit(ip_address, action, max_count, hours):
    """Limitiert Login/Reset-Versuche pro IP."""
    conn = get_db_connection()
    if not conn:
        return True, "OK"
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM registration_logs
            WHERE ip_address = %s AND action = %s
            AND timestamp > NOW() - (%s || ' hours')::interval
        """, (ip_address, action, str(int(hours))))
        count = cursor.fetchone()[0]
        cursor.close()
        if count >= max_count:
            return False, "Zu viele Versuche. Bitte spaeter erneut probieren."
        return True, "OK"
    except Exception as e:
        print(f"Rate-Limit-Check ({action}): {e}")
        return True, "OK"
    finally:
        release_db_connection(conn)


def log_action(user_id, action, ip_address, success, user_agent=None, error_message=None):
    """Schreibt einen Eintrag in registration_logs."""
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO registration_logs
            (user_id, action, ip_address, user_agent, timestamp, success, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, action, ip_address, (user_agent or '')[:500],
              datetime.now(), success, (error_message or '')[:500] or None))
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"log_action: {e}")
    finally:
        release_db_connection(conn)


# =====================================================
# API ROUTES
# =====================================================

@app.route('/api/')
def api_index():
    """API-Discovery (frueher GET /). Wird seit clearnet_bp uebernommen."""
    return jsonify({
        'service': 'XMPP Registration API',
        'version': '2.0.0',
        'domain': XMPP_DOMAIN,
        'endpoints': {
            'check_username': '/api/check-username/<username> (GET)',
            'status': '/api/status (GET)',
            'stats': '/api/stats (GET)'
        }
    })


@app.route('/api/status', methods=['GET'])
def status():
    """API Status Check"""
    try:
        conn = get_db_connection()
        if conn:
            release_db_connection(conn)
            db_status = "connected"
        else:
            db_status = "disconnected"
    except Exception:
        db_status = "error"

    return jsonify({
        'status': 'online',
        'database': db_status,
        'domain': XMPP_DOMAIN,
        'captcha': 'math',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/check-username/<username>', methods=['GET'])
def check_username(username):
    """Prüft ob Username verfügbar ist"""
    ip_address = request.headers.get('X-Real-IP', request.remote_addr)

    # IP-Ban + Rate-Limit (gegen User-Enumeration)
    if check_ip_banned(ip_address):
        return jsonify({'available': False, 'reason': 'Zugang gesperrt'}), 403

    ok, msg = check_account_rate_limit(ip_address, 'username_check', max_count=30, hours=1)
    if not ok:
        return jsonify({'available': False, 'reason': msg}), 429

    # Validierung
    is_valid, message = validate_username(username)
    if not is_valid:
        return jsonify({
            'available': False,
            'reason': message
        }), 400

    # Datenbankprüfung
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Datenbankfehler'}), 500

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM xmpp_users WHERE username = %s AND domain = %s",
            (username, XMPP_DOMAIN)
        )
        count = cursor.fetchone()[0]
        cursor.close()

        # Log fuer Rate-Limit (jede Anfrage zaehlt, unabhaengig vom Ergebnis)
        log_action(None, 'username_check', ip_address, True,
                   user_agent=request.headers.get('User-Agent'))

        if count > 0:
            return jsonify({
                'available': False,
                'reason': 'Username bereits vergeben'
            })

        return jsonify({
            'available': True,
            'jid': f"{username}@{XMPP_DOMAIN}"
        })

    except Exception as e:
        print(f"Username-Check Fehler: {e}")
        return jsonify({'error': 'Prüfung fehlgeschlagen'}), 500
    finally:
        release_db_connection(conn)


@app.route('/api/stats', methods=['GET'])
def stats():
    """Oeffentliche Statistiken (gecached pro Worker, 60s)"""
    now = time.monotonic()
    if _stats_cache['data'] is not None and _stats_cache['expires_at'] > now:
        return jsonify(_stats_cache['data'])

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Datenbankfehler'}), 500

    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT COUNT(*) as total FROM xmpp_users WHERE is_active = true")
        total_users = cursor.fetchone()['total']

        cursor.execute("""
            SELECT COUNT(*) as today
            FROM xmpp_users
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        today_registrations = cursor.fetchone()['today']

        cursor.close()

        payload = {
            'total_users': total_users,
            'registrations_today': today_registrations,
            'domain': XMPP_DOMAIN
        }
        _stats_cache['data'] = payload
        _stats_cache['expires_at'] = now + STATS_CACHE_TTL_SECONDS
        return jsonify(payload)

    except Exception as e:
        print(f"Stats-Fehler: {e}")
        return jsonify({'error': 'Statistiken nicht verfuegbar'}), 500
    finally:
        release_db_connection(conn)




# Pool beim Start initialisieren
with app.app_context():
    init_pool()



# =====================================================
# ONION BLUEPRINT - JS-freie Routes fuer Tor-Mirror
# =====================================================
# Erreichbar nur ueber den nginx onion-mirror (X-Onion-Request:1).
# Liefert HTML-Antworten statt JSON; Forms posten klassisch (kein fetch/JS).

onion_bp = Blueprint('onion', __name__, url_prefix='/api/onion',
                     template_folder='templates')


@onion_bp.before_request
def _onion_only():
    if request.headers.get('X-Onion-Request') != '1':
        abort(404)


def _render_register_error(errors, username='', email=''):
    return render_template('onion_register_error.html',
                           errors=errors, username=username, email=email)


def _render_onion_register_form(errors=None, username='', email='', status=200):
    """Server-gerendertes Onion-Registrierungsformular mit frischem Mathe-Captcha.
    Wird fuer GET und fuer wiederholbare Formularfehler verwendet."""
    q, t = new_math_challenge()
    return render_template('onion_register_form.html',
                           errors=errors or [],
                           username=username, email=email,
                           math_question=q, math_token=t), status


@onion_bp.route('/register', methods=['GET', 'POST'])
def onion_register():
    if request.method == 'GET':
        # Server-gerendertes Formular mit frischem Mathe-Token (Bot-Schutz).
        return _render_onion_register_form()

    username = (request.form.get('username') or '').lower().strip()
    password = request.form.get('password') or ''
    password2 = request.form.get('password2') or ''
    email_raw = (request.form.get('email') or '').strip()
    email = email_raw or None
    privacy_ok = request.form.get('privacy') == 'on'
    math_token = request.form.get('math_token') or ''
    math_answer = request.form.get('math_answer') or ''

    # registration_ip ist Postgres-INET-Typ — kann keine Strings wie 'onion' speichern.
    # Sentinel-IP 0.0.0.0 markiert Onion-Registrierungen in xmpp_users und
    # registration_logs (NOT NULL inet). check_onion_register_rate_limit zaehlt diese.
    ip_address = '0.0.0.0'

    # Honeypot: unsichtbares Feld muss leer bleiben (Bot-Schutz, JS-frei)
    if honeypot_tripped():
        return _render_onion_register_form(['Bot-Schutz ausgeloest.'],
                                           username, email_raw, status=400)

    # Globaler Onion-IP-Ban (auch wenn unwahrscheinlich, dass jemand 'onion' bannt)
    if check_ip_banned(ip_address):
        return _render_register_error(['Zugang gesperrt'], username, email_raw), 403

    # Jeden Versuch loggen — Onion-Rate-Limit zaehlt nur 'registration_attempt'-Logs
    log_action(None, 'registration_attempt', ip_address, True,
               user_agent=request.headers.get('User-Agent'))

    # Mathe-Captcha pruefen (signierter Token, 10 min gueltig) — Bot-Schutz
    if not verify_math(math_token, math_answer):
        return _render_onion_register_form(
            ['Mathe-Antwort falsch oder abgelaufen.'],
            username, email_raw, status=400)

    ok, msg = check_onion_register_rate_limit()
    if not ok:
        return _render_register_error([msg], username, email_raw), 429

    errors = []
    if not privacy_ok:
        errors.append('Bitte die Datenschutzerklaerung akzeptieren.')
    if password != password2:
        errors.append('Die beiden Passwoerter stimmen nicht ueberein.')

    v, m = validate_username(username)
    if not v:
        errors.append(m)
    v, m = validate_password(password)
    if not v:
        errors.append(m)
    if email:
        v, m = validate_email(email)
        if not v:
            errors.append(m)

    if errors:
        return _render_onion_register_form(errors, username, email_raw, status=400)

    conn = get_db_connection()
    if not conn:
        return _render_register_error(['Datenbankverbindung fehlgeschlagen.'],
                                      username, email_raw), 500

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM xmpp_users WHERE username = %s AND domain = %s",
            (username, XMPP_DOMAIN)
        )
        if cursor.fetchone()[0] > 0:
            cursor.close()
            return _render_onion_register_form(['Username bereits vergeben.'],
                                               '', email_raw, status=409)

        if email:
            cursor.execute(
                "SELECT COUNT(*) FROM xmpp_users WHERE email = %s",
                (email,)
            )
            if cursor.fetchone()[0] > 0:
                cursor.close()
                log_action(None, 'register_email_collision', ip_address, False,
                           user_agent=request.headers.get('User-Agent'),
                           error_message=f"email_exists:{email[:60]}")
                return _render_register_error([
                    'Registrierung nicht moeglich. Falls du bereits einen Account hast, '
                    'nutze die Passwort-Zuruecksetzung.'
                ], username, ''), 400

        password_hash = hash_password(password)

        success, prosody_message = create_prosody_account(username, password)
        if not success:
            cursor.close()
            return _render_register_error([
                f'XMPP-Account konnte nicht erstellt werden: {prosody_message}'
            ], username, email_raw), 500

        cursor.execute("""
            INSERT INTO xmpp_users
            (username, domain, password_hash, email, registration_ip, created_at, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (username, XMPP_DOMAIN, password_hash, email, ip_address,
              datetime.now(), True))
        user_id = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO registration_logs
            (user_id, action, ip_address, user_agent, timestamp, success)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, 'registration', ip_address,
              request.headers.get('User-Agent', 'unknown')[:500],
              datetime.now(), True))

        conn.commit()
        cursor.close()

        return render_template(
            'onion_register_success.html',
            jid=f"{username}@{XMPP_DOMAIN}",
            domain=XMPP_DOMAIN,
        ), 201

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Onion-Registrierungsfehler: {e}")
        return _render_register_error(['Serverfehler bei der Registrierung.'],
                                      username, email_raw), 500
    finally:
        release_db_connection(conn)



# =====================================================
# ONION BLUEPRINT — Phase 2 (Account-Mgmt) + Phase 3 (Reset)
# =====================================================
# Stateless: kein Session-Cookie. Jede aendernde Operation traegt
# username + Passwort als Form-Felder, die wie bei der JSON-API gegen
# den bcrypt-Hash geprueft werden. Auf Onion ist das akzeptabel und
# reduziert Angriffsflaeche (keine CSRF-Tokens, kein Session-Storage).

ONION_BASE_URL = os.getenv('ONION_BASE_URL',
    'http://6uolpn5semitqdrjgawl4te7o6tn636bacvcjux6lyf7vh4kc4giglid.onion'
).rstrip('/')

ONION_IP_SENTINEL = '0.0.0.0'


def _onion_account_error(errors):
    return render_template('onion_account_error.html', errors=errors)


@onion_bp.route('/account/change-password', methods=['POST'])
def onion_change_password():
    username = (request.form.get('username') or '').lower().strip()
    current_password = request.form.get('current_password') or ''
    new_password = request.form.get('new_password') or ''
    new_password2 = request.form.get('new_password2') or ''
    ip = ONION_IP_SENTINEL

    if check_ip_banned(ip):
        return _onion_account_error(['Zugang gesperrt']), 403

    ok, msg = check_account_rate_limit(ip, 'password_change_failed', max_count=10, hours=1)
    if not ok:
        return _onion_account_error([msg]), 429

    user, err = verify_account_password(username, current_password)
    if not user:
        log_action(None, 'password_change_failed', ip, False,
                   user_agent=request.headers.get('User-Agent'), error_message=err)
        return _onion_account_error([err]), 401

    errors = []
    if new_password != new_password2:
        errors.append('Die beiden neuen Passwoerter stimmen nicht ueberein.')
    is_valid, vmsg = validate_password(new_password)
    if not is_valid:
        errors.append(vmsg)
    if not errors and new_password == current_password:
        errors.append('Neues Passwort muss sich vom alten unterscheiden.')
    if errors:
        return _onion_account_error(errors), 400

    success, pmsg = prosody_change_password(username, new_password)
    if not success:
        return _onion_account_error([pmsg]), 500

    new_hash = hash_password(new_password)
    conn = get_db_connection()
    if not conn:
        return _onion_account_error(['Datenbankfehler']), 500
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE xmpp_users SET password_hash = %s WHERE id = %s",
            (new_hash, user['id'])
        )
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"Onion change-pw DB-Fehler: {e}")
        return _onion_account_error(['Datenbankfehler']), 500
    finally:
        release_db_connection(conn)

    log_action(user['id'], 'password_change', ip, True,
               user_agent=request.headers.get('User-Agent'))
    return render_template('onion_account_changed.html',
                           jid=f"{username}@{XMPP_DOMAIN}")


@onion_bp.route('/account/delete', methods=['POST'])
def onion_account_delete():
    username = (request.form.get('username') or '').lower().strip()
    password = request.form.get('password') or ''
    confirm = request.form.get('confirm') == 'on'
    ip = ONION_IP_SENTINEL

    if check_ip_banned(ip):
        return _onion_account_error(['Zugang gesperrt']), 403

    ok, msg = check_account_rate_limit(ip, 'delete_failed', max_count=10, hours=1)
    if not ok:
        return _onion_account_error([msg]), 429

    if not confirm:
        return _onion_account_error([
            'Bitte die Bestaetigungs-Checkbox aktivieren — Account-Loeschung ist endgueltig.'
        ]), 400

    user, err = verify_account_password(username, password)
    if not user:
        log_action(None, 'delete_failed', ip, False,
                   user_agent=request.headers.get('User-Agent'), error_message=err)
        return _onion_account_error([err]), 401

    success, pmsg = prosody_delete_account(username)
    if not success:
        return _onion_account_error([pmsg]), 500

    conn = get_db_connection()
    if not conn:
        return _onion_account_error(['Datenbankfehler']), 500
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM xmpp_users WHERE id = %s", (user['id'],))
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"Onion delete DB-Fehler: {e}")
        return _onion_account_error(['Datenbankfehler']), 500
    finally:
        release_db_connection(conn)

    log_action(None, 'account_deleted', ip, True,
               user_agent=request.headers.get('User-Agent'),
               error_message=f"username={username}")
    return render_template('onion_account_deleted.html', jid=f"{username}@{XMPP_DOMAIN}")


@onion_bp.route('/reset/request', methods=['POST'])
def onion_reset_request():
    identifier = (request.form.get('identifier') or '').strip().lower()
    ip = ONION_IP_SENTINEL

    if check_ip_banned(ip):
        return _onion_account_error(['Zugang gesperrt']), 403

    ok, msg = check_account_rate_limit(ip, 'reset_request', max_count=5, hours=1)
    if not ok:
        return _onion_account_error([msg]), 429

    # Generische Antwort gegen User-Enumeration
    generic = render_template('onion_reset_requested.html')

    if not identifier:
        return generic

    conn = get_db_connection()
    if not conn:
        return generic
    user = None
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT id, username, email FROM xmpp_users
            WHERE (username = %s OR email = %s) AND domain = %s AND is_active = TRUE
            LIMIT 1
        """, (identifier, identifier, XMPP_DOMAIN))
        user = cursor.fetchone()
        cursor.close()

        log_action(user['id'] if user else None, 'reset_request', ip,
                   bool(user and user.get('email')),
                   user_agent=request.headers.get('User-Agent'),
                   error_message=None if user else f"no_account:{identifier[:50]}")

        if not user or not user.get('email'):
            return generic

        cursor = conn.cursor()
        cursor.execute("""
            UPDATE password_reset_tokens SET used_at = NOW()
            WHERE user_id = %s AND used_at IS NULL
        """, (user['id'],))

        token = secrets.token_urlsafe(48)
        expires = datetime.now() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
        cursor.execute("""
            INSERT INTO password_reset_tokens (user_id, token, expires_at, request_ip)
            VALUES (%s, %s, %s, %s)
        """, (user['id'], token, expires, ip))
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"Onion Reset-Request-Fehler: {e}")
        return generic
    finally:
        release_db_connection(conn)

    # Mail mit Onion-Link versenden (statt clearnet APP_BASE_URL)
    reset_url = f"{ONION_BASE_URL}/api/onion/reset/confirm?token={token}"
    body = (
        f"Hallo {user['username']},\n\n"
        f"fuer deinen Account {user['username']}@{XMPP_DOMAIN} wurde ueber den\n"
        f"Onion-Mirror eine Passwort-Zuruecksetzung angefordert.\n\n"
        f"Oeffne den folgenden Link im Tor-Browser, um ein neues Passwort zu setzen\n"
        f"(gueltig fuer {RESET_TOKEN_TTL_MINUTES} Minuten):\n\n"
        f"{reset_url}\n\n"
        f"Falls du diese Anfrage nicht gestellt hast, ignoriere diese Mail einfach.\n\n"
        f"-- acidbrns.cc (Onion-Mirror)\n"
    )
    send_email(user['email'], "Passwort zuruecksetzen (Onion) - acidbrns.cc", body)
    return generic


@onion_bp.route('/reset/confirm', methods=['GET', 'POST'])
def onion_reset_confirm():
    if request.method == 'GET':
        token = (request.args.get('token') or '').strip()
        if not token or len(token) < 32:
            return render_template('onion_reset_form.html',
                                   token='', errors=['Ungueltiger oder fehlender Token.']), 400
        return render_template('onion_reset_form.html', token=token, errors=[])

    token = (request.form.get('token') or '').strip()
    new_password = request.form.get('new_password') or ''
    new_password2 = request.form.get('new_password2') or ''
    ip = ONION_IP_SENTINEL

    if check_ip_banned(ip):
        return render_template('onion_reset_form.html',
                               token=token, errors=['Zugang gesperrt']), 403

    ok, msg = check_account_rate_limit(ip, 'reset_confirm_failed', max_count=10, hours=1)
    if not ok:
        return render_template('onion_reset_form.html',
                               token=token, errors=[msg]), 429

    errors = []
    if not token or len(token) < 32:
        errors.append('Ungueltiger Token.')
    if new_password != new_password2:
        errors.append('Die beiden neuen Passwoerter stimmen nicht ueberein.')
    is_valid, vmsg = validate_password(new_password)
    if not is_valid:
        errors.append(vmsg)
    if errors:
        return render_template('onion_reset_form.html',
                               token=token, errors=errors), 400

    conn = get_db_connection()
    if not conn:
        return render_template('onion_reset_form.html',
                               token=token, errors=['Datenbankfehler']), 500
    row = None
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT t.id AS token_id, t.expires_at, t.used_at,
                   u.id AS user_id, u.username, u.is_active
            FROM password_reset_tokens t
            JOIN xmpp_users u ON u.id = t.user_id
            WHERE t.token = %s
            LIMIT 1
        """, (token,))
        row = cursor.fetchone()

        if not row:
            log_action(None, 'reset_confirm_failed', ip, False,
                       user_agent=request.headers.get('User-Agent'),
                       error_message='token_not_found')
            return render_template('onion_reset_form.html',
                                   token='', errors=['Ungueltiger oder abgelaufener Token.']), 400
        if row['used_at'] is not None:
            return render_template('onion_reset_form.html',
                                   token='', errors=['Token bereits verwendet.']), 400
        if row['expires_at'] < datetime.now():
            return render_template('onion_reset_form.html',
                                   token='', errors=['Token abgelaufen.']), 400
        if not row['is_active']:
            return render_template('onion_reset_form.html',
                                   token='', errors=['Account ist deaktiviert.']), 400

        username = row['username']
        success, pmsg = prosody_change_password(username, new_password)
        if not success:
            return render_template('onion_reset_form.html',
                                   token=token, errors=[pmsg]), 500

        new_hash = hash_password(new_password)
        cursor.close()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE xmpp_users SET password_hash = %s WHERE id = %s",
            (new_hash, row['user_id'])
        )
        cursor.execute(
            "UPDATE password_reset_tokens SET used_at = NOW() WHERE id = %s",
            (row['token_id'],)
        )
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"Onion Reset-Confirm-Fehler: {e}")
        if conn:
            conn.rollback()
        return render_template('onion_reset_form.html',
                               token=token, errors=['Datenbankfehler']), 500
    finally:
        release_db_connection(conn)

    log_action(row['user_id'], 'password_reset', ip, True,
               user_agent=request.headers.get('User-Agent'))
    return render_template('onion_reset_done.html',
                           jid=f"{row['username']}@{XMPP_DOMAIN}")


app.register_blueprint(onion_bp)


# =====================================================
# CLEARNET BLUEPRINT — JS-freie Routes fuer Clearnet
# =====================================================
# Spiegelung der Onion-Routen, mit Math-Captcha + Honeypot als Bot-Schutz
# und echter Client-IP (X-Real-IP) fuer Rate-Limiting.

MATH_SECRET = os.getenv('MATH_CAPTCHA_SECRET', secrets.token_urlsafe(32))
_math_signer = URLSafeTimedSerializer(MATH_SECRET, salt='math-captcha')
MATH_TTL = 600  # 10 min

# ── tdwall Gate ────────────────────────────────────────────────────────────────
TDWALL_SECRET  = os.getenv('TDWALL_SECRET', secrets.token_urlsafe(32))
_tdwall_signer = URLSafeTimedSerializer(TDWALL_SECRET, salt='tdwall-gate')
TDWALL_COOKIE_TTL   = 86400   # 24 h  — Cookie-Lebenszeit
TDWALL_TOKEN_TTL    = 120     # 2 min — URL-Token nach meta-refresh (kurz, einmalig)
TDWALL_COOKIE_NAME  = 'tdw'
TDWALL_SPLASH_DELAY = 5       # Sekunden bis meta-refresh

# Rate-Limit für tdwall_events-Inserts (Schutz gegen DDoS-Amplification)
_tdwall_rate = {'count': 0, 'window_start': 0.0}
_TDWALL_MAX_PER_MIN = 120     # max. DB-Schreibvorgänge pro Minute

def _tdwall_make_rayid() -> str:
    """Kurze hex-ID für RAYID-Anzeige (16 Zeichen)."""
    return secrets.token_hex(8).upper()

def _tdwall_make_token(rayid: str) -> str:
    """Signiertes URL-Token das rayid einschließt."""
    return _tdwall_signer.dumps(rayid)

def _tdwall_verify_token(token: str):
    """Gibt rayid zurück wenn Token gültig + frisch, sonst None."""
    if not token:
        return None
    try:
        return _tdwall_signer.loads(token, max_age=TDWALL_TOKEN_TTL)
    except (BadSignature, SignatureExpired):
        return None

def _tdwall_verify_cookie(cookie_val: str):
    """Gibt rayid zurück wenn Cookie gültig, sonst None."""
    if not cookie_val:
        return None
    try:
        return _tdwall_signer.loads(cookie_val, max_age=TDWALL_COOKIE_TTL)
    except (BadSignature, SignatureExpired):
        return None

def _tdwall_log(rayid: str, ip, path: str, ua: str, is_onion: bool):
    """Best-effort, rate-limitiertes INSERT in tdwall_events. Blockiert nicht."""
    now = time.monotonic()
    # Rate-Limit-Fenster zurücksetzen
    if now - _tdwall_rate['window_start'] >= 60:
        _tdwall_rate['count'] = 0
        _tdwall_rate['window_start'] = now
    if _tdwall_rate['count'] >= _TDWALL_MAX_PER_MIN:
        return  # stillschweigend überspringen
    _tdwall_rate['count'] += 1
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tdwall_events (rayid, ip_address, path, user_agent, is_onion) "
            "VALUES (%s, %s, %s, %s, %s)",
            (rayid, ip, path[:500] if path else None,
             ua[:500] if ua else None, is_onion)
        )
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"tdwall_log Fehler: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        release_db_connection(conn)

def _tdwall_ok():
    """
    Gibt (passed: bool, rayid_or_None) zurück.

    Akzeptiert:
      1. Gültiges Cookie  (24 h)
      2. Gültiges URL-Token ?gate=…  (2 min, nach meta-refresh gesetzt)
    Cookie-lose Browser (Tor, strict-mode) kommen über Token durch — kein Loop.
    """
    cookie_val = request.cookies.get(TDWALL_COOKIE_NAME, '')
    rayid = _tdwall_verify_cookie(cookie_val)
    if rayid:
        return True, rayid

    token = request.args.get('gate', '')
    rayid = _tdwall_verify_token(token)
    if rayid:
        return True, rayid

    return False, None


def new_math_challenge():
    a = random.randint(2, 9)
    b = random.randint(2, 9)
    # Embed a one-time nonce so a solved (token, answer) pair cannot be replayed
    # within its TTL window. Legacy int-only tokens are still tolerated by
    # verify_math during the deploy transition.
    payload = {'s': a + b, 'n': secrets.token_urlsafe(9)}
    return f"{a} + {b}", _math_signer.dumps(payload)


def _consume_math_nonce(nonce):
    """Single-use guard for math-captcha tokens, shared across gunicorn workers via DB.
    Returns True if the nonce was unused (and marks it used now), False if it was
    already used (replay). Fails OPEN on any DB error so a hiccup never blocks
    legitimate registrations."""
    if not nonce:
        return True  # legacy token without nonce — accept (transition only)
    conn = get_db_connection()
    if not conn:
        return True
    try:
        cur = conn.cursor()
        # opportunistic cleanup of expired nonces (keeps the table tiny)
        cur.execute(
            "DELETE FROM used_math_tokens WHERE used_at < NOW() - make_interval(secs => %s)",
            (int(MATH_TTL),))
        cur.execute(
            "INSERT INTO used_math_tokens (nonce) VALUES (%s) ON CONFLICT (nonce) DO NOTHING",
            (nonce,))
        fresh = (cur.rowcount == 1)
        conn.commit()
        cur.close()
        return fresh
    except Exception as e:
        print(f"_consume_math_nonce: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return True
    finally:
        release_db_connection(conn)


def verify_math(token, answer):
    if not token or answer is None or str(answer).strip() == '':
        return False
    try:
        data = _math_signer.loads(token, max_age=MATH_TTL)
    except (BadSignature, SignatureExpired):
        return False
    # New tokens are dicts {'s': sum, 'n': nonce}; tolerate legacy int tokens briefly.
    if isinstance(data, dict):
        expected, nonce = data.get('s'), data.get('n')
    else:
        expected, nonce = data, None
    try:
        if int(str(answer).strip()) != int(expected):
            return False
    except (TypeError, ValueError):
        return False
    # Correct answer — now enforce single use (replay protection).
    return _consume_math_nonce(nonce)


def honeypot_tripped():
    return bool((request.form.get('website') or '').strip())


def _client_ip():
    return request.headers.get('X-Real-IP', request.remote_addr)


def _stats_for_template():
    now = time.monotonic()
    if _stats_cache['data'] is not None and _stats_cache['expires_at'] > now:
        return _stats_cache['data']
    conn = get_db_connection()
    if not conn:
        return {'total_users': '-', 'registrations_today': '-', 'domain': XMPP_DOMAIN}
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT COUNT(*) as total FROM xmpp_users WHERE is_active = true")
        total_users = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as today FROM xmpp_users WHERE DATE(created_at) = CURRENT_DATE")
        today_regs = cursor.fetchone()['today']
        cursor.close()
        payload = {'total_users': total_users, 'registrations_today': today_regs, 'domain': XMPP_DOMAIN}
        _stats_cache['data'] = payload
        _stats_cache['expires_at'] = now + STATS_CACHE_TTL_SECONDS
        return payload
    except Exception as e:
        print(f"Stats fuer Template: {e}")
        return {'total_users': '-', 'registrations_today': '-', 'domain': XMPP_DOMAIN}
    finally:
        release_db_connection(conn)


clearnet_bp = Blueprint('clearnet', __name__, template_folder='templates')


@clearnet_bp.before_request
def _clearnet_gate():
    # Onion-Requests gehören nicht hierher
    if request.headers.get('X-Onion-Request') == '1':
        abort(404)

    # Nur GET-Requests prüfen; POST-Formulare und API-Pfade ausnehmen
    if request.method != 'GET':
        return
    if request.path.startswith('/api/'):
        return

    passed, rayid = _tdwall_ok()
    if passed:
        # Hat der Browser via URL-Token bestanden (kein Cookie)?
        # Dann nach_response Cookie setzen — best-effort für Cookie-fähige Browser.
        token_in_url = request.args.get('gate', '')
        if token_in_url and _tdwall_verify_token(token_in_url):
            signed_cookie = _tdwall_signer.dumps(rayid)

            from flask import after_this_request

            @after_this_request
            def _set_tdwall_cookie(response):
                response.set_cookie(
                    TDWALL_COOKIE_NAME,
                    signed_cookie,
                    max_age=TDWALL_COOKIE_TTL,
                    httponly=True,
                    samesite='Lax',
                    secure=True,
                )
                return response
        return  # Gate offen → weiter zum View

    # ── Gate geschlossen: Splash anzeigen ──────────────────────────────────
    ip       = _client_ip()
    ua       = request.headers.get('User-Agent', '')
    new_rayid = _tdwall_make_rayid()
    new_token = _tdwall_make_token(new_rayid)

    # Ziel-URL: altes gate= rausfiltern, neues anhängen — verhindert ?gate=alt&gate=neu
    from urllib.parse import parse_qsl, urlencode
    existing = [(k, v) for k, v in parse_qsl(request.query_string.decode('utf-8', errors='replace')) if k != 'gate']
    existing.append(('gate', new_token))
    refresh_url = f"{request.path}?{urlencode(existing)}"

    _tdwall_log(new_rayid, ip, request.path, ua, is_onion=False)

    resp = make_response(
        render_template('clearnet_tdwall.html',
                        delay=TDWALL_SPLASH_DELAY,
                        next=refresh_url,
                        rayid=new_rayid),
        200
    )
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma']        = 'no-cache'
    return resp


@clearnet_bp.route('/', methods=['GET'])
def cn_home():
    q, t = new_math_challenge()
    return render_template('clearnet_index.html',
                           math_question=q, math_token=t,
                           stats=_stats_for_template(),
                           errors=[], username='', email='')


@clearnet_bp.route('/register', methods=['POST'])
def cn_register():
    username = (request.form.get('username') or '').lower().strip()
    password = request.form.get('password') or ''
    password2 = request.form.get('password2') or ''
    email_raw = (request.form.get('email') or '').strip()
    email = email_raw or None
    privacy_ok = request.form.get('privacy') == 'on'
    math_token = request.form.get('math_token') or ''
    math_answer = request.form.get('math_answer') or ''
    ip = _client_ip()

    def _re(errors, status=400):
        q, t = new_math_challenge()
        return render_template('clearnet_index.html',
                               errors=errors, username=username, email=email_raw,
                               math_question=q, math_token=t,
                               stats=_stats_for_template()), status

    if honeypot_tripped():
        return _re(['Bot-Schutz ausgeloest.'], 400)
    if check_ip_banned(ip):
        return _re(['Zugang gesperrt'], 403)

    log_action(None, 'registration_attempt', ip, True,
               user_agent=request.headers.get('User-Agent'))

    if not verify_math(math_token, math_answer):
        return _re(['Mathe-Antwort falsch oder abgelaufen.'], 400)

    ok, msg = check_rate_limit(ip)
    if not ok:
        return _re([msg], 429)

    errors = []
    if not privacy_ok:
        errors.append('Bitte die Datenschutzerklaerung akzeptieren.')
    if password != password2:
        errors.append('Die beiden Passwoerter stimmen nicht ueberein.')
    v, m = validate_username(username)
    if not v:
        errors.append(m)
    v, m = validate_password(password)
    if not v:
        errors.append(m)
    if email:
        v, m = validate_email(email)
        if not v:
            errors.append(m)
    if errors:
        return _re(errors, 400)

    conn = get_db_connection()
    if not conn:
        return _re(['Datenbankverbindung fehlgeschlagen.'], 500)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM xmpp_users WHERE username = %s AND domain = %s",
                       (username, XMPP_DOMAIN))
        if cursor.fetchone()[0] > 0:
            cursor.close()
            return _re(['Username bereits vergeben.'], 409)
        if email:
            cursor.execute("SELECT COUNT(*) FROM xmpp_users WHERE email = %s", (email,))
            if cursor.fetchone()[0] > 0:
                cursor.close()
                log_action(None, 'register_email_collision', ip, False,
                           user_agent=request.headers.get('User-Agent'),
                           error_message=f"email_exists:{email[:60]}")
                return _re(['Registrierung nicht moeglich. Falls du bereits einen Account hast, '
                            'nutze die Passwort-Zuruecksetzung.'], 400)

        password_hash = hash_password(password)
        success, prosody_message = create_prosody_account(username, password)
        if not success:
            cursor.close()
            return _re([f'XMPP-Account konnte nicht erstellt werden: {prosody_message}'], 500)

        cursor.execute("""
            INSERT INTO xmpp_users
            (username, domain, password_hash, email, registration_ip, created_at, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (username, XMPP_DOMAIN, password_hash, email, ip, datetime.now(), True))
        user_id = cursor.fetchone()[0]
        cursor.execute("""
            INSERT INTO registration_logs
            (user_id, action, ip_address, user_agent, timestamp, success)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, 'registration', ip,
              request.headers.get('User-Agent', 'unknown')[:500], datetime.now(), True))
        conn.commit()
        cursor.close()
        return render_template('clearnet_register_success.html',
                               jid=f"{username}@{XMPP_DOMAIN}", domain=XMPP_DOMAIN), 201
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Clearnet-Registrierungsfehler: {e}")
        return _re(['Serverfehler bei der Registrierung.'], 500)
    finally:
        release_db_connection(conn)


@clearnet_bp.route('/account', methods=['GET'])
def cn_account_get():
    q, t = new_math_challenge()
    return render_template('clearnet_account.html',
                           math_question=q, math_token=t, errors=[])


@clearnet_bp.route('/account/change-password', methods=['POST'])
def cn_change_password():
    username = (request.form.get('username') or '').lower().strip()
    current_password = request.form.get('current_password') or ''
    new_password = request.form.get('new_password') or ''
    new_password2 = request.form.get('new_password2') or ''
    math_token = request.form.get('math_token') or ''
    math_answer = request.form.get('math_answer') or ''
    ip = _client_ip()

    def _re(errors, status=400):
        q, t = new_math_challenge()
        return render_template('clearnet_account.html',
                               errors=errors, math_question=q, math_token=t), status

    if honeypot_tripped():
        return _re(['Bot-Schutz ausgeloest.'], 400)
    if check_ip_banned(ip):
        return _re(['Zugang gesperrt'], 403)
    ok, msg = check_account_rate_limit(ip, 'password_change_failed', max_count=10, hours=1)
    if not ok:
        return _re([msg], 429)
    if not verify_math(math_token, math_answer):
        return _re(['Mathe-Antwort falsch oder abgelaufen.'], 400)

    user, err = verify_account_password(username, current_password)
    if not user:
        log_action(None, 'password_change_failed', ip, False,
                   user_agent=request.headers.get('User-Agent'), error_message=err)
        return _re([err], 401)

    errors = []
    if new_password != new_password2:
        errors.append('Die beiden neuen Passwoerter stimmen nicht ueberein.')
    v, vmsg = validate_password(new_password)
    if not v:
        errors.append(vmsg)
    if not errors and new_password == current_password:
        errors.append('Neues Passwort muss sich vom alten unterscheiden.')
    if errors:
        return _re(errors, 400)

    success, pmsg = prosody_change_password(username, new_password)
    if not success:
        return _re([pmsg], 500)
    new_hash = hash_password(new_password)
    conn = get_db_connection()
    if not conn:
        return _re(['Datenbankfehler'], 500)
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE xmpp_users SET password_hash = %s WHERE id = %s",
                       (new_hash, user['id']))
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"Clearnet change-pw DB-Fehler: {e}")
        return _re(['Datenbankfehler'], 500)
    finally:
        release_db_connection(conn)
    log_action(user['id'], 'password_change', ip, True,
               user_agent=request.headers.get('User-Agent'))
    return render_template('clearnet_account_changed.html', jid=f"{username}@{XMPP_DOMAIN}")


@clearnet_bp.route('/account/delete', methods=['POST'])
def cn_account_delete():
    username = (request.form.get('username') or '').lower().strip()
    password = request.form.get('password') or ''
    confirm = (request.form.get('confirm_text') or '').strip().upper()
    math_token = request.form.get('math_token') or ''
    math_answer = request.form.get('math_answer') or ''
    ip = _client_ip()

    def _re(errors, status=400):
        q, t = new_math_challenge()
        return render_template('clearnet_account.html',
                               errors=errors, math_question=q, math_token=t), status

    if honeypot_tripped():
        return _re(['Bot-Schutz ausgeloest.'], 400)
    if check_ip_banned(ip):
        return _re(['Zugang gesperrt'], 403)
    ok, msg = check_account_rate_limit(ip, 'delete_failed', max_count=10, hours=1)
    if not ok:
        return _re([msg], 429)
    if not verify_math(math_token, math_answer):
        return _re(['Mathe-Antwort falsch oder abgelaufen.'], 400)
    if confirm not in ('LOESCHEN', 'LÖSCHEN'):
        return _re(['Bitte zur Bestaetigung "LOESCHEN" eintippen.'], 400)

    user, err = verify_account_password(username, password)
    if not user:
        log_action(None, 'delete_failed', ip, False,
                   user_agent=request.headers.get('User-Agent'), error_message=err)
        return _re([err], 401)
    success, pmsg = prosody_delete_account(username)
    if not success:
        return _re([pmsg], 500)
    conn = get_db_connection()
    if not conn:
        return _re(['Datenbankfehler'], 500)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM xmpp_users WHERE id = %s", (user['id'],))
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"Clearnet delete DB-Fehler: {e}")
        return _re(['Datenbankfehler'], 500)
    finally:
        release_db_connection(conn)
    log_action(None, 'account_deleted', ip, True,
               user_agent=request.headers.get('User-Agent'),
               error_message=f"username={username}")
    return render_template('clearnet_account_deleted.html', jid=f"{username}@{XMPP_DOMAIN}")


@clearnet_bp.route('/reset', methods=['GET'])
def cn_reset_get():
    q, t = new_math_challenge()
    token = (request.args.get('token') or '').strip()
    if token and len(token) >= 32:
        return render_template('clearnet_reset.html', mode='confirm',
                               token=token, math_question=q, math_token=t, errors=[])
    return render_template('clearnet_reset.html', mode='request',
                           math_question=q, math_token=t, errors=[], token='')


@clearnet_bp.route('/reset/request', methods=['POST'])
def cn_reset_request():
    identifier = (request.form.get('identifier') or '').strip().lower()
    math_token = request.form.get('math_token') or ''
    math_answer = request.form.get('math_answer') or ''
    ip = _client_ip()

    def _re(errors, status=400):
        q, t = new_math_challenge()
        return render_template('clearnet_reset.html', mode='request',
                               math_question=q, math_token=t, errors=errors, token=''), status

    if honeypot_tripped():
        return _re(['Bot-Schutz ausgeloest.'], 400)
    if check_ip_banned(ip):
        return _re(['Zugang gesperrt'], 403)
    ok, msg = check_account_rate_limit(ip, 'reset_request', max_count=5, hours=1)
    if not ok:
        return _re([msg], 429)
    if not verify_math(math_token, math_answer):
        return _re(['Mathe-Antwort falsch oder abgelaufen.'], 400)

    generic = render_template('clearnet_reset_requested.html')
    if not identifier:
        return generic

    conn = get_db_connection()
    if not conn:
        return generic
    user = None
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT id, username, email FROM xmpp_users
            WHERE (username = %s OR email = %s) AND domain = %s AND is_active = TRUE LIMIT 1
        """, (identifier, identifier, XMPP_DOMAIN))
        user = cursor.fetchone()
        cursor.close()
        log_action(user['id'] if user else None, 'reset_request', ip,
                   bool(user and user.get('email')),
                   user_agent=request.headers.get('User-Agent'),
                   error_message=None if user else f"no_account:{identifier[:50]}")
        if not user or not user.get('email'):
            return generic
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE password_reset_tokens SET used_at = NOW()
            WHERE user_id = %s AND used_at IS NULL
        """, (user['id'],))
        token = secrets.token_urlsafe(48)
        expires = datetime.now() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
        cursor.execute("""
            INSERT INTO password_reset_tokens (user_id, token, expires_at, request_ip)
            VALUES (%s, %s, %s, %s)
        """, (user['id'], token, expires, ip))
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"Clearnet Reset-Request-Fehler: {e}")
        return generic
    finally:
        release_db_connection(conn)

    reset_url = f"{APP_BASE_URL}/reset?token={token}"
    body = (
        f"Hallo {user['username']},\n\n"
        f"fuer deinen Account {user['username']}@{XMPP_DOMAIN} wurde eine "
        f"Passwort-Zuruecksetzung angefordert.\n\n"
        f"Klicke den folgenden Link, um ein neues Passwort zu setzen "
        f"(gueltig fuer {RESET_TOKEN_TTL_MINUTES} Minuten):\n\n"
        f"{reset_url}\n\n"
        f"Falls du diese Anfrage nicht gestellt hast, kannst du diese Mail ignorieren.\n\n"
        f"-- acidbrns.cc\n"
    )
    send_email(user['email'], "Passwort zuruecksetzen - acidbrns.cc", body)
    return generic


@clearnet_bp.route('/reset/confirm', methods=['POST'])
def cn_reset_confirm():
    token = (request.form.get('token') or '').strip()
    new_password = request.form.get('new_password') or ''
    new_password2 = request.form.get('new_password2') or ''
    math_token = request.form.get('math_token') or ''
    math_answer = request.form.get('math_answer') or ''
    ip = _client_ip()

    def _re(errors, status=400):
        q, t = new_math_challenge()
        return render_template('clearnet_reset.html', mode='confirm',
                               token=token, math_question=q, math_token=t,
                               errors=errors), status

    if honeypot_tripped():
        return _re(['Bot-Schutz ausgeloest.'], 400)
    if check_ip_banned(ip):
        return _re(['Zugang gesperrt'], 403)
    ok, msg = check_account_rate_limit(ip, 'reset_confirm_failed', max_count=10, hours=1)
    if not ok:
        return _re([msg], 429)
    if not verify_math(math_token, math_answer):
        return _re(['Mathe-Antwort falsch oder abgelaufen.'], 400)

    errors = []
    if not token or len(token) < 32:
        errors.append('Ungueltiger Token.')
    if new_password != new_password2:
        errors.append('Die beiden neuen Passwoerter stimmen nicht ueberein.')
    v, vmsg = validate_password(new_password)
    if not v:
        errors.append(vmsg)
    if errors:
        return _re(errors, 400)

    conn = get_db_connection()
    if not conn:
        return _re(['Datenbankfehler'], 500)
    row = None
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT t.id AS token_id, t.expires_at, t.used_at,
                   u.id AS user_id, u.username, u.is_active
            FROM password_reset_tokens t
            JOIN xmpp_users u ON u.id = t.user_id
            WHERE t.token = %s LIMIT 1
        """, (token,))
        row = cursor.fetchone()
        if not row:
            log_action(None, 'reset_confirm_failed', ip, False,
                       user_agent=request.headers.get('User-Agent'),
                       error_message='token_not_found')
            return _re(['Ungueltiger oder abgelaufener Token.'], 400)
        if row['used_at'] is not None:
            return _re(['Token bereits verwendet.'], 400)
        if row['expires_at'] < datetime.now():
            return _re(['Token abgelaufen.'], 400)
        if not row['is_active']:
            return _re(['Account ist deaktiviert.'], 400)
        username = row['username']
        success, pmsg = prosody_change_password(username, new_password)
        if not success:
            return _re([pmsg], 500)
        new_hash = hash_password(new_password)
        cursor.close()
        cursor = conn.cursor()
        cursor.execute("UPDATE xmpp_users SET password_hash = %s WHERE id = %s",
                       (new_hash, row['user_id']))
        cursor.execute("UPDATE password_reset_tokens SET used_at = NOW() WHERE id = %s",
                       (row['token_id'],))
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"Clearnet Reset-Confirm-Fehler: {e}")
        if conn:
            conn.rollback()
        return _re(['Datenbankfehler'], 500)
    finally:
        release_db_connection(conn)
    log_action(row['user_id'], 'password_reset', ip, True,
               user_agent=request.headers.get('User-Agent'))
    return render_template('clearnet_reset_done.html',
                           jid=f"{row['username']}@{XMPP_DOMAIN}")



@clearnet_bp.route("/info", methods=["GET"])
def clearnet_info():
    ip = (request.headers.get("X-Real-IP")
          or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
          or request.remote_addr)
    interesting = [
        "User-Agent", "Accept-Language", "Accept", "Accept-Encoding",
        "DNT", "Sec-GPC", "Referer", "Via", "X-Forwarded-Proto",
    ]
    headers = {h: request.headers.get(h) for h in interesting if request.headers.get(h)}
    return render_template("clearnet_info.html", ip=ip, headers=headers)

app.register_blueprint(clearnet_bp)


if __name__ == '__main__':
    # Entwicklungs-Server
    # Für Produktion: gunicorn oder uWSGI verwenden!
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=os.getenv('FLASK_DEBUG', 'False') == 'True'
    )
