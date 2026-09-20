import frappe
from frappe.model.document import Document


class ConnectedBusiness(Document):
    def validate(self):
        self._only_one_local()
        self._normalise()
        self._protect_owned_settings()

    def _only_one_local(self):
        if not self.is_local:
            return
        other = frappe.db.get_value(
            "Connected Business", {"is_local": 1, "name": ["!=", self.name]}, "name"
        )
        if other:
            frappe.throw(
                f"{other} is already registered as this site. Only one business "
                f"can hold this site's own data."
            )

    def _normalise(self):
        if self.business_code:
            self.business_code = frappe.scrub(self.business_code)[:40]
        if self.site_url:
            self.site_url = self.site_url.strip().rstrip("/")
        if self.is_local:
            # A local business has no connection details by definition.
            self.site_url = None
            self.api_key = None

    def _protect_owned_settings(self):
        """A peer's settings are read, never written.

        Without this, two administrators on two sites could set different values
        for the same business and the platform would disagree with itself about
        what "overdue" means. The rule is that the site holding the data owns the
        judgement applied to it.
        """
        if self.is_local or self.is_new():
            return
        owned = ("overdue_after_days", "approval_threshold")
        before = self.get_doc_before_save()
        if not before:
            return
        changed = [f for f in owned if self.get(f) != before.get(f)]
        if changed:
            frappe.throw(
                f"{self.business_name} is on another site, which owns these "
                f"settings: {', '.join(changed)}. Change them there."
            )

    def on_update(self):
        # The change feed caches this site's business code on every insert path.
        # Without this the cache outlives a rename or a re-flagging of is_local.
        frappe.cache().delete_value("cc_local_business_code")

    def on_trash(self):
        frappe.cache().delete_value("cc_local_business_code")

    def test_connection(self):
        from command_center.connectors.registry import connector_for

        return connector_for(self.business_code).ping()
