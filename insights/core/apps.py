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
