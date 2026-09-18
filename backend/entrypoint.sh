#!/bin/bash
set -euo pipefail
python /app/wait_for_db.py
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn pcep_project.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 30 \
    --graceful-timeout 30 \
    --worker-tmp-dir /tmp \
    --access-logfile - \
    --access-logformat 'request_id=%({x-request-id}i)s method=%(m)s path=%(U)s status=%(s)s duration=%(L)s' \
    --error-logfile -
