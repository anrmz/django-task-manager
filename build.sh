#!/usr/bin/env bash
# Production build script for the Django Task Manager.
#
# Designed to run on hosted platforms (Render "Build Command": ./build.sh)
# and locally. Every command is strict: if any step fails the build fails —
# nothing is silently swallowed.
#
# NOTE: `migrate` requires the database to be reachable during the build. On
# Render this works because attached databases are provisioned before the
# service builds. If your platform cannot reach the DB at build time, move the
# migrate line into the Start Command (e.g. `python manage.py migrate
# --noinput && gunicorn taskmanager.wsgi:application`).

set -o errexit  # exit immediately on any command failure
set -o nounset  # treat unset variables as an error

echo "==> Installing Python dependencies"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "==> Applying database migrations"
python manage.py migrate --noinput

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Build complete"