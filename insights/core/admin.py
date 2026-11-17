"""The platform's administration (/admin): businesses, people, and what went wrong.

For the platform's administrator only (Django staff). Managers never see it -- their
platform is the designed interface at /command-center. People and their roles are
Django's own Users and Groups pages; give a person the "Insights Dashboard Manager"
group to let them in.

A business's API secret is entered here and stored encrypted (insights.compat
documents.set_password); the form never shows it back.
"""

from django import forms
from django.contrib import admin

from insights.compat import documents
from insights.core import models


class _SecretsForm(forms.ModelForm):
    """A model form with write-only password inputs for the doctype's Password fields."""

    SECRETS: tuple = ()

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        for f in self.SECRETS:
            have = bool(self.instance.pk and documents.get_password(
                self.instance._meta.verbose_name, self.instance.pk, f, raise_exception=False))
            self.fields[f] = forms.CharField(
                required=False, widget=forms.PasswordInput(render_value=False),
                help_text="Stored encrypted. " + ("Leave blank to keep the current one."
                                                   if have else "Not set yet."))

    def save(self, commit=True):
        obj = super().save(commit=commit)
        self._pending = {f: self.cleaned_data.get(f) for f in self.SECRETS
                         if self.cleaned_data.get(f)}
        return obj


class _SecretsAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        from insights.compat.utils import now_datetime
        if not obj.creation:
            obj.creation = now_datetime()
        obj.modified = now_datetime()
        obj.modified_by = request.user.username
        if not obj.owner:
            obj.owner = request.user.username
        super().save_model(request, obj, form, change)
        for field, value in getattr(form, "_pending", {}).items():
            documents.set_password(obj._meta.verbose_name, obj.pk, field, value)


class ConnectedBusinessForm(_SecretsForm):
    SECRETS = ("api_secret", "sso_client_secret")

    class Meta:
        model = models.ConnectedBusiness
        exclude = ("creation", "modified", "modified_by", "owner", "docstatus", "idx")

    def clean(self):
        """A new address on another server: the secret is typed again, never the stored
        one sent there (platform_settings.update_business holds the same rule)."""
        from insights.core.platform_settings import address_moved
        data = super().clean()
        old = self.instance.site_url if self.instance.pk else None
        self.moved = address_moved(old, data.get("site_url"))
        if self.moved and not data.get("api_secret"):
            raise forms.ValidationError(
                "The address is on another server now, so type the API secret again. The "
                "stored secrets belong to the old address and are removed, never sent to "
                "the new one.")
        return data


@admin.register(models.ConnectedBusiness)
class ConnectedBusinessAdmin(_SecretsAdmin):
    form = ConnectedBusinessForm

    def save_model(self, request, obj, form, change):
        if change and getattr(form, "moved", False):
            from insights.core.platform_settings import forget_for_move
            forget_for_move(obj.pk, obj.business_code)
            if not form.cleaned_data.get("sso_client_secret"):
                obj.sso_client_id = None
        super().save_model(request, obj, form, change)
    list_display = ("business_name", "business_code", "site_url", "status", "currency")
    search_fields = ("business_name", "business_code", "site_url")
    list_filter = ("status",)


class SiteCredentialForm(_SecretsForm):
    SECRETS = ("api_secret",)

    class Meta:
        model = models.CommandCenterSiteCredential
        exclude = ("creation", "modified", "modified_by", "owner", "docstatus", "idx")


@admin.register(models.CommandCenterSiteCredential)
class SiteCredentialAdmin(_SecretsAdmin):
    form = SiteCredentialForm
    list_display = ("user", "business_code", "api_key")
    search_fields = ("user", "business_code")


@admin.register(models.CommandCenterAlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ("rule_id", "enabled", "severity", "threshold_amount", "threshold_days")


@admin.register(models.CommandCenterReportSchedule)
class ReportScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "report", "business_code", "enabled", "frequency")


@admin.register(models.CommandCenterIngestState)
class IngestStateAdmin(admin.ModelAdmin):
    list_display = ("fact", "business_code", "status", "last_run", "last_src_modified", "as_of_date")
    list_filter = ("business_code", "status")

    def has_add_permission(self, request):
        return False


@admin.register(models.CommandCenterLoadLog)
class LoadLogAdmin(admin.ModelAdmin):
    list_display = ("fact", "business_code", "status", "rows_loaded", "started", "seconds")
    list_filter = ("business_code", "status")

    def has_add_permission(self, request):
        return False


@admin.register(models.ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ("creation", "title")
    search_fields = ("title", "error")
    readonly_fields = ("title", "error", "creation")

    def has_add_permission(self, request):
        return False
