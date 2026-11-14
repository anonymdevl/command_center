"""First-time setup of a platform installation, safe to run again:

    manage.py setup

Writes a configuration file if there is none (with a new secret key and encryption
key), creates the database tables and the cache, and the role managers hold.
"""

import json
import os
import secrets

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand

from command_center.api.businesses import ROLE


class Command(BaseCommand):
    help = "Create the configuration (if missing), tables, cache and the manager role."

    def handle(self, **opts):
        path = settings.CONFIG_PATH
        data = {}
        if os.path.exists(path):
            with open(path) as fh:
                data = json.load(fh)
        changed = False
        if not data.get("secret_key"):
            data["secret_key"] = secrets.token_urlsafe(50)
            changed = True
        if not data.get("encryption_key"):
            data["encryption_key"] = Fernet.generate_key().decode()
            changed = True
        if changed:
            with open(path, "w") as fh:
                json.dump(data, fh, indent=1)
            os.chmod(path, 0o600)
            settings.CONFIG.update(data)
            self.stdout.write(f"wrote keys to {path} (keep it private; back it up -- "
                              f"without the encryption key stored passwords cannot be read)")
        call_command("migrate", interactive=False, verbosity=0)
        if settings.AUX_SEPARATE:
            call_command("migrate", database="aux", interactive=False, verbosity=0)
        call_command("createcachetable", verbosity=0)
        if settings.AUX_SEPARATE:
            call_command("createcachetable", database="aux", verbosity=0)
        Group.objects.get_or_create(name=ROLE)
        self.stdout.write(f"ready: tables, cache, role {ROLE!r}")
