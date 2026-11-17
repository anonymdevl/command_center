"""The error log and the shared cache use the "aux" connection (see settings.py), so a
request that rolls back its work never rolls back the record of what went wrong, and a
value one request puts in the cache is seen by the next at once."""

from django.conf import settings

AUX_MODELS = {("core", "errorlog"), ("django_cache", "cacheentry"),
              # the usage ledger and its notices (plans.py): billing outlives a rollback
              ("core", "usageevent"), ("core", "plannotice"),
              # the sign-in record (security.py): a rolled-back request keeps its attempt
              ("core", "securityevent"),
              # every email send attempt (runtime.sendmail): a rolled-back request keeps it
              ("core", "emaillog")}


class AuxRouter:
    def _aux(self, model) -> bool:
        return (model._meta.app_label, model._meta.model_name) in AUX_MODELS

    def db_for_read(self, model, **hints):
        return "aux" if self._aux(model) else None

    def db_for_write(self, model, **hints):
        return "aux" if self._aux(model) else None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db != "aux":
            return None
        # On MariaDB "aux" is the default database itself: migrate once, there.
        if not settings.AUX_SEPARATE:
            return False
        return (app_label, model_name) in AUX_MODELS
