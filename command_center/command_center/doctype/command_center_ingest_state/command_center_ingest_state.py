from frappe.model.document import Document


class CommandCenterIngestState(Document):
    """Where each fact load got to, and what it measured against.

    One row per fact per business. It holds the watermark that makes the next run
    incremental, and the as-of date that run used — recorded rather than inferred,
    because an ageing figure whose reference date is unknown cannot be checked.
    """
