"""The explanation spec of each figure: what it is, what it should look like, what to do.

A KPI's definition (kpi/registry.py, kpi/live.py) says how it is computed. A Spec adds
what a manager needs to understand it, and is written once per kind of figure, never per
business: every amount the drawer shows is computed (diagnose.py, build.py), and the
words here carry no number.

    what         one or two plain sentences: what the figure is
    expected     the position a well-run business would show
    owner        who usually owns putting it right
    diagnose     (ctx, key) -> the parts that explain it now (diagnose.py), or None
    resolution   the steps, in order; RECONCILE means guides.RECONCILE_STEPS
    order        the order to tackle it in
    prevention   (sentence, ERPNext path, link label) -- the process change that stops it
                 recurring, each opening the right page on the business's own ERPNext
    related      the KPI keys whose drawers it links to
    recs         recommendation rules (recommend/rules.py) that watch the same thing
    empty        the guide when nothing is recorded behind it: (text, steps, path)
    light        True: another view owns its explanation; only the basics and a link

Every KPI has one: a deep Spec registered here, or the generic one build.py makes from its
definition (fact, measure, filters, direction).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

RECONCILE = "__reconcile__"


@dataclass(frozen=True)
class Spec:
    what: str
    expected: str
    owner: str = "Accounts"
    diagnose: Callable | None = None
    resolution: tuple = ()
    order: str = ""
    prevention: tuple = ()
    related: tuple = ()
    recs: tuple = ()
    empty: tuple | None = None
    light: bool = False
    link: dict | None = None
    extra: dict = field(default_factory=dict)


SPECS: dict[str, Spec] = {}


def register(keys, spec: Spec):
    for k in keys:
        if k in SPECS:
            raise ValueError(f"insight spec for {k!r} is registered twice")
        SPECS[k] = spec


# --------------------------------------------------------------------------- receivables
def _ledger(party_type):
    def run(ctx, key):
        from command_center.insight.diagnose import ledger
        return ledger(ctx, party_type, key)
    return run


def _revenue(ctx, key):
    from command_center.insight.diagnose import revenue
    return revenue(ctx, key)


def _stock(ctx, key):
    from command_center.insight.diagnose import stock
    return stock(ctx, key)


def _bank(ctx, key):
    from command_center.insight.diagnose import bank
    return bank(ctx)


AR_PREVENT = (
    ("Receive every payment against its invoice: open the Sales Invoice and use Create, "
     "then Payment, so the Payment Entry is allocated to it as it is made.",
     "/app/sales-invoice?docstatus=1", "Open Sales Invoices"),
    ("Make returns from the original invoice (Create, then Return / Credit Note), so the "
     "credit note is set against that invoice and not left floating.",
     "/app/sales-invoice?is_return=1", "Open credit notes"),
    ("__auto_reconcile__", "/app/accounts-settings", "Open Accounts Settings"),
    ("Close each month with a reconciliation: Payment Reconciliation for every customer "
     "with unmatched payments, then check that Accounts Receivable agrees with the "
     "customer ledger. This drawer shows the difference after every load.",
     "/app/query-report/Accounts%20Receivable", "Open Accounts Receivable"),
)
AP_PREVENT = (
    ("Pay every supplier against the bill: open the Purchase Invoice and use Create, then "
     "Payment, so the Payment Entry is allocated to it as it is made.",
     "/app/purchase-invoice?docstatus=1", "Open Purchase Invoices"),
    ("Record supplier credits as a debit note made from the bill (Create, then Return / "
     "Debit Note), so it is set against that bill.",
     "/app/purchase-invoice?is_return=1", "Open debit notes"),
    ("__auto_reconcile__", "/app/accounts-settings", "Open Accounts Settings"),
    ("Close each month with a reconciliation: Payment Reconciliation for every supplier "
     "with unmatched payments, then check that Accounts Payable agrees with the supplier "
     "ledger before the payment run is drawn from the bills.",
     "/app/query-report/Accounts%20Payable", "Open Accounts Payable"),
)
AR_RESOLVE = (
    "Start with the largest differences listed above, one customer at a time.",
    RECONCILE,
    "Advances and customers in credit: in the same screen the advance payments are listed "
    "as unreconciled; allocate them to the customer's invoices. Refund only a customer with "
    "no open invoice left (Payment Entry, Pay, against the customer).",
    "Credit notes and journal credits are listed there too (Credit Note and Journal Entry "
    "lines); allocate them to the invoices they reduce.",
    "Within a customer, match the oldest invoices first unless the remittance names them.",
)
AP_RESOLVE = (
    "Start with the largest differences listed above, one supplier at a time.",
    RECONCILE,
    "Advances paid to suppliers: allocate them to the supplier's bills in the same screen. "
    "Ask for a refund or a credit only where no bill is left open.",
    "Debit notes and journal debits are listed there too; allocate them to the bills they "
    "reduce.",
    "Within a supplier, match the oldest bills first unless the remittance names them.",
)
AR_RELATED = ("ar_total", "ar_open_invoices", "ar_unmatched", "ar_in_credit", "ar_over_90",
              "ar_inside_90", "ar_undated")
AP_RELATED = ("ap_total", "ap_open_invoices", "ap_unmatched", "ap_in_credit", "ap_over_90",
              "ap_inside_90", "ap_undated")
AR_RECS = ("unmatched_receipts", "customers_in_credit", "overdue_customers", "credit_hold")
AP_RECS = ("unmatched_supplier_payments", "long_unpaid_bills", "supplier_payments_due")
AR_EMPTY = ("No customer balance is recorded in ERPNext yet.",
            ["Raise each sale as a Sales Invoice and submit it.",
             "Record each payment received as a Payment Entry made from the invoice "
             "(Create, then Payment).",
             "The platform reads the ledger at its next load and shows what is owed here."],
            "/app/sales-invoice/new")
AP_EMPTY = ("No supplier balance is recorded in ERPNext yet.",
            ["Record each supplier bill as a Purchase Invoice and submit it.",
             "Record each payment made as a Payment Entry made from the bill "
             "(Create, then Payment)."],
            "/app/purchase-invoice/new")

register(("ar_total", "ar_owing_count", "largest_debt"), Spec(
    what="What customers owe, by the General Ledger: each customer's debits less credits, "
         "counted where the balance is due to us. A customer who has paid in advance owes "
         "nothing and is shown as in credit instead.",
    expected="The ledger and the open invoices should say the same: every payment matched "
             "to the invoice it pays, every credit note set against its invoice. Most of what "
             "is owed should be inside its payment terms.",
    diagnose=_ledger("Customer"), resolution=AR_RESOLVE, prevention=AR_PREVENT,
    order="Largest difference first; within a customer, oldest first.",
    related=AR_RELATED, recs=AR_RECS, empty=AR_EMPTY))

register(("ar_open_invoices", "ar_count"), Spec(
    what="What the unpaid Sales Invoices themselves say is still owed: the outstanding "
         "amount of every submitted invoice with something left to pay. It is the "
         "invoices' view, and is right only where every payment has been matched to them.",
    expected="It should equal what the customer ledger says is owed. Where it is larger, "
             "payments and credits have been recorded but not set against the invoices they "
             "settle, and every reminder or ageing drawn from the invoices overstates the debt.",
    diagnose=_ledger("Customer"), resolution=AR_RESOLVE, prevention=AR_PREVENT,
    order="Largest difference first; within a customer, oldest invoice first.",
    related=AR_RELATED, recs=AR_RECS, empty=AR_EMPTY))

register(("ar_unmatched", "ar_unmatched_count"), Spec(
    what="Money received from customers that was never matched to an invoice: the "
         "unallocated part of each submitted Payment Entry received from a customer.",
    expected="Close to nothing: a payment is matched to its invoice when it is recorded, or "
             "within the month. Only the last few days' receipts should be waiting.",
    diagnose=_ledger("Customer"), resolution=AR_RESOLVE, prevention=AR_PREVENT,
    order="Oldest unmatched payment first, largest customer first.",
    related=AR_RELATED, recs=AR_RECS, empty=AR_EMPTY))

register(("ar_over_90", "ar_inside_90", "ar_undated", "ar_over_90_pct", "score_paid",
          "ar_open_over_90", "ar_open_inside_90"), Spec(
    what="How old what customers owe is. The open invoices are aged by their due date after "
         "the payments not yet matched are set against the oldest first (the standard "
         "assumption when payments are not matched), so money already paid is not counted "
         "as late.",
    expected="Most of what is owed inside its payment terms; little over 90 days (10% or "
             "less is healthy); nothing without a date.",
    owner="Accounts, with Sales for the collection calls",
    diagnose=_ledger("Customer"),
    resolution=("First match the unmatched payments (the ageing is only as right as the "
                "matching): Payment Reconciliation per customer, oldest first.",
                "Then call the customers listed above, largest over-90 balance first, with a "
                "statement of account (Accounts Receivable, filtered to the customer).",
                "Agree a date for each, and record it as a follow-up To-Do on the customer.",
                "Stop new credit to a customer seriously late: set a credit limit on the "
                "Customer so ERPNext stops new orders beyond it."),
    order="Largest over-90 balance first.",
    prevention=(("Set payment terms on every customer (Customer, Payment Terms Template) so "
                 "each invoice carries its due date.", "/app/payment-terms-template",
                 "Open Payment Terms"),
                ("Set a credit limit on each customer (Customer, Credit Limit) so orders stop "
                 "beyond it.", "/app/customer", "Open Customers"),
                ("Send reminders from ERPNext's Dunning for invoices past due.",
                 "/app/dunning", "Open Dunning")) + AR_PREVENT[:1],
    related=AR_RELATED, recs=AR_RECS, empty=AR_EMPTY))

register(("ar_in_credit", "ar_in_credit_count"), Spec(
    what="Customers whose ledger balance is in their favour: they have paid more than they "
         "were billed, or paid in advance.",
    expected="Few, and short-lived: an advance is set against the invoice that follows; an "
             "overpayment is refunded. A customer in credit who still shows open invoices "
             "means the payment was never matched to them.",
    diagnose=_ledger("Customer"), resolution=AR_RESOLVE[1:3], prevention=AR_PREVENT,
    order="Customers who also show open invoices first: allocate, do not refund.",
    related=AR_RELATED, recs=AR_RECS, empty=AR_EMPTY))

# --------------------------------------------------------------------------- payables
register(("ap_total", "ap_owing_count", "ap_unpaid_pct"), Spec(
    what="What we owe suppliers, by the General Ledger: each supplier's credits less "
         "debits, counted where the balance is due to them. A supplier paid in advance is "
         "owed nothing and is shown as paid in advance instead.",
    expected="The ledger and the open bills should say the same: every payment matched to "
             "the bill it pays. A payment run drawn from the bills is right only then.",
    diagnose=_ledger("Supplier"), resolution=AP_RESOLVE, prevention=AP_PREVENT,
    order="Largest difference first; within a supplier, oldest bill first.",
    related=AP_RELATED, recs=AP_RECS, empty=AP_EMPTY))

register(("ap_open_invoices", "ap_count"), Spec(
    what="What the unpaid Purchase Invoices themselves say is still to pay: the outstanding "
         "amount of every submitted supplier bill with something left on it.",
    expected="It should equal what the supplier ledger says we owe. Where it is larger, "
             "payments to suppliers were recorded but not matched to their bills -- and paying "
             "from the bills would pay some of them twice.",
    diagnose=_ledger("Supplier"), resolution=AP_RESOLVE, prevention=AP_PREVENT,
    order="Largest difference first; within a supplier, oldest bill first.",
    related=AP_RELATED, recs=AP_RECS, empty=AP_EMPTY))

register(("ap_unmatched", "ap_unmatched_count"), Spec(
    what="Money paid to suppliers that was never matched to a bill: the unallocated part of "
         "each submitted Payment Entry paid to a supplier.",
    expected="Close to nothing: every payment is made against a bill, or matched within the "
             "month.",
    diagnose=_ledger("Supplier"), resolution=AP_RESOLVE, prevention=AP_PREVENT,
    order="Oldest unmatched payment first, largest supplier first.",
    related=AP_RELATED, recs=AP_RECS, empty=AP_EMPTY))

register(("ap_over_90", "ap_inside_90", "ap_undated"), Spec(
    what="How old what we owe suppliers is: the open bills aged by their due date after the "
         "payments not yet matched are set against the oldest first.",
    expected="Bills paid inside their terms; little over 90 days; nothing without a date.",
    diagnose=_ledger("Supplier"),
    resolution=("First match the unmatched supplier payments (Payment Reconciliation per "
                "supplier): a bill already paid must not be paid again.",
                "Then agree a payment plan with the suppliers listed above, largest over-90 "
                "balance first.",
                "Schedule the payments against the bank balance (Payment Order or Payment "
                "Entry from the bill)."),
    order="Largest over-90 balance first.",
    prevention=AP_PREVENT, related=AP_RELATED, recs=AP_RECS, empty=AP_EMPTY))

register(("ap_in_credit",), Spec(
    what="Suppliers whose ledger balance is in our favour: paid more than they have billed, "
         "or paid in advance.",
    expected="Small, and cleared by the next bill; a supplier in advance who still shows "
             "open bills means the payment was never matched to them.",
    diagnose=_ledger("Supplier"), resolution=AP_RESOLVE[1:3], prevention=AP_PREVENT,
    order="Suppliers who also show open bills first.",
    related=AP_RELATED, recs=AP_RECS, empty=AP_EMPTY))

# --------------------------------------------------------------------------- revenue and margin
REV_EMPTY = ("No submitted Sales Invoice is recorded yet.",
             ["Raise each sale as a Sales Invoice (from the Sales Order or Delivery Note) and "
              "submit it; drafts are not counted."], "/app/sales-invoice/new")
REV_RELATED = ("revenue_invoiced", "revenue_last_month", "revenue_12m", "revenue_best_month",
               "revenue_uncosted", "margin_pct", "invoices_draft_value")

register(("revenue_invoiced", "revenue_last_month", "revenue_12m", "revenue_best_month"), Spec(
    what="Sales invoiced: the net amount (before tax, in the company's currency) of every "
         "line of every submitted Sales Invoice, returns included as negatives. Drafts are "
         "not counted.",
    expected="Each month inside the business's own usual range, and the same month a year "
             "earlier as the fairest comparison. A fall concentrated in a few customers is a "
             "relationship to follow up; a fall across all of them is a market or stock "
             "question.",
    owner="Sales",
    diagnose=_revenue,
    resolution=("Look at the customers whose buying moved most (above) and ask Sales why.",
                "Check the drafts: an invoice saved but never submitted is a sale not counted.",
                "Check the order book for orders delivered but not yet invoiced."),
    order="Largest fall first.",
    prevention=(("Invoice every delivery the day it goes out: Delivery Note, Create, then "
                 "Sales Invoice.", "/app/delivery-note?docstatus=1", "Open Delivery Notes"),
                ("Submit invoices as they are written; review drafts weekly.",
                 "/app/sales-invoice?docstatus=0", "Open draft invoices")),
    related=REV_RELATED, recs=("sales_falling", "customer_concentration", "customers_gone_quiet",
                               "draft_documents", "delivered_unbilled"),
    empty=REV_EMPTY))

register(("revenue_uncosted", "margin_excluded_lines", "revenue_costed"), Spec(
    what="Sales whose cost is not known: invoice lines with no valuation behind them, so "
         "their margin cannot be worked out and is left out of every margin figure.",
    expected="Nothing, apart from services sold with no stock behind them, which carry no "
             "cost by design.",
    owner="Stock Manager, with Accounts",
    diagnose=_revenue,
    resolution=("For each stocked product listed, set its Valuation Rate from the last "
                "purchase price (Stock Reconciliation, keeping the quantity).",
                "For services, untick Maintain Stock on the Item: they then carry no cost by "
                "design, and are not mistaken for missing costs."),
    order="Largest revenue first.",
    prevention=(("Receive every stocked product through a Purchase Receipt or Purchase "
                 "Invoice with Update Stock, so it arrives with its cost.",
                 "/app/purchase-receipt", "Open Purchase Receipts"),
                ("Leave Allow Zero Valuation Rate unticked on invoice lines.",
                 "/app/stock-settings", "Open Stock Settings")),
    related=("margin_pct", "revenue_invoiced", "revenue_costed", "stock_unvalued_lines"),
    recs=("lines_without_cost", "missing_valuations"), empty=REV_EMPTY))

register(("margin_pct", "margin_known_cost"), Spec(
    what="Gross margin: invoiced revenue less the cost of what was sold, on the lines whose "
         "cost is known. Lines with no cost are left out, so the margin is not flattered by "
         "a cost of nothing.",
    expected="Steady inside its own range; nothing sold below cost; little revenue with no "
             "cost recorded.",
    owner="Sales, with Accounts",
    diagnose=_revenue,
    resolution=("Look at the product groups whose margin is lowest (above) and check their "
                "price lists against the latest purchase cost.",
                "Find the lines sold below cost and ask who approved the price."),
    order="Lowest margin on the largest revenue first.",
    prevention=(("Keep selling prices in a Price List updated when costs change.",
                 "/app/item-price", "Open Item Prices"),
                ("Require approval for discounts beyond the price list (Pricing Rule, or a "
                 "workflow on Sales Order).", "/app/pricing-rule", "Open Pricing Rules")),
    related=("revenue_costed", "revenue_uncosted", "margin_excluded_lines", "revenue_invoiced"),
    recs=("margin_shrinking", "sold_below_cost", "discounts_outside_price_list",
          "lines_without_cost"), empty=REV_EMPTY))

# --------------------------------------------------------------------------- stock
register(("stock_value", "stock_lines", "stock_valued_value", "stock_unvalued_lines"), Spec(
    what="Stock on hand at cost: the quantity held in each item and warehouse times its "
         "valuation rate, as ERPNext's stock balance holds it.",
    expected="Every line valued; most of it moving (sold or issued within three months); "
             "held in warehouses it is sold from.",
    owner="Stock Manager",
    diagnose=_stock,
    resolution=("Agree a plan for the largest products not moving (above): a price that "
                "sells them, a customer, a return to the supplier.",
                "Buy no more of them until they move.",
                "Value the lines held with no valuation (Stock Reconciliation), and write off "
                "what has expired or cannot be sold (Stock Entry, Material Issue)."),
    order="Largest value first.",
    prevention=(("Review Stock Ageing monthly.", "/app/query-report/Stock%20Ageing",
                 "Open Stock Ageing"),
                ("Set reorder levels per item so buying follows what sells (Item, "
                 "Auto Re-order).", "/app/item", "Open Items")),
    related=("stock_value", "stock_unvalued_lines", "stock_reserved_qty", "stock_available_qty",
             "stock_worst_shortfall"),
    recs=("stock_not_moving", "near_expiry", "po_for_slow_items", "missing_valuations",
          "reserved_over_available"),
    empty=("No stock is recorded in ERPNext yet.",
           ["Receive stock through a Purchase Receipt, or enter opening stock with a Stock "
            "Reconciliation (quantity and valuation rate per item and warehouse)."],
           "/app/stock-reconciliation/new")))

# --------------------------------------------------------------------------- orders: light
register(("order_book", "order_book_count", "order_book_late", "order_book_on_time",
          "order_book_late_pct", "order_book_late_count"), Spec(
    what="Sales orders confirmed and not yet delivered in full, at their undelivered value.",
    expected="Delivered by the promised date; nothing waiting long for stock.",
    owner="Sales, with the Stock Manager",
    light=True,
    link={"view": "sales", "label": "Open the order cover on Sales and Payments"},
    related=("order_book", "order_book_late", "order_unbilled"),
    recs=("late_orders", "delivered_unbilled")))

# --------------------------------------------------------------------------- cash and bank
register(("bank_cleared_pct",), Spec(
    what="Of the payments made through a bank account, the share matched to the bank "
         "statement in ERPNext (they carry a clearance date).",
    expected="All of them, up to the last statement: the ledger's bank balance is then the "
             "bank's own.",
    diagnose=_bank,
    resolution=("Open Bank Reconciliation Tool, choose the bank account and the statement "
                "dates, and match each statement line to its payment.",
                "Record a payment for any statement line with none (bank charges, interest), "
                "then match it."),
    order="The account with the most unmatched first; the oldest month first.",
    prevention=(("Reconcile each bank account every month, the day the statement arrives.",
                 "/app/bank-reconciliation-tool", "Open Bank Reconciliation Tool"),
                ("Import the statement (Bank Statement Import) rather than typing it.",
                 "/app/bank-statement-import", "Open Bank Statement Import")),
    related=(), recs=("supplier_payments_due",)))
