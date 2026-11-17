from frappe.model.document import Document


class CommandCenterTaskSendBack(Document):
    """One "Send it back" on work a manager handed out (api/work.review): which To-Do on
    which business, who sent it back, when, and their reason. Outstanding Tasks counts
    these for "Sent Back More Than Once", so the count never depends on whether the
    manager may read ERPNext's Comments.

    Written by command_center.api.work only (in_create), never by hand.
    """
