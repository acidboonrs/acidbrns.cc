-- PostgreSQL Database Schema for XMPP Registration System
-- This script creates the necessary database, users, and tables.
--
-- Run as the postgres superuser:
--   sudo -u postgres psql -f database-schema.sql

-- Create database (run as postgres user before executing the rest)
-- CREATE DATABASE xmpp_registration;

-- Connect to the database
\c xmpp_registration

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
-- Core user table. Every XMPP account registered through the web interface
-- has exactly one corresponding row here.
--
-- Column notes:
--   password_hash   - bcrypt hash; plaintext is never stored
--   updated_at      - automatically maintained by the update_users_updated_at trigger
--
-- Planned (not yet implemented) columns:
--   last_login      - will be updated by the XMPP session handler when SSO/auth
--                     integration is added
--   is_active       - reserved for account suspension/ban functionality
--   email_verified  - set to true after the user clicks the email verification link
--                     (verification flow not yet implemented)
--   verification_token - single-use token sent in the verification email;
--                        expires after 24 h (enforced in application logic)
--   reset_token        - single-use token for password resets; expires at
--                        reset_token_expires (password reset flow not yet implemented)
--   reset_token_expires - expiry timestamp for reset_token
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL PRIMARY KEY,
    username             VARCHAR(32)  NOT NULL UNIQUE,
    email                VARCHAR(254) NOT NULL UNIQUE,
    password_hash        VARCHAR(255) NOT NULL,
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Planned: updated when the user authenticates via XMPP
    last_login           TIMESTAMP WITH TIME ZONE,

    -- Planned: used to suspend or ban accounts
    is_active            BOOLEAN DEFAULT true,

    -- Planned: email verification flow
    email_verified       BOOLEAN DEFAULT false,
    verification_token   VARCHAR(64),

    -- Planned: password reset flow
    reset_token          VARCHAR(64),
    reset_token_expires  TIMESTAMP WITH TIME ZONE
);

-- Index on username for O(log n) availability checks and login lookups
CREATE INDEX IF NOT EXISTS idx_users_username   ON users(username);

-- Index on email for duplicate-check queries
CREATE INDEX IF NOT EXISTS idx_users_email      ON users(email);

-- Index on created_at for admin/analytics queries sorted by registration date
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at DESC);

-- ---------------------------------------------------------------------------
-- Trigger: keep updated_at current on every UPDATE
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ---------------------------------------------------------------------------
-- registration_log
-- ---------------------------------------------------------------------------
-- Audit log for every registration attempt, successful or not.
-- Written by log_registration_attempt() in app.py on every call to
-- POST /api/register.
--
-- Purposes:
--   - Abuse detection: repeated failures from the same IP indicate brute-force
--     or enumeration attempts
--   - Debugging: failed registrations include an error_message explaining
--     which step (validation, Prosody, database) failed
--   - Analytics: successful registrations show growth over time
--
-- The username and email columns are nullable so that attempts that fail
-- before input parsing can still be logged with only an ip_address.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS registration_log (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(32),
    email         VARCHAR(254),
    ip_address    INET,
    success       BOOLEAN NOT NULL,
    error_message TEXT,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for time-based analytics and log rotation queries
CREATE INDEX IF NOT EXISTS idx_registration_log_created_at
    ON registration_log(created_at DESC);

-- Index for IP-based abuse queries (e.g. "show all attempts from 1.2.3.4")
CREATE INDEX IF NOT EXISTS idx_registration_log_ip
    ON registration_log(ip_address);

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
-- Run these statements after the xmpp_web role has been created.
-- The xmpp_web user needs SELECT+INSERT on users (no UPDATE/DELETE from the
-- web process) and SELECT+INSERT on registration_log.
--
-- GRANT CONNECT ON DATABASE xmpp_registration TO xmpp_web;
-- GRANT USAGE ON SCHEMA public TO xmpp_web;
-- GRANT SELECT, INSERT ON users TO xmpp_web;
-- GRANT SELECT, INSERT ON registration_log TO xmpp_web;
-- GRANT USAGE, SELECT ON SEQUENCE users_id_seq TO xmpp_web;
-- GRANT USAGE, SELECT ON SEQUENCE registration_log_id_seq TO xmpp_web;
--
-- Example: create the role (run as postgres superuser)
-- CREATE USER xmpp_web WITH PASSWORD 'your_secure_password_here';
