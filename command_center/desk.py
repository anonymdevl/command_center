"""A desk workspace, so the platform's figures can be inspected without me.

The SPA arrives at step 4. Until then everything this app holds is invisible
unless you know the doctype names, which makes the only view of the numbers a
summary written by whoever loaded them. That is the wrong arrangement: figures
should be checkable by the person they are being reported to.

So this builds, inside ERPNext's own desk:

*   number cards for the figures that matter, computed live by Frappe rather than
    by us, which makes them an independent check on our fact tables
*   a chart of the ageing distribution, grouped by the bucket we stored
*   shortcuts into the fact tables themselves, where every row shows the source
    document it came from

Everything here is idempotent and public. It is created on install and by the
patch, so an existing site picks it up on `bench migrate`.
"""

from __future__ import annotations

import json

import frappe

FACT_INVOICE = "Command Center Fact Sales Invoice"
FACT_LINE = "Command Center Fact Sales Invoice Line"
FACT_PAYMENT = "Command Center Fact Payment Allocation"

UNPAID = [["outstanding_amount", ">", 0], ["src_docstatus", "=", 1]]


def build():
    cards = _number_cards()
    charts = _charts()
    _workspace(cards, charts)
    frappe.db.commit()
    return {"cards": cards, "charts": charts}


# ---------------------------------------------------------------------------
def _card(label, doctype, function, based_on=None, filters=None, color=None):
    existing = frappe.db.exists("Number Card", {"label": label})
    doc = frappe.get_doc("Number Card", existing) if existing else frappe.new_doc("Number Card")
    doc.update({
        "label": label,
        "type": "Document Type",
        "document_type": doctype,
        "function": function,
        "aggregate_function_based_on": based_on,
        "filters_json": json.dumps(filters or []),
        "is_public": 1,
        "show_percentage_stats": 0,
        "module": "Command Center",
        "color": color,
    })
    doc.save(ignore_permissions=True)
    return doc.name


def _number_cards():
    return [
        _card("Owed to us", FACT_INVOICE, "Sum", "outstanding_amount", UNPAID, "#c0392b"),
        _card("Unpaid invoices", FACT_INVOICE, "Count", None, UNPAID),
        _card("Beyond three months", FACT_INVOICE, "Sum", "outstanding_amount",
              UNPAID + [["ageing_bucket", "=", "90+"]], "#c0392b"),
        _card("Invoiced revenue", FACT_LINE, "Sum", "base_net_amount",
              [["src_docstatus", "=", 1]]),
        _card("Margin, where cost is known", FACT_LINE, "Sum", "base_margin_amount",
              [["src_docstatus", "=", 1], ["has_cost", "=", 1]]),
        _card("Cash applied", FACT_PAYMENT, "Sum", "allocated_amount"),
    ]


def _chart(name, doctype, based_on, group_by, filters=None, chart_type="Bar"):
    existing = frappe.db.exists("Dashboard Chart", {"chart_name": name})
    doc = frappe.get_doc("Dashboard Chart", existing) if existing else frappe.new_doc("Dashboard Chart")
    doc.update({
        "chart_name": name,
        "chart_type": "Group By",
        "document_type": doctype,
        "group_by_type": "Sum",
        "group_by_based_on": group_by,
        "aggregate_function_based_on": based_on,
        "filters_json": json.dumps(filters or []),
        "type": chart_type,
        "is_public": 1,
        "module": "Command Center",
        "number_of_groups": 0,
    })
    doc.save(ignore_permissions=True)
    return doc.name


def _charts():
    return [
        _chart("Money owed by age", FACT_INVOICE, "outstanding_amount",
               "ageing_bucket", UNPAID),
        _chart("Money owed by customer", FACT_INVOICE, "outstanding_amount",
               "customer", UNPAID),
        _chart("Revenue by item group", FACT_LINE, "base_net_amount",
               "item_group", [["src_docstatus", "=", 1]]),
    ]


# ---------------------------------------------------------------------------
def _workspace(cards, charts):
    name = "Command Center"
    doc = (frappe.get_doc("Workspace", name)
           if frappe.db.exists("Workspace", name) else frappe.new_doc("Workspace"))

    doc.update({
        "name": name, "label": name, "title": name,
        "module": "Command Center", "public": 1, "is_hidden": 0,
        "icon": "dashboard-list", "sequence_id": 99,
    })

    doc.set("number_cards", [{"number_card_name": c} for c in cards])
    doc.set("charts", [{"chart_name": c, "label": c} for c in charts])
    doc.set("shortcuts", [
        {"type": "DocType", "link_to": FACT_INVOICE, "label": "Invoices, as facts"},
        {"type": "DocType", "link_to": FACT_LINE, "label": "Invoice lines"},
        {"type": "DocType", "link_to": FACT_PAYMENT, "label": "Payments applied"},
        {"type": "DocType", "link_to": "Connected Business", "label": "Businesses"},
        {"type": "DocType", "link_to": "Command Center Ingest State", "label": "Load state"},
        {"type": "DocType", "link_to": "Command Center Change Event", "label": "Change feed"},
    ])
    doc.set("links", [
        {"type": "Card Break", "label": "Facts", "onboard": 0},
        {"type": "Link", "link_type": "DocType", "link_to": FACT_INVOICE,
         "label": "Fact Sales Invoice", "dependencies": "", "onboard": 0},
        {"type": "Link", "link_type": "DocType", "link_to": FACT_LINE,
         "label": "Fact Sales Invoice Line", "dependencies": "", "onboard": 0},
        {"type": "Link", "link_type": "DocType", "link_to": FACT_PAYMENT,
         "label": "Fact Payment Allocation", "dependencies": "", "onboard": 0},
        {"type": "Card Break", "label": "Platform", "onboard": 0},
        {"type": "Link", "link_type": "DocType", "link_to": "Connected Business",
         "label": "Connected Business", "dependencies": "", "onboard": 0},
        {"type": "Link", "link_type": "DocType", "link_to": "Command Center Ingest State",
         "label": "Ingest State", "dependencies": "", "onboard": 0},
        {"type": "Link", "link_type": "DocType", "link_to": "Command Center Change Event",
         "label": "Change Event", "dependencies": "", "onboard": 0},
        {"type": "Link", "link_type": "DocType", "link_to": "Command Center Site Credential",
         "label": "My Site Credentials", "dependencies": "", "onboard": 0},
    ])

    doc.content = json.dumps(_content(cards, charts))
    doc.flags.ignore_links = True
    doc.save(ignore_permissions=True)
    return doc.name


def _content(cards, charts):
    blocks = [
        _block("header", {"text": "<span class=\"h4\"><b>What the platform is showing</b></span>", "col": 12}),
        _block("paragraph", {"text": (
            "Every figure below is computed by Frappe from this app's fact tables — "
            "not by the code that loaded them. If a card disagrees with what the "
            "platform reports, the fact tables are wrong and the difference is "
            "visible here rather than hidden. Ageing is measured as at the latest "
            "posting date the data contains, not today."), "col": 12}),
    ]
    for c in cards:
        blocks.append(_block("number_card", {"number_card_name": c, "col": 4}))

    blocks.append(_block("spacer", {"col": 12}))
    blocks.append(_block("header", {"text": "<span class=\"h4\"><b>Distribution</b></span>", "col": 12}))
    for c in charts:
        blocks.append(_block("chart", {"chart_name": c, "col": 12 if "age" in c.lower() else 6}))

    blocks.append(_block("spacer", {"col": 12}))
    blocks.append(_block("header", {"text": "<span class=\"h4\"><b>Look at the rows</b></span>", "col": 12}))
    blocks.append(_block("paragraph", {"text": (
        "Each fact row carries the document it came from — source doctype, "
        "document name and child row. That is what makes any figure answerable "
        "with “which records?”"), "col": 12}))
    for label in ("Invoices, as facts", "Invoice lines", "Payments applied",
                  "Businesses", "Load state", "Change feed"):
        blocks.append(_block("shortcut", {"shortcut_name": label, "col": 4}))
    return blocks


def _block(kind, data):
    return {"id": frappe.generate_hash(length=10), "type": kind, "data": data}
