"""The platform's tables.

The business tables are generated from the doctype JSON (models_generated.py) and keep
their names. The few below are what Frappe used to provide around them: the error log,
per-user stored values (DefaultValue), and the encrypted store for passwords -- a
business's API secret never sits in a readable column.

People are Django's own users: username = the person's email, groups = their roles
("Insights Dashboard Manager"), is_superuser = the platform's administrator.
"""

from django.db import models

from insights.core.models_generated import *  # noqa: F401,F403
from insights.core.models_generated import DOCTYPE_MODELS  # noqa: F401


class ErrorLog(models.Model):
    """frappe.log_error: what went wrong, for whoever watches the platform."""

    title = models.CharField(max_length=255, db_index=True)
    error = models.TextField(blank=True, default="")
    creation = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "tabError Log"
        ordering = ["-creation"]
        verbose_name = "Error Log"
        verbose_name_plural = "Error Log"

    def __str__(self):
        return f"{self.creation:%Y-%m-%d %H:%M} {self.title}"


class DefaultValue(models.Model):
    """frappe.defaults: small stored values, per user or global (parent '__default')."""

    parent = models.CharField(max_length=140, db_index=True)
    defkey = models.CharField(max_length=140, db_index=True)
    defvalue = models.TextField(blank=True, default="")

    class Meta:
        db_table = "tabDefaultValue"


class Secret(models.Model):
    """A Password field's value, encrypted with the platform's key
    (insights.compat.secrets). Never a column on the business tables themselves."""

    doctype = models.CharField(max_length=140)
    docname = models.CharField(max_length=140)
    fieldname = models.CharField(max_length=140)
    value = models.TextField()

    class Meta:
        db_table = "__Auth"
        unique_together = [("doctype", "docname", "fieldname")]
