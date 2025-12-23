#!/bin/sh
set -e

# Always use the venv's python

echo "Running migrations..."
# python manage.py makemigrations accounts --noinput
# python manage.py migrate accounts --noinput
# python manage.py migrate accounts 0026 --fake --noinput

# python3 manage.py makemigrations --noinput
# python3 manage.py migrate --noinput
# python manage.py migrate accounts 0012 --fake
# python manage.py migrate
# python manage.py showmigrations accounts

echo "Collecting static files..."
# python3 manage.py collectstatic --noinput

echo "Starting server..."
exec "$@"
