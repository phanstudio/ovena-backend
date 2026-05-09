#!/bin/sh
set -e

# Apply migrations
python manage.py migrate --noinput

# Collect static files
python manage.py collectstatic --noinput

# Run passed command (e.g., runserver or gunicorn)
echo "Starting server..."
exec python manage.py runserver 0.0.0.0:8000
