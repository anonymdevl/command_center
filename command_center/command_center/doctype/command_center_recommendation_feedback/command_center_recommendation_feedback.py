from frappe.model.document import Document


class CommandCenterRecommendationFeedback(Document):
    """A manager's decision about a recommendation, and -- for Done -- whether the figure improved afterwards (command_center.recommend.learning). Feeds the rule's learned weight.

    Written by the recommendations engine only (in_create), never by hand.
    """
