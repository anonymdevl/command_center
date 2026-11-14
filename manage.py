#!/usr/bin/env python
"""The platform's command line: manage.py migrate | runserver | createsuperuser | ..."""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "insights.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
