"""The platform's web entry point: gunicorn insights.wsgi:application"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "insights.settings")
application = get_wsgi_application()
