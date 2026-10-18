from frappe.model.document import Document


class CommandCenterConversation(Document):
    """One person's conversation with the AI: their questions and its answers.

    Private to the person who had it (if_owner on every role), kept on the server so it
    survives a refresh, a sign-out and a different device. Written and read only through
    api/conversations.py; the assistant itself never reads or writes it.
    """
