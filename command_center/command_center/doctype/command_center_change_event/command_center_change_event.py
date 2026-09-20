from frappe.model.document import Document


class CommandCenterChangeEvent(Document):
    """One line per tracked transaction.

    The feed exists so that refreshing figures does not mean re-reading tables.
    Rows are disposable: once consumed they are pruned, and a lost row is
    recovered by the next full sweep.
    """
