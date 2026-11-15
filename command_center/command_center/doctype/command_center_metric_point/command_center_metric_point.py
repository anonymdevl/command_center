from frappe.model.document import Document


class CommandCenterMetricPoint(Document):
    """One value of one figure for one business on one day (grain day) or for one month (grain month): the history a business's normal range is learned from (command_center.recommend.metrics).

    Written by the recommendations engine only (in_create), never by hand.
    """
