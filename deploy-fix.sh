#!/bin/bash
# Fix: Deployed app.py mit korrigierter Version ersetzen und gunicorn neustarten
set -e

echo "Kopiere korrigierte app.py..."
sudo cp /home/acid/xmpp-acidbrns/backend/app.py /var/www/xmpp-registration/backend/app.py
sudo chown www-data:www-data /var/www/xmpp-registration/backend/app.py

echo "Starte gunicorn neu..."
sudo systemctl restart xmpp-backend

echo "Warte 2 Sekunden..."
sleep 2

echo "Teste API..."
curl -s http://127.0.0.1:5000/api/status
echo ""
echo ""
echo "Done!"
