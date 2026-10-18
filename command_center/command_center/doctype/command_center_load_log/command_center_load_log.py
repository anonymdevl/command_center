from frappe.model.document import Document


class CommandCenterLoadLog(Document):
    """One load of one fact: when, how long, how many rows, and whether it worked.

    Written by ingest/base.py on every run, scheduled or pressed, and kept for ninety
    days (api/ingest.prune_load_log). Business Health shows the latest of these, so a
    manager can see the figures they are reading were refreshed, and when.
    """
