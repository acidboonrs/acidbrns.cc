#!/usr/bin/env python3
"""
XMPP Account Registration Backend
===================================
Flask REST API for creating XMPP accounts via the acidbrns.cc web interface.

Endpoints:
  GET  /api/health          - Liveness check (DB + Prosody)
  POST /api/register        - Register a new XMPP account
  POST /api/check-username  - Check if a username is available

Registration flow:
  1. Validate all input fields (username, email, password).
  2. Create Prosody account via prosodyctl.
  3. Insert user record into PostgreSQL.
  4. On DB failure: best-effort rollback of the Prosody account.
  5. Log every attempt in registration_log for abuse monitoring.
"""

import os
import re
import subprocess
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2 import OperationalError, InterfaceError
import bcrypt
from dotenv import load_dotenv

# Load environment variables from .env (no-op if running with system env)
load_dotenv()

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'xmpp_registration')
DB_USER = os.getenv('DB_USER', 'xmpp_web')
DB_PASSWORD = os.getenv('DB_PASSWORD')
XMPP_DOMAIN = os.getenv('XMPP_DOMAIN', 'acidbrns.cc')
PROSODY_PATH = os.getenv('PROSODY_PATH', '/usr/bin/prosodyctl')
FIX_PERMS_SCRIPT = os.getenv('FIX_PERMS_SCRIPT', '/usr/local/bin/fix-prosody-perms.sh')

# Fail fast: do not start if the database password is missing
if DB_PASSWORD is None:
    raise RuntimeError(
        "DB_PASSWORD environment variable is not set. "
        "Configure it in .env or the system environment before starting."
    )

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------
# Username rules follow XMPP localpart restrictions (RFC 6122 §2.3)
USERNAME_MIN_LEN = 3
USERNAME_MAX_LEN = 32
USERNAME_PATTERN = re.compile(r'^[a-z0-9_-]+$', re.IGNORECASE)

# Password rules follow NIST SP 800-63B guidance:
#   - minimum 8 characters prevents trivially weak passwords
#   - maximum 128 characters prevents bcrypt DoS; bcrypt silently truncates
#     inputs beyond 72 bytes, so we reject anything longer than 128 chars
#     to avoid silent truncation of very long passwords
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 128

# RFC 5321 §4.5.3.1.3 limits the total email address length to 254 characters.
# The regex is intentionally pragmatic rather than a full RFC 5322 implementation,
# which would cause false negatives on common valid addresses.
EMAIL_MAX_LEN = 254
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

# Prosody subprocess timeouts in seconds
PROSODY_CMD_TIMEOUT = 10   # adduser / deluser
PROSODY_PERMS_TIMEOUT = 5  # fix-prosody-perms.sh


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db_connection():
    """
    Open and return a new PostgreSQL connection.

    Uses a 5-second connect_timeout to avoid hanging indefinitely when the
    database is unreachable.

    Raises:
        psycopg2.OperationalError: if the database is unreachable or
            credentials are wrong.
    """
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=5,
        )
        return conn
    except OperationalError as e:
        app.logger.error(f"Database connection error: {e}")
        raise


def log_registration_attempt(username, email, ip_address, success, error_message=None):
    """
    Append a row to registration_log for audit and abuse monitoring.

    This function is best-effort: any failure is logged as a warning and
    does not affect the HTTP response returned to the client.

    Args:
        username (str):           Requested username (may be empty on early
                                  validation failure).
        email (str):              Requested email (may be empty on early
                                  validation failure).
        ip_address (str):         Client IP from request.remote_addr.
        success (bool):           Whether registration succeeded.
        error_message (str|None): Short description of the failure, if any.
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO registration_log
                    (username, email, ip_address, success, error_message)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (username or None, email or None, ip_address, success, error_message),
            )
            conn.commit()
            cursor.close()
        finally:
            conn.close()
    except Exception as e:
        app.logger.warning(f"Could not write registration_log: {e}")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def validate_username(username):
    """
    Validate a username against XMPP localpart rules.

    Rules:
      - Length between USERNAME_MIN_LEN (3) and USERNAME_MAX_LEN (32)
      - Only letters, digits, hyphens (-), and underscores (_)

    Args:
        username (str): Username to validate (should already be stripped and
                        lowercased by the caller).

    Returns:
        tuple[bool, str|None]: (is_valid, error_message). error_message is
            None when is_valid is True.
    """
    if len(username) < USERNAME_MIN_LEN or len(username) > USERNAME_MAX_LEN:
        return False, (
            f"Benutzername muss {USERNAME_MIN_LEN}–{USERNAME_MAX_LEN} Zeichen lang sein"
        )
    if not USERNAME_PATTERN.match(username):
        return False, "Benutzername darf nur Buchstaben, Zahlen, - und _ enthalten"
    return True, None


def validate_password(password):
    """
    Validate password strength.

    Rules (NIST SP 800-63B):
      - At least PASSWORD_MIN_LEN (8) characters.
      - At most PASSWORD_MAX_LEN (128) characters – bcrypt truncates silently
        at 72 bytes, so we enforce an upper bound to prevent unexpected
        truncation and to mitigate bcrypt DoS with extremely long inputs.
      - Must contain at least one letter and one digit.

    Args:
        password (str): Raw plaintext password.

    Returns:
        tuple[bool, str|None]: (is_valid, error_message).
    """
    if len(password) < PASSWORD_MIN_LEN:
        return False, f"Passwort muss mindestens {PASSWORD_MIN_LEN} Zeichen lang sein"
    if len(password) > PASSWORD_MAX_LEN:
        return False, f"Passwort darf maximal {PASSWORD_MAX_LEN} Zeichen lang sein"
    if not re.search(r'[a-zA-Z]', password) or not re.search(r'[0-9]', password):
        return False, "Passwort muss mindestens einen Buchstaben und eine Zahl enthalten"
    return True, None


def validate_email(email):
    """
    Validate an email address format.

    Uses a pragmatic regex covering the vast majority of real-world addresses.
    Exact RFC 5322 compliance is intentionally omitted because it rejects
    many common valid addresses.

    Args:
        email (str): Email address to validate (should already be stripped and
                     lowercased by the caller).

    Returns:
        tuple[bool, str|None]: (is_valid, error_message).
    """
    if len(email) > EMAIL_MAX_LEN:
        return False, "E-Mail-Adresse zu lang"
    if not EMAIL_PATTERN.match(email):
        return False, "Ungültige E-Mail-Adresse"
    return True, None


# ---------------------------------------------------------------------------
# Prosody integration
# ---------------------------------------------------------------------------
def create_prosody_account(username, password):
    """
    Create a new user account in the Prosody XMPP server via prosodyctl.

    prosodyctl reads the password from stdin in the format::

        <password>\\n<password>\\n

    (entered twice for confirmation, same as the interactive adduser command).

    After a successful creation, fix-prosody-perms.sh is invoked with sudo to
    correct file-system ownership of the new account data directory. A failure
    of that helper is non-fatal and is logged as a warning.

    Args:
        username (str): XMPP localpart (without domain).
        password (str): Plaintext password.

    Returns:
        tuple[bool, str]: (success, message).
    """
    try:
        jid = f"{username}@{XMPP_DOMAIN}"

        process = subprocess.Popen(
            [PROSODY_PATH, 'adduser', jid],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send the password twice (new + confirmation prompt)
        stdout, stderr = process.communicate(
            input=f"{password}\n{password}\n",
            timeout=PROSODY_CMD_TIMEOUT,
        )

        if process.returncode != 0:
            error_msg = stderr.strip() or "Unbekannter Fehler"
            app.logger.error(f"prosodyctl adduser failed for {jid}: {error_msg}")
            return False, f"Prosody Fehler: {error_msg}"

        # Prosody stores account data as files owned by the prosody system user.
        # The web process runs under a different user, so permissions must be
        # corrected after every account creation.
        try:
            subprocess.run(
                ['sudo', FIX_PERMS_SCRIPT],
                timeout=PROSODY_PERMS_TIMEOUT,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            app.logger.warning(f"fix-prosody-perms.sh exited with {e.returncode}")
        except subprocess.TimeoutExpired:
            app.logger.warning("fix-prosody-perms.sh timed out")
        except OSError as e:
            app.logger.warning(f"Could not run fix-prosody-perms.sh: {e}")

        return True, "Account erfolgreich erstellt"

    except subprocess.TimeoutExpired:
        app.logger.error(f"prosodyctl adduser timed out for {username}")
        return False, "Timeout bei Account-Erstellung"
    except OSError as e:
        app.logger.error(f"Could not execute prosodyctl: {e}")
        return False, f"Fehler bei Account-Erstellung: {e}"


def delete_prosody_account(username):
    """
    Delete a user account from Prosody (rollback on DB failure).

    Called when the database insert fails after a successful Prosody account
    creation, to avoid leaving an orphaned XMPP account. If this rollback
    also fails the incident is logged for manual cleanup.

    Args:
        username (str): XMPP localpart (without domain).

    Returns:
        tuple[bool, str]: (success, message).
    """
    try:
        jid = f"{username}@{XMPP_DOMAIN}"

        result = subprocess.run(
            [PROSODY_PATH, 'deluser', jid],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=PROSODY_CMD_TIMEOUT,
        )

        if result.returncode == 0:
            app.logger.info(f"Prosody rollback succeeded for {jid}")
            return True, "Account gelöscht"

        error_msg = result.stderr.strip() or "Unbekannter Fehler"
        app.logger.error(f"prosodyctl deluser failed for {jid}: {error_msg}")
        return False, f"Prosody Löschfehler: {error_msg}"

    except subprocess.TimeoutExpired:
        app.logger.error(f"prosodyctl deluser timed out for {username}")
        return False, "Timeout bei Account-Löschung"
    except OSError as e:
        app.logger.error(f"Could not execute prosodyctl for rollback: {e}")
        return False, f"Fehler bei Account-Löschung: {e}"


# ---------------------------------------------------------------------------
# Database account management
# ---------------------------------------------------------------------------
def create_database_account(username, email, password):
    """
    Insert a new user record into PostgreSQL.

    The password is hashed with bcrypt before storage; the plaintext value is
    never persisted. bcrypt's work factor is determined by bcrypt.gensalt()
    defaults (currently 12 rounds).

    Args:
        username (str): Validated, lowercased username.
        email (str):    Validated, lowercased email address.
        password (str): Plaintext password (hashed internally before insert).

    Returns:
        tuple[bool, int|str]: (True, user_id) on success,
                              (False, error_message) on failure.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # bcrypt is intentionally slow to resist brute-force attacks.
        # The resulting hash string is stored in password_hash (VARCHAR 255).
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, created_at)
            VALUES (%s, %s, %s, NOW())
            RETURNING id
            """,
            (username, email, password_hash.decode('utf-8')),
        )

        user_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        return True, user_id

    except psycopg2.IntegrityError as e:
        if conn:
            conn.rollback()
        err = str(e)
        app.logger.error(f"DB integrity error for {username}: {err}")
        if 'username' in err:
            return False, "Benutzername bereits vergeben"
        if 'email' in err:
            return False, "E-Mail-Adresse bereits registriert"
        return False, "Benutzer existiert bereits"

    except (OperationalError, InterfaceError) as e:
        app.logger.error(f"DB connection error: {e}")
        return False, "Datenbankfehler: Verbindung nicht möglich"

    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Liveness and readiness endpoint.

    Checks:
      - PostgreSQL connectivity (attempts a real connection)
      - prosodyctl availability (runs ``prosodyctl about``)

    Returns:
        200 JSON  { status: 'healthy', database: str, prosody: str }
        503 JSON  { status: 'unhealthy', error: str }
    """
    try:
        conn = get_db_connection()
        conn.close()

        result = subprocess.run(
            [PROSODY_PATH, 'about'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        prosody_ok = result.returncode == 0

        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'prosody': 'available' if prosody_ok else 'unavailable',
        }), 200

    except OperationalError as e:
        return jsonify({'status': 'unhealthy', 'error': f'Database: {e}'}), 503
    except Exception as e:
        app.logger.error(f"Health check error: {e}")
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 503


@app.route('/api/register', methods=['POST'])
def register():
    """
    Register a new XMPP account.

    Expects JSON body::

        { "username": str, "email": str, "password": str }

    Flow:
      1. Parse and validate all fields.
      2. Create Prosody account via prosodyctl.
      3. Insert DB record.
      4. On DB failure: attempt Prosody rollback, then return 500.
      5. Log outcome in registration_log regardless of success or failure.

    Returns:
        201 JSON  { success: true, message: str, jid: str }
        400 JSON  { error: str }   on validation failure
        500 JSON  { error: str }   on server-side failure
    """
    ip_address = request.remote_addr
    username = ''
    email = ''

    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'error': 'Keine oder ungültige JSON-Daten empfangen'}), 400

        username = data.get('username', '').strip().lower()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        if not username or not email or not password:
            return jsonify({'error': 'Alle Felder sind erforderlich'}), 400

        valid, error = validate_username(username)
        if not valid:
            return jsonify({'error': error}), 400

        valid, error = validate_email(email)
        if not valid:
            return jsonify({'error': error}), 400

        valid, error = validate_password(password)
        if not valid:
            return jsonify({'error': error}), 400

        # --- Create Prosody account ---
        success, message = create_prosody_account(username, password)
        if not success:
            app.logger.error(f"Prosody creation failed for {username}: {message}")
            log_registration_attempt(username, email, ip_address, False, f"Prosody: {message}")
            return jsonify({'error': f'XMPP-Account konnte nicht erstellt werden: {message}'}), 500

        # --- Create database record ---
        success, result = create_database_account(username, email, password)
        if not success:
            app.logger.error(f"DB insert failed for {username}: {result}")
            # Best-effort rollback – if this also fails, the incident is logged
            # and must be resolved manually
            rb_ok, rb_msg = delete_prosody_account(username)
            if not rb_ok:
                app.logger.error(
                    f"Prosody rollback failed for {username}: {rb_msg} – manual cleanup required"
                )
            log_registration_attempt(username, email, ip_address, False, f"DB: {result}")
            return jsonify({'error': f'Datenbank-Eintrag konnte nicht erstellt werden: {result}'}), 500

        jid = f"{username}@{XMPP_DOMAIN}"
        app.logger.info(f"Account registered: {jid} from {ip_address}")
        log_registration_attempt(username, email, ip_address, True)

        return jsonify({
            'success': True,
            'message': 'Account erfolgreich erstellt',
            'jid': jid,
        }), 201

    except Exception as e:
        app.logger.error(f"Unexpected registration error for '{username}': {e}")
        log_registration_attempt(username, email, ip_address, False, f"Unexpected: {e}")
        return jsonify({'error': 'Interner Serverfehler'}), 500


@app.route('/api/check-username', methods=['POST'])
def check_username():
    """
    Check whether a username is still available.

    Expects JSON body::

        { "username": str }

    Note: There is an inherent race condition between this check and a
    subsequent /api/register call. The database UNIQUE constraint on
    ``username`` is the authoritative guard against duplicates; this endpoint
    is only for UX pre-validation feedback.

    Returns:
        200 JSON  { available: bool, message: str }
        400 JSON  { error: str }   on missing/invalid input
        500 JSON  { error: str }   on server error
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'available': False, 'error': 'Ungültige Anfrage'}), 400

        username = data.get('username', '').strip().lower()

        if not username:
            return jsonify({'available': False, 'error': 'Kein Benutzername angegeben'}), 400

        valid, error = validate_username(username)
        if not valid:
            return jsonify({'available': False, 'error': error}), 400

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # Use SELECT 1 ... LIMIT 1 instead of COUNT(*) to short-circuit on first match
            cursor.execute("SELECT 1 FROM users WHERE username = %s LIMIT 1", (username,))
            exists = cursor.fetchone() is not None
            cursor.close()
        finally:
            conn.close()

        return jsonify({
            'available': not exists,
            'message': (
                'Benutzername verfügbar' if not exists else 'Benutzername bereits vergeben'
            ),
        }), 200

    except OperationalError as e:
        app.logger.error(f"DB error in check_username: {e}")
        return jsonify({'error': 'Datenbankfehler'}), 500
    except Exception as e:
        app.logger.error(f"Username check error: {e}")
        return jsonify({'error': 'Fehler bei der Überprüfung'}), 500


if __name__ == '__main__':
    # This block is only reached when running directly with `python app.py`.
    # In production the application is served by gunicorn (see xmpp-backend.service).
    app.run(host='127.0.0.1', port=5000, debug=False)
