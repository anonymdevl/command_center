from frappe.model.document import Document


class CommandCenterReportRun(Document):
    """One writing of a management report for one business: who asked (or which schedule),
    where it is (queued, running, done, failed), and the report itself once written, so the
    Reports screen can say what happened last and reopen it (command_center.api.reports).

    Written by the reports job only (in_create), never by hand.
    """
