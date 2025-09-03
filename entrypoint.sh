#!/bin/sh
set -e

# Always use the venv's python

echo "Running migrations..."
# python3 manage.py makemigrations --noinput
# python3 manage.py migrate --noinput

echo "Collecting static files..."
# python3 manage.py collectstatic --noinput

echo "Starting server..."
exec "$@"
