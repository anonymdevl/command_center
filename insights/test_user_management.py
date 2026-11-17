"""User Management (17 Nov 2026), as Michael asked:

    .venv-platform/bin/python manage.py test insights.test_user_management

  1. Anyone given Settings access, in any section, is a kind of administrator: the list
     says Yes for them, and only Yes (the sections are in Manage, from settings_access).
  2. Administrator accounts are seen by administrators only -- never by a delegate, in
     User Management, the people pickers (the same list) or ERPNext API Keys -- and a
     delegate who names one is answered as if there were no such person, as in ERPNext.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TransactionTestCase

from insights import tests as _tests  # the module: its TestCases are not collected twice

S = "insights.core.platform_settings"


class UserManagement(TransactionTestCase):
    databases = {"default", "aux"}

    def setUp(self):
        _tests.SettingsPage.setUp(self)
        self.addCleanup(_tests.SettingsPage.tearDown, self)
        U = get_user_model()
        mgr = U.objects.get(username="manager@test.com")
        for g in ("Settings: People", "Settings: Personal Keys"):
            mgr.groups.add(Group.objects.get_or_create(name=g)[0])
        plain = U.objects.create_user("plain@test.com", "plain@test.com", "a-long-test-pass-8")
        plain.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
        r = self._call(self.admin, "add_business", business_name="Test Medical Ltd",
                       site_url="https://erp.test", api_key="key-abcd1234",
                       api_secret="biz-secret-value-71x")
        self.assertEqual(r.status_code, 200, r.content[:300])
        r = self._call(self.admin, "set_credential", user="boss@test.com",
                       business_code="test_medical_ltd", api_key="boss-key", api_secret="boss-s")
        self.boss_key = r.json()["message"]["name"]

    def _call(self, client, fn, **args):
        return client.post(f"/api/method/{S}.{fn}", json.dumps(args),
                           content_type="application/json")

    def _people(self, client) -> dict:
        r = self._call(client, "people")
        self.assertEqual(r.status_code, 200, r.content[:300])
        return {p["username"]: p for p in r.json()["message"]}

    def test_settings_access_reads_as_administrator(self):
        listed = self._people(self.admin)
        boss, mgr, plain = (listed["boss@test.com"], listed["manager@test.com"],
                            listed["plain@test.com"])
        self.assertTrue(boss["settings_admin"])
        self.assertTrue(mgr["settings_admin"], "Settings access is a kind of administrator")
        self.assertEqual(sorted(mgr["settings_access"]), ["keys", "people"])
        self.assertFalse(mgr["is_admin"], "but not the platform's administrator")
        self.assertFalse(plain["settings_admin"])
        # Yes is enough: no sentence of sections for the table to print under it.
        for p in (boss, mgr, plain):
            self.assertNotIn("settings_words", p)

    def test_administrators_are_hidden_from_delegates(self):
        self.assertIn("boss@test.com", self._people(self.admin))
        listed = self._people(self.manager)
        self.assertNotIn("boss@test.com", listed)
        self.assertIn("plain@test.com", listed)
        self.assertIn("manager@test.com", listed)
        # named anyway: no such person, not "only the administrator can change them"
        for fn, args in (("set_active", {"on": 0}), ("reset_password", {"set_later": 1}),
                         ("update_person", {"full_name": "X Y"}),
                         ("send_set_password_link", {}),
                         ("set_credential", {"business_code": "test_medical_ltd",
                                             "api_key": "k", "api_secret": "s"})):
            body = {"username": "boss@test.com", "user": "boss@test.com", **args}
            r = self._call(self.manager, fn, **body)
            self.assertEqual(r.status_code, 417, f"{fn}: {r.content[:200]!r}")
            self.assertIn("no one with that email", r.content.decode(), fn)
            self.assertNotIn("administrator", json.loads(r.content)["exception"].lower(), fn)
        self.assertTrue(get_user_model().objects.get(username="boss@test.com").is_active)
        # their keys are not listed, nor can they be touched
        r = self._call(self.manager, "credentials")
        self.assertNotIn("boss@test.com", [c["user"] for c in r.json()["message"]])
        for fn in ("remove_credential", "test_credential"):
            self.assertIn(self._call(self.manager, fn, name=self.boss_key).status_code, (403, 417), fn)
        # nothing a delegate is sent names an administrator
        for fn in ("people", "credentials"):
            self.assertNotIn("boss@test.com", self._call(self.manager, fn).content.decode(), fn)
        page = self.manager.get("/command-center").content.decode()
        self.assertNotIn("boss@test.com", page)
