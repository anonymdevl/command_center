"""Buying and payables KPIs.

The mirror of the sales side, and deliberately so: what is owed to us and what we
owe are the same question asked in two directions, and a manager comparing them
should not have to allow for two different definitions of "overdue".
"""

from command_center.kpi.registry import Kpi, register

UNPAID = {"outstanding_amount": [">", 0], "src_docstatus": 1}
SUBMITTED = {"src_docstatus": 1}

register(
    Kpi(
        key="ap_total",
        label="We owe suppliers",
        fact="fact_purchase_invoice",
        measure="outstanding_amount",
        unit="currency",
        direction="higher_is_worse",
        filters=UNPAID,
        note="{ap_count} invoices unpaid",
        drill_filters=UNPAID,
        as_of_basis="data_horizon",
        components=("ap_over_90", "ap_inside_90"),
    ),
    Kpi(
        key="ap_count",
        label="Unpaid supplier invoices",
        fact="fact_purchase_invoice",
        measure="*",
        agg="count",
        unit="count",
        filters=UNPAID,
        note="worth {ap_total}",
        drill_filters=UNPAID,
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="ap_over_90",
        label="Owed over three months",
        fact="fact_purchase_invoice",
        measure="outstanding_amount",
        unit="currency",
        direction="higher_is_worse",
        filters={**UNPAID, "ageing_bucket": "90+"},
        note="{ap_over_90_share} of what we owe",
        drill_filters={**UNPAID, "ageing_bucket": "90+"},
        as_of_basis="data_horizon",
        subset_of="everything we owe",
        share_of="ap_total",
    ),
    Kpi(
        key="ap_inside_90",
        label="Still inside 90 days",
        fact="fact_purchase_invoice",
        measure="outstanding_amount",
        unit="currency",
        filters={**UNPAID,
                 "ageing_bucket": ["in", ["Not yet due", "0-30", "31-60", "61-90"]]},
        note="{ap_inside_90_share} of what we owe",
        drill_filters={**UNPAID,
                       "ageing_bucket": ["in", ["Not yet due", "0-30", "31-60", "61-90"]]},
        as_of_basis="data_horizon",
        subset_of="everything we owe",
        share_of="ap_total",
    ),
    Kpi(
        key="spend_total",
        label="Bought in",
        fact="fact_purchase_invoice_line",
        measure="base_net_amount",
        unit="currency",
        direction="neutral",
        filters=SUBMITTED,
        note="across every submitted purchase line",
        drill_filters=SUBMITTED,
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="spend_lines",
        label="Purchase lines",
        fact="fact_purchase_invoice_line",
        measure="*",
        agg="count",
        unit="count",
        filters=SUBMITTED,
        note="worth {spend_total}",
        drill_filters=SUBMITTED,
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="supplier_billed",
        label="Billed to us",
        fact="fact_purchase_invoice",
        measure="base_grand_total",
        unit="currency",
        direction="neutral",
        filters=SUBMITTED,
        note="every submitted supplier invoice",
        drill_filters=SUBMITTED,
        as_of_basis="data_horizon",
    ),
    Kpi(
        # Named for what it measures. The first version of this was called
        # ap_settled_pct and labelled "Paid off" while computing the unpaid share --
        # the card would have shown a number that contradicted its own label, which
        # is worse than a wrong number because it is not obviously wrong.
        key="ap_unpaid_pct",
        label="Still unpaid",
        fact="fact_purchase_invoice",
        measure="*",
        agg="ratio",
        numerator="ap_total",
        denominator="supplier_billed",
        unit="percent",
        direction="higher_is_worse",
        note="of {supplier_billed} billed to us",
        as_of_basis="data_horizon",
        subset_of="everything billed to us",
    ),
)
