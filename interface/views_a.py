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
V_SALES=f'''<div class="topbar"><div><h3>Sales and Payments</h3>
<div class="when">7,765 invoices · 1,436 orders · 806 still unpaid</div></div></div>
<div class="kpis six">
{kpi("Last full month","1.55","M GHS","July 2025","up","","rev")}
{kpi("Best month","3.19","M GHS","June 2025","up","","rev")}
{kpi("Owed to us","9.18","M GHS","74% over 3 months late","dn","review","ar")}
{kpi("Unpaid invoices","806","","behind that balance","flat","","ar")}
{kpi("Not despatched","4","","GHS 84,950","dn","","openorders")}
{kpi("Never issued","88","","in nobody's figures","flat","","drafts")}
</div>
<div class="two">
{panel("How sales have moved","<div style='padding:0 0 4px'>"+line_chart(REV_LABELS,[{"data":REV}],h=160,fmt=lambda v:'GHS '+g(v))+"</div>",
 "Monthly, from confirmed orders","rev")}
{panel("Who owes us, and how long it has been",
 stacked([("Under 1 month",0,"var(--ok)"),("1–2 months",0,"var(--med)"),("2–3 months",0,"var(--high)"),("Over 3 months",4592482,"var(--crit)")])
 +thin("Nearly three quarters sits beyond three months. GHS 2.40M across 159 invoices is still inside ninety days, so this is a collection problem rather than a total stop."),
 "Ten largest balances","ar")}
</div>
<div class="two">
{panel("From enquiry to order", funnel([("Enquiries",17,0,"Barely used — 17 in the whole system"),
 ("Opportunities",0,0,"Not used at all"),("Quotations",122,1668921,"Only 122 against 1,436 orders"),
 ("Orders",1436,20363857,"Most orders never start as a quotation")]),
 "Whole history","funnel")}
{panel("Largest balances owed", bar_chart([(c,v,"var(--crit)") for c,v in AR[:8]], fmt=lambda v:g(v)),
 "GHS · the ten largest hold GHS 4,592,482, half of all money owed","ar")}
</div>
{panel("Where orders are held up",
 '<div class="grid six">'+"".join(f'<div class="bk" onclick="explain({SQ}openorders{SQ})"><div class="n">{n}</div><div class="l">{l}</div><div class="v">{v}</div></div>'
 for n,l,v in [("2","Awaiting stock","GHS 18,450"),("1","Awaiting purchase","GHS 65,100"),
 ("4","Awaiting despatch","GHS 84,950"),("4","Awaiting invoice","GHS 84,950"),
 ("0","Awaiting install","—"),("4","Awaiting payment","GHS 13,537")])+'</div>',
 "Click any box for the orders behind it","openorders")}
{panel("Orders taken but not despatched",
 '<table class="dt"><thead><tr><th>Order</th><th>Customer</th><th style="text-align:right">Value GHS</th><th>Despatched</th><th></th></tr></thead><tbody>'
 +"".join(f'<tr><td><span class="lnk" onclick="openDrawer({SQ}{d}{SQ})">{n}</span></td><td>{c}</td><td class="num">{g(v)}</td>'
          f'<td style="color:var(--dim)">None of it</td><td><button class="btn" onclick="ask2({SQ}Why is the {s} order still open?{SQ})">Ask why</button></td></tr>'
 for n,c,v,d,s in [("SAL-ORD-2025-00910","EJURA MUNICIPAL HOSPITAL",65100,"ejura","Ejura"),
  ("SAL-ORD-2025-00909","ROSSY'S SUPPLY",16700,"order","Rossy's"),
  ("SAL-ORD-2025-00906-1","ST MARYS HOSPITAL (DROBO)",1750,"order","St Marys"),
  ("SAL-ORD-2025-00907","LILIAN ACHIAA",1400,"order","Lilian Achiaa")])+'</tbody></table>')}
{panel("Discounts and price changes outside policy", thin("<b>Nothing to show from this demo extract.</b> The live system records discounts on each order; this copy has none above the threshold. The panel stays here so the shape of the screen is the shape of the finished product."),"","discount")}'''
