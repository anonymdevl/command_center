from frappe.model.document import Document


class CommandCenterAlert(Document):
    """A material exception the alert engine found, and what was done about it.

    Raised by command_center.alerts.engine, never by hand (in_create). The lifecycle --
    raised, acknowledged, actioned, deferred, dismissed, false positive, resolved -- is
    kept, so the rules can be tuned against what managers actually did (AL-06).
    """
