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


# --- plans, licences and usage (insights/core/plans.py) ---------------------------------
# The product the client bought: a customer account (one client, one or more Connected
# Businesses), its plan and licence, the people it pays seats for, and the usage ledger
# the monthly statement is built from. Not doctypes: they belong to the platform, not to
# the business logic, like the error log above.
class ClientAccount(models.Model):
    """A customer of the platform: who it is licensed to, which plan, any limits the
    administrator has overridden, the licence dates and the administrator's own rates."""

    name = models.CharField(max_length=140, unique=True)
    licensed_to = models.CharField(max_length=140, blank=True, default="")
    plan = models.CharField(max_length=40, default="custom")
    # {"ai_questions": 500, "seats": null, ...}: a key present overrides the plan's limit
    # (null = unlimited); a key absent takes the plan's.
    limits = models.TextField(blank=True, default="{}")
    licence_start = models.DateField(null=True, blank=True)
    # No renewal date: no expiry (the state of every business until a licence is set).
    renewal_date = models.DateField(null=True, blank=True)
    grace_days = models.IntegerField(default=30)
    allow_overage = models.BooleanField(default=True)
    # The administrator's rates for this customer, only ever shown to the administrator:
    # {"currency": "GHS", "base_fee": 0, "overage": {"ai_questions": 2.5, ...}}; a key
    # absent takes the plan's default.
    rates = models.TextField(blank=True, default="{}")
    notes = models.TextField(blank=True, default="")
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "insights_client_account"
        ordering = ["name"]
        verbose_name = "Customer"

    def __str__(self):
        return self.name


class ClientBusiness(models.Model):
    """A Connected Business belongs to one customer at most."""

    client = models.ForeignKey(ClientAccount, on_delete=models.CASCADE, related_name="businesses")
    business_code = models.CharField(max_length=140, unique=True)

    class Meta:
        db_table = "insights_client_business"


class ClientMember(models.Model):
    """A person who uses the platform for a customer, taking one of its seats. An
    Account Manager also sees Plan & Usage and receives its notices; a User sees the
    plan badge only."""

    ROLES = (("manager", "Account Manager"), ("user", "User"))
    client = models.ForeignKey(ClientAccount, on_delete=models.CASCADE, related_name="members")
    username = models.CharField(max_length=150, db_index=True)
    role = models.CharField(max_length=20, choices=ROLES, default="user")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "insights_client_member"
        unique_together = [("client", "username")]


class _Ledger(models.QuerySet):
    def update(self, **kw):
        raise PermissionError("The usage ledger is never edited: record a correction instead.")

    def delete(self):
        raise PermissionError("The usage ledger is never deleted from.")


class UsageEvent(models.Model):
    """One billable event, written once and never changed: an AI analyst question, an AI
    report, a Daily Brief, a scheduled report sent, tokens spent outside any of those (a
    connection check), or a day's count of seats and businesses. A correction is a new
    row on the same meter, with a positive or negative quantity, outcome "correction",
    and `corrects` naming the row it corrects (or none, for a month-level adjustment).

    On the "aux" connection (routers.py), like the error log: a question whose request
    is rolled back -- the analyst's write guard does exactly that -- still leaves its
    usage on record. client_id is a plain number for the same reason (no foreign key
    across connections); client_name is kept as it was at the time."""

    at = models.DateTimeField(db_index=True)
    period = models.CharField(max_length=7, db_index=True)  # "2026-11", server time
    client_id = models.IntegerField(null=True, blank=True, db_index=True)
    client_name = models.CharField(max_length=140, blank=True, default="")
    business_code = models.CharField(max_length=140, blank=True, default="", db_index=True)
    user = models.CharField(max_length=150, blank=True, default="")
    meter = models.CharField(max_length=40, db_index=True)
    quantity = models.IntegerField(default=0)
    input_tokens = models.BigIntegerField(default=0)
    output_tokens = models.BigIntegerField(default=0)
    cache_read_tokens = models.BigIntegerField(default=0)
    cache_write_tokens = models.BigIntegerField(default=0)
    requests = models.IntegerField(default=0)
    model = models.CharField(max_length=80, blank=True, default="")
    est_cost = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True)
    cost_currency = models.CharField(max_length=8, blank=True, default="")
    outcome = models.CharField(max_length=20, blank=True, default="ok")
    ref = models.CharField(max_length=140, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")
    corrects = models.IntegerField(null=True, blank=True)

    objects = _Ledger.as_manager()

    class Meta:
        db_table = "insights_usage_event"
        ordering = ["at", "id"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("The usage ledger is never edited: record a correction instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("The usage ledger is never deleted from.")


class PlanNotice(models.Model):
    """A notice in the bell (and by email when email is set up): an allowance at 80% or
    used up, a licence renewal coming or passed, the month's statements ready. One per
    person per `dedupe`, so a daily check never repeats itself. On "aux" with the ledger,
    because the allowance notices are raised when usage is recorded."""

    recipient = models.CharField(max_length=150, db_index=True)
    client_id = models.IntegerField(null=True, blank=True)
    kind = models.CharField(max_length=40)
    dedupe = models.CharField(max_length=140)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    link = models.CharField(max_length=40, blank=True, default="")
    created = models.DateTimeField(db_index=True)
    dismissed = models.DateTimeField(null=True, blank=True)
    emailed = models.BooleanField(default=False)

    class Meta:
        db_table = "insights_plan_notice"
        unique_together = [("recipient", "dedupe")]
        ordering = ["-created"]
