# -*- coding: utf-8 -*-
import sys; sys.path.insert(0,IFACE)
exec(_src('chart.py'))
exec(_src('data.py'))
# g() is defined once, in p2.py. Defining it here shadowed that copy and the two drifted apart.

# _money() is defined once, in p2.py. Defining it here shadowed that copy and the two drifted apart.

# kpi() is defined once, in p2.py. It was redefined here and the two
# disagreed by one class, which is why cards looked different between
# views. Do not reintroduce it.

def panel(title, body, sub="", explain=""):
    od=f''' onclick="explain('{explain}')"''' if explain else ''
    h=f'<div class="ph{" clickable" if explain else ""}"{od}><div><b>{title}</b>{f"<span>{sub}</span>" if sub else ""}</div>{"<span class=pmore>What Is This? →</span>" if explain else ""}</div>'
    return f'<div class="panel">{h}{body}</div>'

def thin(t): return f'<div class="thin">{t}</div>'

# _afig() is defined once, in p2.py. Defining it here shadowed that copy and the two drifted apart.

# alert() is defined once, in p2.py. Defining it here shadowed that copy and the two drifted apart.

# ============ SALES ============
# Production markup: every figure, name, date and currency on this screen is filled from
# the selected business at runtime (legacy/hydrate.js for the cards and tiles,
# api/panels.py + legacy/panels.js for the panels, findings and the line under the
# heading). Nothing here is a sample: the marks are empty until the business answers.
def dtable(heads):
    """An empty designed table: its headings only. ("Value", True) is a number column,
    and a heading ending in "$" carries the business's currency after it."""
    th = []
    for h in heads:
        label, num = (h, False) if isinstance(h, str) else h
        cur = label.endswith("$")
        label = label.rstrip("$").strip()
        style = ' style="text-align:right"' if num else ""
        th.append(f'<th{style}>{label}{" <span data-cur></span>" if cur else ""}</th>')
    return f'<table class="dt"><thead><tr>{"".join(th)}</tr></thead><tbody></tbody></table>'

def bars0(): return '<div class="bars"></div>'

def trend0(h=160):
    return line_chart([""]*12, [{"data": [0]*12}], h=h, fmt=lambda v: "")

def tile0(label, key):
    return (f'<div class="bk" onclick="explain({SQ}{key}{SQ})"><div class="n">—</div>'
            f'<div class="l">{label}</div><div class="v">—</div></div>')

def warn0(): return '<div class="warn" hidden></div>'

def cover0():
    """Promised Orders — Cover (api/coverage.py, legacy/cover.js): every open order line and
    what covers it. Empty until the business answers; the same panel on Sales, Buying and
    Stock."""
    return panel("Promised Orders — Cover", '<div class="cover"></div>',
                 "Every open Sales Order line, and what covers it", "cover")

V_SALES=f'''<div class="topbar"><div><h3>Sales and Payments</h3>
<div class="when"></div></div></div>
<div class="kpis six">
{kpi("Invoiced, Last Full Month","—","","","flat","","rev")}
{kpi("Best Month Invoiced","—","","","flat","","rev")}
{kpi("Accounts Receivable","—","","","flat","","ar")}
{kpi("Unpaid Sales Invoices","—","","","flat","","ar")}
{kpi("To Deliver","—","","","flat","","openorders")}
{kpi("Draft Sales Invoices","—","","","flat","","drafts")}
</div>
<div class="two">
{panel("Sales Order Trends","<div style='padding:0 0 4px'>"+trend0(160)+"</div>",
 "Monthly, submitted Sales Orders","rev")}
{panel("Accounts Receivable Ageing",
 stacked([("0-30 Days",0,"var(--ok)"),("31-60 Days",0,"var(--med)"),("61-90 Days",0,"var(--high)"),("Over 90 Days",0,"var(--crit)")])
 +thin("Customer Ledger Balance by age, after unreconciled payments are set against the oldest invoices."),
 "Top 10 by Customer Ledger Balance","ar")}
</div>
<div class="two">
{panel("Sales Funnel", funnel([("Leads",0,0,""),
 ("Opportunities",0,0,""),("Quotations",0,0,""),
 ("Orders",0,0,"")]),
 "All Time","funnel")}
{panel("Largest Customer Ledger Balances", bars0(),
 "Top 10","ar")}
</div>
{warn0()}
{warn0()}
{panel("Customer Ledger Balance vs Invoice Outstanding",
 '<div class="dt-scroll">'+dtable(["Customer",("Sales Invoice Outstanding$",True),("Customer Ledger Balance$",True),("Difference$",True),"Why",
 ("Not Yet Due",True),("1–30 Days",True),("31–60 Days",True),("61–90 Days",True),("Over 90 Days",True)])+'</div>',
 "Customer Ledger Balance beside Sales Invoice Outstanding","ledger")}
{panel("Where Sales Orders Are Held Up",
 '<div class="grid six">'+"".join(tile0(l,"openorders") for l in ["Awaiting Stock","Awaiting Purchase Order",
 "Awaiting Delivery Note","Awaiting Sales Invoice","Awaiting Installation","Awaiting Payment"])+'</div>',
 "","openorders")}
{cover0()}
{panel("Sales Orders To Deliver",
 dtable(["Order","Customer",("Value$",True),"Delivered",""]))}
{panel("Discounts Outside Pricing Rules", thin("<b>Sales Invoice lines below Price List Rate with no Pricing Rule.</b>"),"","discount")}'''
