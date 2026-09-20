"""The assistant's catalogue. Everything it can do is in this file.

Gigmann's requirements AI-B1 to AI-B8 name eight classes of action the assistant
must not be able to take on its own initiative:

    1.  issue or amend an invoice, credit note, price, discount or credit term
    2.  initiate a payment, transfer or purchase
    3.  post a journal or touch a reconciled balance
    4.  alter payroll or tax records
    5.  change customer, supplier, employee or item master data
    6.  send binding external correspondence
    7.  release a Board or governance report
    8.  delete anything

None of those appear below, and the assistant cannot reach `actions.py`. It is
handed TOOL_CATALOGUE and nothing else — there is no query tool, no passthrough,
no `eval`. The model returns a name from this dictionary; if a name is not in it,
nothing happens.

This constrains the assistant. **It does not constrain a manager.** Everything in
the eight classes remains available to a human being through actions.py, subject
to their ERPNext permissions, because a platform that stops a CEO approving a
purchase order is not a safe platform, it is a broken one. The restriction exists
because an unattended model should not be able to move money on a hunch, not
because the actions are forbidden.

Raising the ceiling is a one-line change here, per tool, per client — which is the
point of keeping the catalogue in one small file.
"""

from __future__ import annotations

from command_center.api import actions


def draft_communication(business_code: str, to: str, subject: str, body: str,
                        about_doctype: str | None = None,
                        about_name: str | None = None):
    """Write it; never send it.

    A drafted message waits for a person. Requirement AI-B6 is about binding
    correspondence leaving the company unread, not about drafting being unsafe.
    """
    note = f"Draft to {to} — {subject}\n\n{body}"
    return actions.add_comment(business_code,
                               about_doctype or "Communication",
                               about_name or "draft", note) \
        if about_doctype and about_name else {"draft": note, "sent": False}


TOOL_CATALOGUE = {
    # Delegation — the assistant may put work in front of a person.
    "create_task": actions.create_task,
    "assign_to": actions.assign_to,
    # Annotation — the assistant may write on a record, never change its values.
    "add_comment": actions.add_comment,
    # Correspondence — drafted, held, never sent.
    "draft_communication": draft_communication,
}


def call(tool_name: str, **kwargs):
    """The assistant's only route to anything.

    A name not in the catalogue does not reach a function. That is the whole of
    the mechanism, and it is why the boundary does not depend on the model
    behaving itself.
    """
    fn = TOOL_CATALOGUE.get(tool_name)
    if not fn:
        raise KeyError(
            f"'{tool_name}' is not a tool the assistant has. Available: "
            f"{', '.join(sorted(TOOL_CATALOGUE))}."
        )
    return fn(**kwargs)
