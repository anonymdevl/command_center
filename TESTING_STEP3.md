# Testing step 3 on Biomed

After `git pull` and `bench migrate`, open a console:

```bash
bench --site biomed.ultrasoft-systems.com console
```

## 1. Load the facts

```python
import frappe
frappe.set_user("Administrator")

from command_center.api.ingest import run
run(full=True)
```

Expect something like:

```
{'as_of': '2025-08-19',
 'loaded': [{'fact': 'fact_sales_invoice', 'business': 'gigmann_medical_supplies_ltd', 'rows': ...},
            {'fact': 'fact_sales_invoice_line', ...},
            {'fact': 'fact_payment_allocation', ...}]}
```

**`as_of` must read 2025-08-19, not today.** That date is the latest posting date the
data actually contains. If it says 2026-09-20, `resolve_as_of` is broken and every
ageing figure will be wrong in the same way the first reading of this data was wrong.

## 2. Reconcile — this is the real test

```python
from command_center.api.ingest import reconcile
reconcile()
```

Every check must come back `reconciled: True`. The one that matters most:

| Check | Expected |
| --- | --- |
| Outstanding receivables | **9,177,568.91** |
| Unpaid invoice count | **806** |

If outstanding comes back near 4,592,482 something is filtering to the top ten
customers. If it comes back far larger than 9.18M, the document-level outstanding has
leaked onto item lines and is being summed per line — the exact mistake the
three-grain split exists to prevent.

## 3. Check the ageing distribution

```python
from command_center.api.facts import query
query(fact="fact_sales_invoice",
      measures=["outstanding_amount"],
      group_by=["ageing_bucket"],
      filters={"outstanding_amount": [">", 0], "src_docstatus": 1})
```

Should reproduce, as at 19 Aug 2025:

| bucket | GHS | invoices |
| --- | --- | --- |
| 0-30 | 499,077.50 | 47 |
| 31-60 | 1,511,117.10 | 61 |
| 61-90 | 390,231.39 | 51 |
| 90+ | 6,777,142.92 | 647 |

If everything lands in `90+`, the as-of date is today rather than the data's horizon.

## 4. Drill down — prove lineage works

```python
from command_center.api.facts import lineage
lineage(fact="fact_sales_invoice",
        filters={"ageing_bucket": "90+"}, limit=5)
```

Each row returns `src_doctype` and `src_name`, so any figure can name the documents
behind it. That is the drill-down contract, and it is a property of the schema rather
than something each screen implements.

## 5. Margin, and honesty about missing cost

```python
query(fact="fact_sales_invoice_line",
      measures=["base_net_amount", "base_cost_amount", "base_margin_amount"],
      group_by=["item_group"])
```

Then check how much of the revenue has no cost behind it:

```python
query(fact="fact_sales_invoice_line",
      measures=["base_net_amount"], group_by=["has_cost"])
```

Any margin KPI must exclude `has_cost = 0`. Treating a missing valuation as zero cost
reports it as pure profit, which is worse than reporting nothing.

## 6. Ingest state

```python
from command_center.api.ingest import status
status()
```

Shows the watermark and as-of date per fact. A second `run()` without `full=True`
should load few or no rows — that proves the incremental path works.

## 7. The controller fallback

Only testable while a broken app is installed. If posawesome is still there:

```python
from command_center.connectors.registry import local_connector
d = local_connector().get_doc("Sales Invoice", "20250819090603609383")
d.get("_controller_unavailable")   # True if the fallback was used
```

With posawesome removed this returns `None` and the normal path is used, which is the
correct outcome.
