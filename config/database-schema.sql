-- PostgreSQL Database Schema for XMPP Registration System
-- This script creates the necessary database, users, and tables

-- Create database (run as postgres user)
-- CREATE DATABASE xmpp_registration;

-- Connect to the database
\c xmpp_registration

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(32) NOT NULL UNIQUE,
    email VARCHAR(254) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    email_verified BOOLEAN DEFAULT false,
    verification_token VARCHAR(64),
    reset_token VARCHAR(64),
    reset_token_expires TIMESTAMP WITH TIME ZONE
);

-- Create index on username for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Create index on email for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Create index on created_at for sorting
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at DESC);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger to automatically update updated_at
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create audit log table (optional, for tracking registration attempts)
CREATE TABLE IF NOT EXISTS registration_log (
    id SERIAL PRIMARY KEY,
    username VARCHAR(32),
    email VARCHAR(254),
    ip_address INET,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index on registration_log for analytics
CREATE INDEX IF NOT EXISTS idx_registration_log_created_at ON registration_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_registration_log_ip ON registration_log(ip_address);

-- Grant privileges to xmpp_web user
-- Run these after creating the xmpp_web user:
-- GRANT CONNECT ON DATABASE xmpp_registration TO xmpp_web;
-- GRANT USAGE ON SCHEMA public TO xmpp_web;
-- GRANT SELECT, INSERT, UPDATE ON users TO xmpp_web;
-- GRANT SELECT, INSERT ON registration_log TO xmpp_web;
-- GRANT USAGE, SELECT ON SEQUENCE users_id_seq TO xmpp_web;
-- GRANT USAGE, SELECT ON SEQUENCE registration_log_id_seq TO xmpp_web;

-- Example: Create xmpp_web user (run as postgres user)
-- CREATE USER xmpp_web WITH PASSWORD 'your_secure_password_here';
