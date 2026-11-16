"""The Executive Summary's memo, as the screen asks for it (command_center/summary.py).

    memo(business_code)     the header, the five vital signs and their changes, the short
                            version (today's AI paragraph when written, else the one worked
                            out from the figures, with `pending` when the AI may write it
                            now), the three decisions, the risks, what is going well
    waiting(business_code)  Waiting On You: approvals awaiting you, delegated tasks done to
                            review, overdue delegated tasks (api/work.summary), or why they
                            cannot be read -- asked separately, so the memo never waits on
                            the business's ERPNext
    write(business_code)    today's short version by the AI, when it is not written yet;
                            the screen shows the fallback first and swaps this in

Reads only, apart from the paragraph kept per business per day and the day's vital signs.
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import require_manager


@frappe.whitelist()
def memo(business_code: str | None = None):
    require_manager()
    from command_center import summary
    return summary.memo(business_code)


@frappe.whitelist()
def waiting(business_code: str | None = None):
    require_manager()
    from command_center import summary
    return summary.waiting(business_code)


@frappe.whitelist(methods=["POST"])
def write(business_code: str | None = None):
    require_manager()
    from command_center import summary
    return summary.write(business_code)
