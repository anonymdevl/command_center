"""Add someone who may use the platform, and set their password (not echoed):

    manage.py add_manager someone@business.com "Their Name"

They sign in at /command-center-login. --admin makes them a platform administrator.
"""

import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError

from command_center.api.businesses import ROLE


class Command(BaseCommand):
    help = "Add a manager (or, with --admin, an administrator) and set their password."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("full_name", nargs="?", default="")
        parser.add_argument("--admin", action="store_true")
        parser.add_argument("--no-password", action="store_true")

    def handle(self, email, full_name, admin=False, no_password=False, **opts):
        email = email.strip().lower()
        U = get_user_model()
        user, created = U.objects.get_or_create(username=email, defaults={"email": email})
        first, _, last = (full_name or "").partition(" ")
        if full_name:
            user.first_name, user.last_name = first, last
        user.email = email
        user.is_active = True
        if admin:
            user.is_staff = user.is_superuser = True
        if not no_password:
            pw = getpass.getpass(f"Password for {email} (not shown): ")
            if pw != getpass.getpass("Again: "):
                raise CommandError("The two passwords differ.")
            validate_password(pw, user)
            user.set_password(pw)
        elif created:
            user.set_unusable_password()
        user.save()
        user.groups.add(Group.objects.get_or_create(name=ROLE)[0])
        self.stdout.write(f"{'added' if created else 'updated'} {email}"
                          f"{' (administrator)' if admin else ''}: {ROLE}")
