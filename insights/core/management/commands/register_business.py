"""Connect a business's ERPNext, asking for what is needed (secrets are not echoed):

    manage.py register_business

The platform reads that ERPNext over its standard API with the key and secret of a
user there; nothing is installed on it. Afterwards it shows what that user can read.
"""

import getpass

from django.core.management.base import BaseCommand

from insights.compat import run_as


class Command(BaseCommand):
    help = "Connect a business's ERPNext site to the platform."

    def add_arguments(self, parser):
        parser.add_argument("--name")
        parser.add_argument("--url")
        parser.add_argument("--company", default="")

    def handle(self, name=None, url=None, company="", **opts):
        name = name or input("Business name: ").strip()
        url = (url or input("Its ERPNext address (https://...): ").strip()).rstrip("/")
        api_key = input("API key of the ERPNext user the platform reads as: ").strip()
        api_secret = getpass.getpass("Its API secret (not shown): ").strip()
        from command_center import install
        from command_center.api import ingest
        with run_as("Administrator"):
            out = install.register_business(name, url, api_key, api_secret,
                                            erpnext_company=company or None)
        self.stdout.write(f"registered {out}")
        with run_as("Administrator"):
            ingest.check_access(out["code"])
