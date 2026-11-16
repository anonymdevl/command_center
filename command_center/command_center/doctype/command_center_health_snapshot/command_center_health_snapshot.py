from frappe.model.document import Document


class CommandCenterHealthSnapshot(Document):
    """Business Health on one day for one business: Control Health and each question's
    score and state (command_center.health). Named "<business>::<day>", so there is never
    more than one a day; the latest of the day replaces it.

    Written by command_center.health only (in_create), never by hand.
    """
