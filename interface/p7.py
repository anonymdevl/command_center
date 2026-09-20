# -*- coding: utf-8 -*-
exec(_src('p6.py'))
import json

# ---- simple placeholder views for remaining domains ----
def simple(title, when, body):
    return f'<div class="topbar"><div><h3>{title}</h3><div class="when">{when}</div></div></div>{body}'

V_PROC=simple("Buying and suppliers","299 purchase orders",
 f'''<div class="kpis" style="grid-template-columns:repeat(4,1fr)">
{kpi("Purchase orders","299","")}{kpi("Awaiting approval","—","","not yet configured","flat")}
{kpi("Late deliveries","—","","supplier dates not set","flat")}{kpi("Order-to-invoice checks","—","","not yet switched on","flat")}</div>
<div class="warn"><b>This area has real data but little structure.</b> Supplier lead times and expected
delivery dates are largely unset, so "late" cannot yet be measured. Approved-supplier status is not
recorded anywhere. Both are quick to fix and both are needed before this screen means much.</div>''')

V_INV=simple("Stock and warehouses","GHS 3,769,970 held across six locations",
 f'''<div class="kpis" style="grid-template-columns:repeat(4,1fr)">
{kpi("Stock we hold","3.77","M GHS","a third not in any warehouse","dn")}
{kpi("Off warehouse","1.18","M GHS","31% of everything","dn","review","openDrawer('recon')")}
{kpi("Reserved, unavail.","491","products","no stock behind the promise","dn","","openDrawer('stock')")}
{kpi("Reserved lines","771","")}</div>
<div class="sect">Where the value sits</div>
<table class="dt"><thead><tr><th>Location</th><th style="text-align:right">Roughly</th><th>Note</th></tr></thead><tbody>
<tr><td>Stock adjustment account</td><td class="num" style="color:var(--crit)">1,175,920</td>
<td style="color:var(--high)">Not a warehouse — nothing here can be sold</td></tr>
<tr><td>Kumasi Warehouse and Store</td><td class="num">—</td><td style="color:var(--mut)">Trading stock</td></tr>
<tr><td>Central Warehouse and Store</td><td class="num">—</td><td style="color:var(--mut)">Trading stock</td></tr>
<tr><td>Accra Warehouse</td><td class="num">—</td><td style="color:var(--mut)">Trading stock</td></tr>
</tbody></table>
<div class="sect" style="margin-top:20px">Worst over-promises</div>
<table class="dt"><thead><tr><th>Product</th><th>Where</th><th style="text-align:right">Reserved</th>
<th style="text-align:right">Actually held</th><th style="text-align:right">Short by</th></tr></thead><tbody>
<tr><td>Syringe &amp; needle, 5ml</td><td>Central Warehouse</td><td class="num">40,080</td>
<td class="num">139</td><td class="num" style="color:var(--crit)">39,941</td></tr>
<tr><td>Syringe &amp; needle, 10ml</td><td>Central Warehouse</td><td class="num">16,021</td>
<td class="num">0</td><td class="num" style="color:var(--crit)">16,021</td></tr>
<tr><td>Infusion sets</td><td>Central Warehouse</td><td class="num">8,000</td>
<td class="num">0</td><td class="num" style="color:var(--crit)">8,000</td></tr>
<tr><td>Examination gloves</td><td>Central Store</td><td class="num">2,844</td>
<td class="num">93</td><td class="num" style="color:var(--crit)">2,751</td></tr>
</tbody></table>''')

V_FIN=simple("Money in and out","Full ledger available",
 f'''<div class="kpis" style="grid-template-columns:repeat(4,1fr)">
{kpi("Owed to us","9.18","M GHS","74% over 3 months late","dn")}
{kpi("Unpaid invoices","806","","GHS 9.18M between them","dn")}
{kpi("Never issued","88","","not in any total","flat")}
{kpi("Bank checks","—","","status not confirmed","flat","review")}</div>
<div class="warn">The ledger is complete and usable. What is not yet known is whether the bank accounts
have been checked against it recently — that is the first thing to establish, because every cash figure
on this platform depends on it.</div>''')

V_HR=simple("People","35 employees · names and pay hidden by default",
 f'''<div class="kpis" style="grid-template-columns:repeat(4,1fr)">
{kpi("Employees","35","")}{kpi("Left recently","6","","from the exit paperwork on file","flat")}
{kpi("Payroll","—","","shown as status only","flat")}{kpi("Certs expiring","—","","not yet recorded","flat")}</div>
<div class="warn"><b>This platform never calculates or changes pay.</b> It shows whether payroll has been
run and whether anything moved unusually. Individual salaries and personal records stay hidden unless
you hold the HR role, and the assistant cannot read them at all on your behalf.</div>''')

V_IT=simple("Systems and access","Measured by this platform, not by ERPNext",
 f'''<div class="kpis" style="grid-template-columns:repeat(4,1fr)">
{kpi("Availability","99.9","%","last 30 days","up")}
{kpi("Last refreshed","06:58","","this morning","flat")}
{kpi("Failed syncs","0","","last 24 hours","up")}
{kpi("With access","7","","management only","flat")}</div>
<div class="warn">ERPNext keeps no record of uptime, backups or system health, so <b>this platform is the
record for those</b>. Everything on this screen is measured by us, about us.</div>''')

V_AUD=simple("Internal audit","Arrives with the platform",
 '''<div class="denied"><div class="big">◷</div><h4>Nothing to show yet</h4>
<p>ERPNext has nowhere to record an audit finding or a corrective action, so there is no history to
display. This becomes live once the platform is installed, and the problems already visible on Control
Health are the obvious first entries.</p>
<div class="acts" style="justify-content:center;margin-top:16px">
<button class="btn pri" onclick="go('health')">See what would be raised first</button></div></div>''')

# ---------- DRAWERS ----------
DRAWERS={
 "ejura":{"kind":"Sales order","name":"SAL-ORD-2025-00910","rows":[
   ("Customer","EJURA MUNICIPAL HOSPITAL"),("Placed","19 August 2025"),("Value","GHS 65,100.00"),
   ("Despatched","None of it"),("Invoiced","None of it"),("Confirmed","Yes — a confirmed order, not a draft")],
  "chain":[("Order placed","19 Aug 2025",1),("Goods despatched","never happened — this is the hold-up",0),
   ("Invoice raised","cannot happen until despatch",0),("Payment received","cannot happen until invoiced",0)],
  "prov":[("Held in","ERPNext, as a sales order"),("Reference","SAL-ORD-2025-00910"),
   ("Confirmed","Yes — a confirmed order, not a draft"),("Last changed","19 Aug 2025 at 14:22, in ERPNext"),
   ("Read by us","Today at 06:58")]},
 "ubuntu":{"kind":"Customer — both sides","name":"UBUNTU ORTHOPAEDIC & SPINE HOSPITAL","rows":[
   ("They owe us","GHS 636,675 — all more than three months late"),
   ("We owe them","Three installations, promised for 28 Feb 2025"),
   ("C-arm installation","Not started · 19 months late"),
   ("Theatre setup","Not started · 19 months late"),
   ("X-ray installation","Not started · 19 months late"),
   ("Anyone assigned","Nobody, on any of the three")],
  "chain":[("Equipment sold and invoiced","2024–25",1),("Installations promised","by 28 Feb 2025",1),
   ("Installations carried out","never happened",0),("Payment received","nothing against this balance",0)],
  "prov":[("Held in","ERPNext — customer account and three projects"),
   ("References","PROJ-0028, PROJ-0029, PROJ-0030"),("Confirmed","Yes — all three are live projects"),
   ("Last changed","Feb 2025, in ERPNext"),("Read by us","Today at 06:58")]},
 "ar":{"kind":"Money owed to us","name":"All unpaid invoices","rows":[
   ("Total owed","GHS 9,177,569"),("Under one month","GHS 499,078 · 47 invoices"),
   ("One to two months","GHS 1,511,117 · 61 invoices"),
   ("Two to three months","GHS 390,231 · 51 invoices"),
   ("Over three months","GHS 6,777,143 · 647 invoices — 74%"),
   ("Ten largest customers","GHS 4,592,482 — half the total"),
   ("Unpaid invoices behind this","806"),
   ("Ageing measured as at","19 Aug 2025, the last date the data covers")],
  "chain":[("Goods sold and delivered","2024–25",1),("Invoices raised","2024–25",1),
   ("Payment terms passed","for 74% of the money",1),("Payment received","not against these balances",0)],
  "prov":[("Held in","ERPNext — customer account balances"),("Covers","806 unpaid invoices, all customers"),
   ("Confirmed","Yes — confirmed invoices only, drafts excluded"),
   ("Last changed","19 Aug 2025, in ERPNext"),("Read by us","Today at 06:58")]},
 "stock":{"kind":"Stock position","name":"Reserved but unavailable","rows":[
   ("Products affected","491"),("Products with any reservation","771"),
   ("Worst line","Syringe & needle 5ml — 40,080 promised, 139 held"),
   ("Also","10ml syringes: 16,021 promised, none held"),("Also","Infusion sets: 8,000 promised, none held"),
   ("Locations","Central, Kumasi and Accra")],
  "chain":[("Orders taken and stock promised","ongoing",1),("Stock received to cover them","did not happen",0),
   ("Goods picked","will fail when attempted",0)],
  "prov":[("Held in","ERPNext — stock position per product and location"),
   ("Covers","2,375 product-location records"),("Confirmed","Yes — live stock figures"),
   ("Last changed","19 Aug 2025, in ERPNext"),("Read by us","Today at 06:58")]},
 "recon":{"kind":"Stock adjustment account","name":"Equipment held outside every warehouse","rows":[
   ("Value","GHS 1,175,920 — and that is only the top 100 of 207 lines"),
   ("Share of all stock","About a third"),
   ("Largest items","Two new haematology analysers — GHS 81,500 and 78,800"),
   ("Also","Anaesthesia machine GHS 55,000 · ultrasound GHS 54,120"),
   ("Also","15 hospital beds · 946 crutches"),("Can it be sold from here","No")],
  "chain":[("Stock counted and adjusted","various",1),("Adjustment account used as a store","ongoing",1),
   ("Equipment moved to a sellable location","has not happened",0)],
  "prov":[("Held in","ERPNext — stock position, adjustment location"),("Covers","207 product lines with value"),
   ("Confirmed","Yes — live stock figures"),("Last changed","19 Aug 2025, in ERPNext"),
   ("Read by us","Today at 06:58")]},
 "a1":{"kind":"Invoice","name":"20250819090603609383","rows":[
   ("Customer","A1 MEDICALSUPPLIES"),("Raised","19 August 2025"),("Value","GHS 11,000.00"),
   ("Still outstanding","GHS 11,000.00 — all of it"),("Order behind it","SAL-ORD-2025-00905, fully despatched"),
   ("Confirmed","Yes — a confirmed invoice")],
  "chain":[("Order placed","18 Aug 2025",1),("Goods despatched","in full",1),("Invoice raised","19 Aug 2025",1),
   ("Payment received","nothing received",0)],
  "prov":[("Held in","ERPNext, as a sales invoice"),("Reference","20250819090603609383"),
   ("Confirmed","Yes — a confirmed invoice, not a draft"),("Last changed","19 Aug 2025, in ERPNext"),
   ("Read by us","Today at 06:58")]},
 "order":{"kind":"Sales order","name":"Open order","rows":[
   ("Status","Taken, not yet despatched"),("Confirmed","Yes")],
  "chain":[("Order placed","2025",1),("Goods despatched","not yet",0)],
  "prov":[("Held in","ERPNext, as a sales order"),("Confirmed","Yes"),("Read by us","Today at 06:58")]},
}
