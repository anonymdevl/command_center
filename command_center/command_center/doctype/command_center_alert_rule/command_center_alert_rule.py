from frappe.model.document import Document


class CommandCenterAlertRule(Document):
    """One alert rule's switch and thresholds, editable by the site's administrators (AL-05).

    Created with the defaults in command_center.alerts.rules the first time the engine
    runs; changing a threshold here changes what is raised next time, with no release.
    """
