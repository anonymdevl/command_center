"""Add someone who may use the platform, and set their password (not echoed):

    manage.py add_manager someone@business.com "Their Name"

They sign in at /sign-in. --admin makes them a platform administrator.
"""

import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
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
            user.set_password(self._ask_password(email, user))
        elif created:
            user.set_unusable_password()
        user.save()
        user.groups.add(Group.objects.get_or_create(name=ROLE)[0])
        self.stdout.write(f"{'added' if created else 'updated'} {email}"
                          f"{' (administrator)' if admin else ''}: {ROLE}")

    def _ask_password(self, email, user, tries=5):
        """Ask until the password is acceptable (at least 10 characters, not common,
        not all digits, not like the email), saying what was wrong each time."""
        for _ in range(tries):
            pw = getpass.getpass(f"Password for {email} (at least 10 characters, not shown): ")
            if pw != getpass.getpass("Again: "):
                self.stderr.write("   The two passwords differ. Try again.")
                continue
            try:
                validate_password(pw, user)
            except ValidationError as e:
                self.stderr.write("   " + " ".join(e.messages) + " Try again.")
                continue
            return pw
        raise CommandError("No acceptable password given.")
