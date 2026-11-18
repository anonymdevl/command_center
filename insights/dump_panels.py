"""The panels every screen shows, as the platform answers them for the test business.

    DUMP_OUT=frontend/preview/real-panels.json INSIGHTS_CONFIG=$PWD/insights.json \
        DJANGO_SETTINGS_MODULE=insights.settings .venv-platform/bin/python manage.py test insights.dump_panels

Not part of `manage.py test insights` (the name does not start with "test"). The preview's
sample panels are only tables; with ?real=1 (preview/mock.js) it shows these instead, so
the notes, subtitles and findings on a screen are the real ones at their real length
(18 Nov 2026, the lean-cards review). Do not run it while another test run is going: it
uses the same test database.
"""

import json, os
from unittest import mock
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TransactionTestCase
from insights import tests as T
from insights import bench_screens as B

class Dump(TransactionTestCase):
    databases = {"default", "aux"}
    def test_dump(self):
        from django.conf import settings
        from cryptography.fernet import Fernet
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        Group.objects.get_or_create(name="Insights Dashboard Manager")
        fake = T.FakeERPNext()
        with mock.patch("requests.get", fake("GET")), mock.patch("requests.post", fake("POST")), \
             mock.patch("command_center.speed.person_waits", lambda *a, **k: False):
            from command_center import install
            from command_center.api import ingest
            from insights.compat import run_as
            with mock.patch("time.sleep", lambda s: None):
                with run_as("Administrator"):
                    install.register_business("Test Medical Ltd", "https://erp.test", "key", "s3cret")
                    ingest.run_all(full=True)
            U = get_user_model()
            m = U.objects.create_user("manager@test.com", "manager@test.com", "a-long-test-pass-9")
            m.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
            c = Client(); c.login(username="manager@test.com", password="a-long-test-pass-9")
            keys = B._keys(); out = {}
            for v in B.VIEWS:
                out[v] = {}
                for method, args in B._calls(v, keys.get(v)):
                    r = c.post(f"/api/method/{method}", json.dumps(args), content_type="application/json")
                    try: out[v][method] = r.json().get("message")
                    except Exception: out[v][method] = r.status_code
            json.dump(out, open(os.environ["DUMP_OUT"], "w"), indent=1, default=str)
