-- Prosody XMPP Server Configuration for acidbrns.cc
-- Place this file at: /etc/prosody/prosody.cfg.lua

-- Server-wide settings
admins = { }

-- Plugin paths
plugin_paths = { "/usr/lib/prosody/modules" }

-- Modules to load
modules_enabled = {
    -- Core modules
    "roster";           -- Allow users to have a roster
    "saslauth";         -- Authentication for clients
    "tls";              -- Add support for secure TLS on c2s/s2s connections
    "dialback";         -- s2s dialback support
    "disco";            -- Service discovery
    "carbons";          -- Keep multiple clients in sync
    "pep";              -- Enables users to publish their avatar, mood, activity, etc.
    "private";          -- Private XML storage (for room bookmarks, etc.)
    "blocklist";        -- Allow users to block communications with other users
    "vcard4";           -- User profiles (stored in PEP)
    "vcard_legacy";     -- Conversion between old vCard and vcard4
    "limits";           -- Enable bandwidth limiting for XMPP connections

    -- Nice to have
    "version";          -- Replies to server version requests
    "uptime";           -- Report how long server has been running
    "time";             -- Let others know the time here on this server
    "ping";             -- Replies to XMPP pings with pongs
    "register";         -- Allow users to register on this server using a client
    "mam";              -- Message Archive Management
    "csi_simple";       -- Simple Mobile optimizations

    -- Admin interfaces
    "admin_adhoc";      -- Allows administration via an XMPP client

    -- HTTP modules
    "bosh";             -- Enable BOSH clients
    "websocket";        -- Enable WebSocket support
    "http_files";       -- Serve static files from a directory

    -- Other modules
    "posix";            -- POSIX functionality
    "announce";         -- Send announcement to all online users
    "watchregistrations"; -- Alert admins of registrations
    "legacyauth";       -- Legacy authentication (XEP-0078)
}

-- Modules to disable
modules_disabled = {
    -- "offline"; -- Store messages for offline users
}

-- Allow registration
allow_registration = false  -- Disable in-band registration (use web interface instead)

-- C2S (Client-to-Server) settings
c2s_require_encryption = true
c2s_ports = { 5222 }

-- S2S (Server-to-Server) settings
s2s_require_encryption = true
s2s_secure_auth = false
s2s_ports = { 5269 }

-- Authentication
authentication = "internal_hashed"

-- Storage
storage = "internal"

-- Logging
log = {
    info = "/var/log/prosody/prosody.log";
    error = "/var/log/prosody/prosody.err";
}

-- Statistics
statistics = "internal"

-- Certificates
certificates = "certs"

-- Rate limits
limits = {
    c2s = {
        rate = "10kb/s";
    };
    s2sin = {
        rate = "30kb/s";
    };
}

-- HTTP server
http_ports = { 5280 }
http_interfaces = { "127.0.0.1", "::1" }

https_ports = { 5281 }
https_interfaces = { "127.0.0.1", "::1" }

-- HTTPS certificate
https_certificate = "/etc/prosody/certs/acidbrns.cc.crt"

-- VirtualHost
VirtualHost "acidbrns.cc"
    enabled = true

    -- SSL/TLS certificates
    ssl = {
        key = "/etc/prosody/certs/acidbrns.cc.key";
        certificate = "/etc/prosody/certs/acidbrns.cc.crt";
    }

-- Multi-User Chat (MUC)
Component "conference.acidbrns.cc" "muc"
    modules_enabled = {
        "muc_mam";          -- Message Archive Management for MUC
        "vcard_muc";        -- MUC vCards
    }
    restrict_room_creation = false
    max_history_messages = 50

-- HTTP File Upload
Component "upload.acidbrns.cc" "http_file_share"
    http_file_share_size_limit = 10485760  -- 10 MB
    http_file_share_daily_quota = 52428800  -- 50 MB per day
    http_file_share_expire_after = 60 * 60 * 24 * 7  -- 7 days
