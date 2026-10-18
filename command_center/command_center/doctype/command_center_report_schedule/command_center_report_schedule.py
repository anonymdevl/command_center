import frappe
from frappe.model.document import Document


class CommandCenterReportSchedule(Document):
    """When a management report is written and who it is emailed to.

    Edited from the Reports screen or here. Recipients must be people with an enabled
    account on this site, so a scheduled report never leaves the company; the board
    report is not schedulable at all (it is released only with an approval).
    """

    def validate(self):
        from command_center.api.reports import check_schedule, next_run

        check_schedule(self)
        self.next_run = next_run(self) if self.enabled else None
