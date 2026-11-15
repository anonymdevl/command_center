"""Run one of the business logic's functions, like `bench execute`:

    manage.py execute command_center.api.ingest.run_all --kwargs '{"full": true}'

It runs as Administrator -- the platform itself -- in one transaction, committed when it
finishes. The result is printed as JSON.
"""

import json

from django.core.management.base import BaseCommand

from insights.compat import get_attr, run_as


class Command(BaseCommand):
    help = "Run a function of the business logic as the platform (Administrator)."

    def add_arguments(self, parser):
        parser.add_argument("method")
        parser.add_argument("--kwargs", default="{}")
        # dest is not "args": Django takes an option of that name as the command's
        # positional arguments, which made every call fail.
        parser.add_argument("--args", dest="fn_args", default="[]")
        parser.add_argument("--user", default="Administrator")

    def handle(self, *_, method, kwargs, fn_args, user, **opts):
        fn = get_attr(method)
        with run_as(user):
            result = fn(*json.loads(fn_args), **json.loads(kwargs))
        if result is not None:
            self.stdout.write(json.dumps(result, default=str))
