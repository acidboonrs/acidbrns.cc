// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const API_BASE_URL = '/api';

/**
 * How long to wait (ms) after the user stops typing before sending a
 * username-availability request. 500 ms is a common UX sweet spot: short
 * enough to feel responsive, long enough to avoid a request on every keystroke
 * for fast typists.
 */
const USERNAME_DEBOUNCE_MS = 500;

/**
 * Timeout (ms) for all API fetch calls.
 * If the server doesn't respond within this window the request is aborted
 * and an error is shown to the user.
 */
const FETCH_TIMEOUT_MS = 8000;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
/** @type {number|null} Timeout ID for the debounced username availability check. */
let usernameCheckTimeout = null;

// ---------------------------------------------------------------------------
// DOM Elements
// ---------------------------------------------------------------------------
const form                = document.getElementById('registrationForm');
const usernameInput       = document.getElementById('username');
const emailInput          = document.getElementById('email');
const passwordInput       = document.getElementById('password');
const passwordConfirmInput = document.getElementById('passwordConfirm');
const submitButton        = document.getElementById('submitButton');
const alertBox            = document.getElementById('alertBox');
const usernameCheck       = document.getElementById('usernameCheck');
const passwordMatch       = document.getElementById('passwordMatch');
const passwordStrength    = document.getElementById('passwordStrength');
const successMessage      = document.getElementById('successMessage');
const jidDisplay          = document.getElementById('jidDisplay');

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

/**
 * Perform a fetch with an automatic timeout.
 *
 * Creates an AbortController internally so the caller does not need to manage
 * one. The abort signal is wired into the fetch options alongside any options
 * provided by the caller.
 *
 * @param {string} url         - Request URL.
 * @param {RequestInit} options - Standard fetch options (method, headers, body …).
 * @param {number} [timeout]   - Timeout in ms (defaults to FETCH_TIMEOUT_MS).
 * @returns {Promise<Response>}
 * @throws {DOMException} When the request is aborted due to timeout.
 */
function fetchWithTimeout(url, options = {}, timeout = FETCH_TIMEOUT_MS) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    return fetch(url, { ...options, signal: controller.signal })
        .finally(() => clearTimeout(timer));
}

/**
 * Show a dismissible alert banner above the form.
 *
 * The banner automatically hides after 5 seconds so users who fix the issue
 * quickly are not left staring at an old error.
 *
 * @param {string} message        - Human-readable message to display.
 * @param {'error'|'success'|'info'} [type='error'] - CSS modifier class.
 */
function showAlert(message, type = 'error') {
    alertBox.textContent = message;
    alertBox.className = `alert ${type}`;
    alertBox.style.display = 'block';

    setTimeout(() => {
        alertBox.style.display = 'none';
    }, 5000);
}

/** Hide the alert banner immediately. */
function hideAlert() {
    alertBox.style.display = 'none';
}

/**
 * Set the text and valid/invalid CSS class on a validation message element.
 *
 * @param {HTMLElement} element - The element to update.
 * @param {string}  message     - Text to display.
 * @param {boolean} isValid     - Whether to apply the 'valid' or 'invalid' class.
 */
function setValidationMessage(element, message, isValid) {
    element.textContent = message;
    element.className = `validation-message ${isValid ? 'valid' : 'invalid'}`;
}

/**
 * Clear text and CSS classes from a validation message element.
 *
 * @param {HTMLElement} element - The element to reset.
 */
function clearValidationMessage(element) {
    element.textContent = '';
    element.className = 'validation-message';
}

// ---------------------------------------------------------------------------
// Username validation
// ---------------------------------------------------------------------------

/**
 * Check whether a username string satisfies the local format rules.
 *
 * Rules (must match backend validate_username):
 *   - 3–32 characters
 *   - Only letters (a–z, A–Z), digits (0–9), hyphens (-), and underscores (_)
 *
 * @param {string} username - Username to check (should already be trimmed).
 * @returns {{ valid: boolean, message: string }}
 */
function validateUsernameFormat(username) {
    if (username.length < 3) {
        return { valid: false, message: 'Zu kurz (mindestens 3 Zeichen)' };
    }
    if (username.length > 32) {
        return { valid: false, message: 'Zu lang (maximal 32 Zeichen)' };
    }
    if (!/^[a-z0-9_-]+$/i.test(username)) {
        return { valid: false, message: 'Nur Buchstaben, Zahlen, - und _ erlaubt' };
    }
    return { valid: true, message: '' };
}

/**
 * Ask the backend whether a username is still available.
 *
 * Uses fetchWithTimeout so a slow/unresponsive server does not leave the UI
 * in a perpetual loading state.
 *
 * @param {string} username - Validated username to check.
 * @returns {Promise<{ available: boolean, message: string }>}
 */
async function checkUsernameAvailability(username) {
    try {
        const response = await fetchWithTimeout(`${API_BASE_URL}/check-username`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username }),
        });

        const data = await response.json();

        if (response.ok) {
            return { available: data.available, message: data.message };
        }
        return { available: false, message: data.error || 'Fehler bei der Überprüfung' };

    } catch (error) {
        if (error.name === 'AbortError') {
            console.warn('Username check timed out');
            return { available: false, message: 'Zeitüberschreitung' };
        }
        console.error('Username check error:', error);
        return { available: false, message: 'Verbindungsfehler' };
    }
}

// Input: validate format immediately, then debounce the server availability check.
usernameInput.addEventListener('input', (e) => {
    // Trim whitespace but do NOT normalise to lowercase while the user is typing –
    // modifying the value mid-input is jarring and can confuse password managers.
    // Lowercasing happens on submit.
    const username = e.target.value.trim();

    if (usernameCheckTimeout) {
        clearTimeout(usernameCheckTimeout);
    }

    if (!username) {
        clearValidationMessage(usernameCheck);
        usernameInput.classList.remove('valid', 'invalid');
        return;
    }

    const formatCheck = validateUsernameFormat(username.toLowerCase());

    if (!formatCheck.valid) {
        setValidationMessage(usernameCheck, formatCheck.message, false);
        usernameInput.classList.remove('valid');
        usernameInput.classList.add('invalid');
        return;
    }

    // Debounce the network request so we don't fire on every keystroke
    usernameCheckTimeout = setTimeout(async () => {
        const result = await checkUsernameAvailability(username.toLowerCase());

        if (result.available) {
            setValidationMessage(usernameCheck, '✓ Verfügbar', true);
            usernameInput.classList.remove('invalid');
            usernameInput.classList.add('valid');
        } else {
            setValidationMessage(usernameCheck, result.message, false);
            usernameInput.classList.remove('valid');
            usernameInput.classList.add('invalid');
        }
    }, USERNAME_DEBOUNCE_MS);
});

// ---------------------------------------------------------------------------
// Password strength
// ---------------------------------------------------------------------------

/**
 * Estimate the strength of a password on a three-level scale.
 *
 * Scoring criteria (each satisfied criterion adds 1 point):
 *   1. Length ≥ 8 characters  (meets the minimum)
 *   2. Length ≥ 12 characters (comfortably above minimum)
 *   3. Mixed case (both lower- and uppercase letters present)
 *   4. Contains at least one digit
 *   5. Contains at least one special / non-alphanumeric character
 *
 * Score → strength:
 *   0–2  → 'weak'
 *   3–4  → 'medium'
 *   5    → 'strong'
 *
 * @param {string} password - Plaintext password.
 * @returns {'weak'|'medium'|'strong'}
 */
function calculatePasswordStrength(password) {
    let score = 0;

    if (password.length >= 8)  score++;
    if (password.length >= 12) score++;
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^a-zA-Z0-9]/.test(password)) score++;

    if (score <= 2) return 'weak';
    if (score <= 4) return 'medium';
    return 'strong';
}

passwordInput.addEventListener('input', (e) => {
    const password = e.target.value;

    if (!password) {
        passwordStrength.className = 'password-strength';
        return;
    }

    const strength = calculatePasswordStrength(password);
    passwordStrength.className = `password-strength ${strength}`;

    // Keep the confirm-match indicator in sync while the primary field changes
    if (passwordConfirmInput.value) {
        checkPasswordMatch();
    }
});

// ---------------------------------------------------------------------------
// Password confirmation
// ---------------------------------------------------------------------------

/**
 * Update the password-match validation indicator based on the current values
 * of both password fields.
 */
function checkPasswordMatch() {
    const password = passwordInput.value;
    const confirm  = passwordConfirmInput.value;

    if (!confirm) {
        clearValidationMessage(passwordMatch);
        passwordConfirmInput.classList.remove('valid', 'invalid');
        return;
    }

    if (password === confirm) {
        setValidationMessage(passwordMatch, '✓ Passwörter stimmen überein', true);
        passwordConfirmInput.classList.remove('invalid');
        passwordConfirmInput.classList.add('valid');
    } else {
        setValidationMessage(passwordMatch, '✗ Passwörter stimmen nicht überein', false);
        passwordConfirmInput.classList.remove('valid');
        passwordConfirmInput.classList.add('invalid');
    }
}

passwordConfirmInput.addEventListener('input', checkPasswordMatch);

// ---------------------------------------------------------------------------
// Email validation
// ---------------------------------------------------------------------------

/**
 * Validate an email address against a pragmatic regex.
 *
 * This regex matches the vast majority of real-world email addresses and
 * mirrors the server-side EMAIL_PATTERN. Full RFC 5322 validation is
 * deliberately omitted because it rejects common valid addresses.
 *
 * @param {string} email - Email address to check.
 * @returns {boolean}
 */
function isValidEmail(email) {
    return /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/.test(email);
}

emailInput.addEventListener('blur', (e) => {
    const email = e.target.value.trim();

    if (!email) return;

    if (isValidEmail(email)) {
        emailInput.classList.remove('invalid');
        emailInput.classList.add('valid');
    } else {
        emailInput.classList.remove('valid');
        emailInput.classList.add('invalid');
    }
});

// ---------------------------------------------------------------------------
// Form submission
// ---------------------------------------------------------------------------

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    hideAlert();

    // Normalise values on submit (lowercase username and email)
    const username        = usernameInput.value.trim().toLowerCase();
    const email           = emailInput.value.trim().toLowerCase();
    const password        = passwordInput.value;
    const passwordConfirm = passwordConfirmInput.value;

    // Client-side validation (mirrors server-side checks for fast feedback)
    if (!username || !email || !password || !passwordConfirm) {
        showAlert('Bitte fülle alle Felder aus', 'error');
        return;
    }

    const formatCheck = validateUsernameFormat(username);
    if (!formatCheck.valid) {
        showAlert(`Ungültiger Benutzername: ${formatCheck.message}`, 'error');
        return;
    }

    if (!isValidEmail(email)) {
        showAlert('Ungültige E-Mail-Adresse', 'error');
        return;
    }

    if (password !== passwordConfirm) {
        showAlert('Passwörter stimmen nicht überein', 'error');
        return;
    }

    if (password.length < 8) {
        showAlert('Passwort muss mindestens 8 Zeichen lang sein', 'error');
        return;
    }

    if (!/[a-zA-Z]/.test(password) || !/[0-9]/.test(password)) {
        showAlert('Passwort muss Buchstaben und Zahlen enthalten', 'error');
        return;
    }

    // Disable form while the request is in-flight
    submitButton.disabled = true;
    submitButton.textContent = 'Account wird erstellt…';

    try {
        const response = await fetchWithTimeout(`${API_BASE_URL}/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, email, password }),
        });

        const data = await response.json();

        if (response.ok) {
            form.style.display = 'none';
            successMessage.style.display = 'block';
            jidDisplay.textContent = data.jid;
            window.scrollTo({ top: 0, behavior: 'smooth' });
        } else {
            showAlert(data.error || 'Registrierung fehlgeschlagen', 'error');
            submitButton.disabled = false;
            submitButton.textContent = 'Account erstellen';
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            showAlert('Zeitüberschreitung. Bitte versuche es erneut.', 'error');
        } else {
            console.error('Registration error:', error);
            showAlert('Verbindungsfehler. Bitte versuche es später erneut.', 'error');
        }
        submitButton.disabled = false;
        submitButton.textContent = 'Account erstellen';
    }
});

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    // Check that the backend is reachable. If not, disable the submit button
    // and show a persistent warning so users don't waste time filling out
    // a form that cannot be submitted.
    fetchWithTimeout(`${API_BASE_URL}/health`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'healthy') {
                console.log('Backend API is healthy');
            } else {
                console.warn('Backend API health check failed:', data);
                submitButton.disabled = true;
                showAlert(
                    'Der Registrierungsservice ist momentan nicht verfügbar. Bitte versuche es später erneut.',
                    'error'
                );
            }
        })
        .catch(error => {
            console.error('Backend API is not reachable:', error);
            submitButton.disabled = true;
            showAlert(
                'Backend-Verbindung nicht erreichbar. Bitte versuche es später erneut.',
                'error'
            );
        });
});
