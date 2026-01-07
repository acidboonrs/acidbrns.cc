// Configuration
const API_BASE_URL = '/api';
const USERNAME_DEBOUNCE_MS = 500;

// State
let usernameCheckTimeout = null;

// DOM Elements
const form = document.getElementById('registrationForm');
const usernameInput = document.getElementById('username');
const emailInput = document.getElementById('email');
const passwordInput = document.getElementById('password');
const passwordConfirmInput = document.getElementById('passwordConfirm');
const submitButton = document.getElementById('submitButton');
const alertBox = document.getElementById('alertBox');
const usernameCheck = document.getElementById('usernameCheck');
const passwordMatch = document.getElementById('passwordMatch');
const passwordStrength = document.getElementById('passwordStrength');
const successMessage = document.getElementById('successMessage');
const jidDisplay = document.getElementById('jidDisplay');

// Utility Functions
function showAlert(message, type = 'error') {
    alertBox.textContent = message;
    alertBox.className = `alert ${type}`;
    alertBox.style.display = 'block';

    // Auto-hide after 5 seconds
    setTimeout(() => {
        alertBox.style.display = 'none';
    }, 5000);
}

function hideAlert() {
    alertBox.style.display = 'none';
}

function setValidationMessage(element, message, isValid) {
    element.textContent = message;
    element.className = `validation-message ${isValid ? 'valid' : 'invalid'}`;
}

function clearValidationMessage(element) {
    element.textContent = '';
    element.className = 'validation-message';
}

// Username Validation
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

async function checkUsernameAvailability(username) {
    try {
        const response = await fetch(`${API_BASE_URL}/check-username`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username }),
        });

        const data = await response.json();

        if (response.ok) {
            return {
                available: data.available,
                message: data.message
            };
        } else {
            return {
                available: false,
                message: data.error || 'Fehler bei der Überprüfung'
            };
        }
    } catch (error) {
        console.error('Username check error:', error);
        return {
            available: false,
            message: 'Verbindungsfehler'
        };
    }
}

usernameInput.addEventListener('input', (e) => {
    const username = e.target.value.trim().toLowerCase();

    // Update input value to lowercase
    e.target.value = username;

    // Clear previous timeout
    if (usernameCheckTimeout) {
        clearTimeout(usernameCheckTimeout);
    }

    // Validate format first
    const formatCheck = validateUsernameFormat(username);

    if (!username) {
        clearValidationMessage(usernameCheck);
        usernameInput.classList.remove('valid', 'invalid');
        return;
    }

    if (!formatCheck.valid) {
        setValidationMessage(usernameCheck, formatCheck.message, false);
        usernameInput.classList.remove('valid');
        usernameInput.classList.add('invalid');
        return;
    }

    // Check availability with debounce
    usernameCheckTimeout = setTimeout(async () => {
        const result = await checkUsernameAvailability(username);

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

// Password Strength
function calculatePasswordStrength(password) {
    let strength = 0;

    if (password.length >= 8) strength++;
    if (password.length >= 12) strength++;
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength++;
    if (/[0-9]/.test(password)) strength++;
    if (/[^a-zA-Z0-9]/.test(password)) strength++;

    if (strength <= 2) return 'weak';
    if (strength <= 4) return 'medium';
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

    // Check if passwords match (if confirm field has content)
    if (passwordConfirmInput.value) {
        checkPasswordMatch();
    }
});

// Password Match Validation
function checkPasswordMatch() {
    const password = passwordInput.value;
    const confirm = passwordConfirmInput.value;

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

// Email Validation
emailInput.addEventListener('blur', (e) => {
    const email = e.target.value.trim();

    if (!email) return;

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (emailRegex.test(email)) {
        emailInput.classList.remove('invalid');
        emailInput.classList.add('valid');
    } else {
        emailInput.classList.remove('valid');
        emailInput.classList.add('invalid');
    }
});

// Form Submission
form.addEventListener('submit', async (e) => {
    e.preventDefault();

    hideAlert();

    // Get form values
    const username = usernameInput.value.trim().toLowerCase();
    const email = emailInput.value.trim().toLowerCase();
    const password = passwordInput.value;
    const passwordConfirm = passwordConfirmInput.value;

    // Validate all fields
    if (!username || !email || !password || !passwordConfirm) {
        showAlert('Bitte fülle alle Felder aus', 'error');
        return;
    }

    // Check username format
    const formatCheck = validateUsernameFormat(username);
    if (!formatCheck.valid) {
        showAlert(`Ungültiger Benutzername: ${formatCheck.message}`, 'error');
        return;
    }

    // Check password match
    if (password !== passwordConfirm) {
        showAlert('Passwörter stimmen nicht überein', 'error');
        return;
    }

    // Check password strength
    if (password.length < 8) {
        showAlert('Passwort muss mindestens 8 Zeichen lang sein', 'error');
        return;
    }

    if (!/[a-zA-Z]/.test(password) || !/[0-9]/.test(password)) {
        showAlert('Passwort muss Buchstaben und Zahlen enthalten', 'error');
        return;
    }

    // Disable form during submission
    submitButton.disabled = true;
    submitButton.textContent = 'Account wird erstellt...';

    try {
        const response = await fetch(`${API_BASE_URL}/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                username,
                email,
                password
            }),
        });

        const data = await response.json();

        if (response.ok) {
            // Show success message
            form.style.display = 'none';
            successMessage.style.display = 'block';
            jidDisplay.textContent = data.jid;

            // Scroll to top
            window.scrollTo({ top: 0, behavior: 'smooth' });
        } else {
            showAlert(data.error || 'Registrierung fehlgeschlagen', 'error');
            submitButton.disabled = false;
            submitButton.textContent = 'Account erstellen';
        }
    } catch (error) {
        console.error('Registration error:', error);
        showAlert('Verbindungsfehler. Bitte versuche es später erneut.', 'error');
        submitButton.disabled = false;
        submitButton.textContent = 'Account erstellen';
    }
});

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('XMPP Registration Form loaded');

    // Check API health
    fetch(`${API_BASE_URL}/health`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'healthy') {
                console.log('Backend API is healthy');
            } else {
                console.warn('Backend API health check failed:', data);
            }
        })
        .catch(error => {
            console.error('Backend API is not reachable:', error);
            showAlert('Backend-Verbindung nicht erreichbar. Bitte versuche es später erneut.', 'error');
        });
});
