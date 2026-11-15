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
    h=f'<div class="ph{" clickable" if explain else ""}"{od}><div><b>{title}</b>{f"<span>{sub}</span>" if sub else ""}</div>{"<span class=pmore>what is this? →</span>" if explain else ""}</div>'
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

V_SALES=f'''<div class="topbar"><div><h3>Sales and Payments</h3>
<div class="when">Invoices, orders and what is still unpaid</div></div></div>
<div class="kpis six">
{kpi("Last full month","—","","","flat","","rev")}
{kpi("Best month","—","","","flat","","rev")}
{kpi("Owed to us","—","","","flat","","ar")}
{kpi("Unpaid invoices","—","","","flat","","ar")}
{kpi("Not despatched","—","","","flat","","openorders")}
{kpi("Never issued","—","","","flat","","drafts")}
</div>
<div class="two">
{panel("How sales have moved","<div style='padding:0 0 4px'>"+trend0(160)+"</div>",
 "Monthly, from confirmed orders","rev")}
{panel("Who owes us, and how long it has been",
 stacked([("Under 1 month",0,"var(--ok)"),("1–2 months",0,"var(--med)"),("2–3 months",0,"var(--high)"),("Over 3 months",0,"var(--crit)")])
 +thin("How the money owed by the ten largest balances is spread by age, after payments not yet matched are set against the oldest invoices."),
 "Ten largest balances","ar")}
</div>
<div class="two">
{panel("From enquiry to order", funnel([("Enquiries",0,0,""),
 ("Opportunities",0,0,""),("Quotations",0,0,""),
 ("Orders",0,0,"")]),
 "Whole history","funnel")}
{panel("Largest balances owed", bars0(),
 "The ten largest balances, by the ledger","ar")}
</div>
{warn0()}
{warn0()}
{panel("What each customer really owes",
 '<div class="dt-scroll">'+dtable(["Customer",("On Open Invoices$",True),("Ledger Balance$",True),("Difference$",True),"Why",
 ("Not Yet Due",True),("1–30 Days",True),("31–60 Days",True),("61–90 Days",True),("Over 90 Days",True)])+'</div>',
 "By the ledger, beside what the open invoices say","ledger")}
{panel("Where orders are held up",
 '<div class="grid six">'+"".join(tile0(l,"openorders") for l in ["Awaiting stock","Awaiting purchase",
 "Awaiting despatch","Awaiting invoice","Awaiting install","Awaiting payment"])+'</div>',
 "Click any box for the orders behind it","openorders")}
{panel("Orders taken but not despatched",
 dtable(["Order","Customer",("Value$",True),"Despatched",""]))}
{panel("Discounts and price changes outside policy", thin("<b>Invoice lines sold below their price-list price with no pricing rule behind them.</b> A discount given by a pricing rule is policy; one typed in by hand is not."),"","discount")}'''
