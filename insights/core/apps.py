import importlib
import pkgutil

from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "insights.core"
    label = "core"
    verbose_name = "Platform"

    def ready(self):
        """Import every module under command_center.api, so each @frappe.whitelist
        endpoint is registered before the first request asks for it."""
        import command_center.api as api
        for m in pkgutil.iter_modules(api.__path__):
            importlib.import_module(f"command_center.api.{m.name}")
        # The Settings screen's calls (platform administrators only).
        importlib.import_module("insights.core.platform_settings")
        # Plans, licences and usage: Plan & Usage, View Plans, Settings -> Customers.
        importlib.import_module("insights.core.plans")
        # Settings -> Security (the administrator's only), and every successful sign-in
        # in its record, whichever way it came.
        importlib.import_module("insights.core.security")
        from django.contrib.auth.signals import user_logged_in

        from insights.core.security import on_logged_in
        user_logged_in.connect(on_logged_in, dispatch_uid="insights-security-sign-in")
        # Every figure definition, once, before any request: loaded lazily, several
        # requests at once could find the catalogue half-filled.
        from command_center.kpi.registry import load_all
        load_all()
        # Where each API call's time goes (insights/core/timing.py).
        from insights.core import timing
        timing.install()
