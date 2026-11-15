from frappe.model.document import Document


class CommandCenterRecommendation(Document):
    """One recommendation the engine made for a business, and what a manager did about it.

    Written by command_center.recommend.engine, never by hand (in_create). One open row per
    business and recommendation key: a condition that persists refreshes it; one that
    clears resolves it, and the row is kept as history. Done, Not Relevant and Snoozed are
    the manager's; Resolved is the engine's.
    """
