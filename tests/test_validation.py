"""Unit tests for the pure validation / bot-protection helpers.

These run without a database: the single-use nonce check fails open when no DB
is reachable, so the math-captcha round-trip is verifiable in CI.
"""
import app


# --- username -------------------------------------------------------------

def test_username_valid():
    ok, _ = app.validate_username("alice_99")
    assert ok


def test_username_too_short():
    ok, _ = app.validate_username("ab")
    assert not ok


def test_username_too_long():
    ok, _ = app.validate_username("a" * 33)
    assert not ok


def test_username_invalid_chars():
    for bad in ["Alice", "al ice", "alice!", "ali.ce", "über"]:
        ok, _ = app.validate_username(bad)
        assert not ok, bad


def test_username_reserved():
    for reserved in ["admin", "root", "prosody", "security"]:
        ok, _ = app.validate_username(reserved)
        assert not ok, reserved


# --- password -------------------------------------------------------------

def test_password_strong():
    ok, _ = app.validate_password("Sup3r!Secret42")
    assert ok


def test_password_rules():
    for weak in [
        "short1!A",          # too short
        "alllowercase1!",    # no uppercase
        "ALLUPPERCASE1!",    # no lowercase
        "NoDigitsHere!!",    # no digit
        "NoSpecialChar12",   # no special char
    ]:
        ok, _ = app.validate_password(weak)
        assert not ok, weak


def test_password_too_long():
    ok, _ = app.validate_password("A1!" + "a" * 130)
    assert not ok


# --- email ----------------------------------------------------------------

def test_email_optional_empty_is_ok():
    ok, _ = app.validate_email("")
    assert ok


def test_email_valid():
    ok, _ = app.validate_email("user@example.org")
    assert ok


def test_email_invalid():
    for bad in ["not-an-email", "a@b", "@example.org", "user@", "a@b@c.de"]:
        ok, _ = app.validate_email(bad)
        assert not ok, bad


# --- math captcha ---------------------------------------------------------

def test_math_roundtrip_correct_answer():
    question, token = app.new_math_challenge()
    a, b = (int(x) for x in question.replace(" ", "").split("+"))
    assert app.verify_math(token, a + b) is True


def test_math_wrong_answer():
    question, token = app.new_math_challenge()
    a, b = (int(x) for x in question.replace(" ", "").split("+"))
    assert app.verify_math(token, a + b + 1) is False


def test_math_rejects_empty_and_tampered():
    _, token = app.new_math_challenge()
    assert app.verify_math("", 5) is False
    assert app.verify_math(token + "x", 5) is False
    assert app.verify_math(token, "") is False
