#!/bin/sh
set -e

# Fail early and clearly if someone changed a model without committing its migration.
python manage.py makemigrations --check --dry-run || {
  echo "ERROR: models changed but migrations are missing. Run deploy/makemigrations.sh and commit the new files." >&2
  exit 1
}

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --access-logfile - \
  --error-logfile -
