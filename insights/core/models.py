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


# --- security (insights/core/security.py, Settings -> Security) -----------------------
# The administrator's alone. The sign-in record is on "aux" with the usage ledger, so a
# request that is rolled back still leaves its sign-in attempt on record, and like the
# ledger it is never edited or deleted. Never a password, never a full key or secret.
class _AppendOnly(models.QuerySet):
    def update(self, **kw):
        raise PermissionError("The security record is never edited.")

    def delete(self):
        raise PermissionError("The security record is never deleted from.")


class SecurityEvent(models.Model):
    """One sign-in attempt on the platform or the administration, a sign-out, an
    unlock or a Sign Out Everywhere: who (as typed, for a failure), from where, with
    what kind of browser (a summary, never the whole user-agent string), and what
    happened."""

    at = models.DateTimeField(db_index=True)
    kind = models.CharField(max_length=30, db_index=True)      # sign_in, sign_out, unlock, end_sessions
    outcome = models.CharField(max_length=20, db_index=True)   # success, failed, blocked, refused, done
    username = models.CharField(max_length=150, blank=True, default="", db_index=True)
    known_user = models.BooleanField(default=False)
    ip = models.CharField(max_length=64, blank=True, default="", db_index=True)
    agent = models.CharField(max_length=80, blank=True, default="")
    channel = models.CharField(max_length=20, blank=True, default="")  # platform, admin, sso
    locked = models.BooleanField(default=False)    # this attempt locked the account or address
    new_ip = models.BooleanField(default=False)
    new_agent = models.BooleanField(default=False)
    first_seen = models.BooleanField(default=False)
    actor = models.CharField(max_length=150, blank=True, default="")   # who did an unlock
    note = models.CharField(max_length=255, blank=True, default="")

    objects = _AppendOnly.as_manager()

    class Meta:
        db_table = "insights_security_event"
        ordering = ["-at", "-id"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("The security record is never edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("The security record is never deleted from.")


class SecurityCheck(models.Model):
    """The last run of one watch check on one connected business's ERPNext: whether it
    could be read, and what was seen (the baseline the next run is compared with --
    names, dates, fingerprints of code and keys; never code or a key itself)."""

    business_code = models.CharField(max_length=140, db_index=True)
    check_id = models.CharField(max_length=40)
    status = models.CharField(max_length=20, default="ok")  # ok, refused, unavailable, unreachable, error
    message = models.TextField(blank=True, default="")
    baseline = models.TextField(blank=True, default="")
    checked_at = models.DateTimeField(null=True, blank=True)
    first_run = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "insights_security_check"
        unique_together = [("business_code", "check_id")]


class SecurityFinding(models.Model):
    """Something the watch or the sign-in record found, once per fingerprint. A finding
    about how things are now (a setting off, risky code present) clears itself when it is
    no longer so; one about something that happened (a new administrator, a new key)
    stays open until the administrator acknowledges it."""

    fingerprint = models.CharField(max_length=64, unique=True)
    business_code = models.CharField(max_length=140, blank=True, default="", db_index=True)
    check_id = models.CharField(max_length=40, db_index=True)
    severity = models.CharField(max_length=10, db_index=True)  # critical, high, medium, low, info
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True, default="")
    evidence = models.TextField(blank=True, default="[]")      # JSON list of {label, value}
    action = models.TextField(blank=True, default="")
    doc_url = models.CharField(max_length=500, blank=True, default="")
    state_kind = models.BooleanField(default=False)            # clears itself when gone
    status = models.CharField(max_length=20, default="open", db_index=True)  # open, acknowledged, cleared
    first_seen = models.DateTimeField(db_index=True)
    last_seen = models.DateTimeField()
    cleared_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.CharField(max_length=150, blank=True, default="")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    alerted = models.BooleanField(default=False)

    class Meta:
        db_table = "insights_security_finding"
        ordering = ["-first_seen", "-id"]


class SecurityIncident(models.Model):
    """The incident register: an incident opened from a finding or by hand, its
    status, the businesses it touched, and the report's sections."""

    STATUSES = ("Open", "Investigating", "Contained", "Resolved")
    title = models.CharField(max_length=200)
    severity = models.CharField(max_length=10, default="high")
    status = models.CharField(max_length=20, default="Open", db_index=True)
    businesses = models.TextField(blank=True, default="[]")    # JSON list of business codes
    findings = models.TextField(blank=True, default="[]")      # JSON list of finding ids
    summary = models.TextField(blank=True, default="")
    impact = models.TextField(blank=True, default="")
    actions = models.TextField(blank=True, default="")
    root_cause = models.TextField(blank=True, default="")
    lessons = models.TextField(blank=True, default="")
    recommendations = models.TextField(blank=True, default="")
    opened_by = models.CharField(max_length=150, blank=True, default="")
    opened_at = models.DateTimeField(db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    modified = models.DateTimeField()

    class Meta:
        db_table = "insights_security_incident"
        ordering = ["-opened_at", "-id"]


class SecurityIncidentNote(models.Model):
    """One line of an incident's timeline, as written, never changed."""

    incident = models.ForeignKey(SecurityIncident, on_delete=models.CASCADE, related_name="notes")
    at = models.DateTimeField()
    by = models.CharField(max_length=150, blank=True, default="")
    kind = models.CharField(max_length=20, default="note")    # note, status, finding, opened
    text = models.TextField()

    class Meta:
        db_table = "insights_security_incident_note"
        ordering = ["at", "id"]
