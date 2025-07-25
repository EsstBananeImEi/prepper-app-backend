#!/bin/bash

# Prepper App Startup Script mit Gunicorn

# Setze Umgebungsvariablen (falls nicht bereits gesetzt)
export FLASK_APP=app.py
export FLASK_ENV=production

# Prüfe ob alle kritischen Umgebungsvariablen gesetzt sind
required_vars=("JWT_SECRET_KEY" "DATABASE_URI")

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "FEHLER: Umgebungsvariable $var ist nicht gesetzt!"
        exit 1
    fi
done

echo "Starting Prepper App with Gunicorn..."
echo "Database URI: $DATABASE_URI"
echo "Worker processes: 2"

# Starte Gunicorn mit Konfigurationsdatei
exec gunicorn \
    --config gunicorn.conf.py \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --timeout 30 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    app:app
