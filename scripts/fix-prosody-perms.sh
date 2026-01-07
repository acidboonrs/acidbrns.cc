#!/bin/bash
#
# Fix Prosody Account File Permissions
# This script is called by the web registration backend after creating accounts
# to ensure proper file ownership and permissions
#

PROSODY_DIR="/var/lib/prosody/acidbrns%2ecc/accounts"

if [ -d "$PROSODY_DIR" ]; then
    # Fix ownership of all .dat files in the accounts directory
    chown prosody:prosody "$PROSODY_DIR"/*.dat 2>/dev/null || true

    # Ensure proper permissions (read/write for owner and group)
    chmod 660 "$PROSODY_DIR"/*.dat 2>/dev/null || true
fi

exit 0
