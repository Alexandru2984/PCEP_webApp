#!/bin/bash
set -e

echo "Waiting for PostgreSQL at ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
while ! python -c "import socket; socket.create_connection(('${POSTGRES_HOST:-db}', int('${POSTGRES_PORT:-5432}')), timeout=2)" 2>/dev/null; do
    sleep 1
done
echo "PostgreSQL is up."

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn pcep_project.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --access-logfile - \
    --error-logfile -
