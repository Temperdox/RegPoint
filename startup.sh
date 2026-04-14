#!/bin/bash
# Azure App Service startup script
python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn RegPoint.wsgi --bind=0.0.0.0:8000 --workers=2 --timeout=600
