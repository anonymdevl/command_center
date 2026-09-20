# -*- coding: utf-8 -*-
exec(_src('views_a.py'))

# ============ PROCUREMENT ============
SUPP_AVG=[("CYNSEL INNOVATION",73,"var(--crit)","5 orders · longest 184 days"),
 ("QINGDAO HIGHTOP BIOTECH",84,"var(--crit)","1 order"),
 ("SICHUAN M.K.R CO LTD",44,"var(--high)","8 orders · 2 with no date set")]
lead_rows=[(nm,d,c,note) for nm,d,c,note in SUPP_AVG]
V_PROC=f'''<div class="topbar"><div><h3>Buying and suppliers</h3>
<div class="when">299 purchase orders · GHS 8.4M across the fourteen largest alone</div></div></div>
<div class="kpis six">
{kpi("Purchase orders","299","","all time","flat","","po")}
{kpi("Spend, top 14","8.43","M GHS","2 suppliers are 95% of it","flat","","spend")}
{kpi("Top supplier","57","%","one supplier","dn","risk","supp")}
{kpi("Top 2 suppliers","95","%","of that spend","dn","risk","supp")}
{kpi("Longest wait","184","days","CYNSEL · ordered Dec, due June","dn","","lead")}
{kpi("No due date","2","","GHS 977,077","dn","review","nodate")}
</div>
<div class="two">
{panel("Where the money goes", bar_chart([(s,v,"var(--crit)" if i==0 else "var(--accent)",f"{n} orders") for i,(s,v,n,note) in enumerate(SUPP)], fmt=lambda v:g(v)),
 "GHS, fourteen largest orders","supp")}
{panel("How long each supplier takes", bar_chart(lead_rows, fmt=lambda v:str(v)+" days"),
 "Average days from order to promised delivery · click for every order","lead")}
</div>
<div class="warn"><b>Almost everything comes from two suppliers.</b> SICHUAN M.K.R and CYNSEL INNOVATION
between them account for about 95% of the largest orders, and both ship from abroad with lead times of
one to six months. If either stops supplying, or a shipment is held at the port, there is no second source
ready. That is worth a board conversation before it becomes one.</div>
<div class="two">
{panel("Orders still open",
 '<table class="dt"><thead><tr><th>Order</th><th>Supplier</th><th style="text-align:right">Value GHS</th><th>Where it is</th></tr></thead><tbody>'
 +"".join(f'<tr><td><span class="lnk">{n.replace("PUR-ORD-","")}</span></td><td>{s}</td><td class="num">{g(v)}</td>'
          f'<td><span class="tag {"t-wt" if "Still" in st else "t-ok"}">{st}</span></td></tr>'
   for n,s,v,d,st in PO_LEAD if "Still" in st)
 +'</tbody></table>'+thin("Only two of the fourteen largest are still open. The rest are complete."))}
{panel("Checks before we pay",
 thin("<b>Not switched on in this demo extract.</b> The finished platform compares every supplier invoice "
 "against the order and the goods actually received, and holds payment where the three disagree. "
 "The records needed for it are present; the comparison has not been configured here."))}
</div>
<div class="two">
{panel("Supplier performance", thin("<b>Not scored in this demo extract.</b> On-time delivery, quality failures and repeat problems per supplier need delivery dates recorded against receipts. Two of the fourteen largest orders have no promised date at all, so the measure would mislead."))}
{panel("Money paid to suppliers in advance", thin("<b>Nothing to show from this demo extract.</b> Advances paid but not yet matched to goods are a normal exposure for an importer. The panel is here because the finished screen carries it."))}
</div>'''

# ============ INVENTORY ============
V_INV=f'''<div class="topbar"><div><h3>Stock and warehouses</h3>
<div class="when">GHS 3,769,970 held · 2,375 product-location records across six places</div></div></div>
<div class="kpis six">
{kpi("Stock we hold","3.77","M GHS","a third not in any warehouse","dn","","stockval")}
{kpi("Off warehouse","1.18","M GHS","31% of everything","dn","review","recon")}
{kpi("Reserved, unavail.","491","products","no stock behind the promise","dn","","over")}
{kpi("Worst shortfall","39,941","short","5ml syringes","dn","","worst")}
{kpi("Lines promised","771","","only 36% covered","dn","","reserved")}
{kpi("Near expiry","—","","not recorded here","flat","","expiry")}
</div>
<div class="two">
{panel("Where the value sits", bar_chart([(w,v,c,n) for w,v,c,n in WH], fmt=lambda v:g(v)),
 "GHS by location","stockval")}
{panel("Reserved against what is available",
 '<table class="dt"><thead><tr><th>Product</th><th>Where</th><th style="text-align:right">Reserved</th>'
 '<th style="text-align:right">Available</th><th style="text-align:right">Short by</th></tr></thead><tbody>'
 +"".join(f'<tr><td>{p}</td><td style="color:var(--mut)">{w}</td><td class="num">{g(r)}</td>'
          f'<td class="num">{g(a)}</td><td class="num" style="color:var(--crit)">{g(r-a)}</td></tr>'
   for p,w,r,a in STOCK_OVER)+'</tbody></table>',"Worst eight of 491","over")}
</div>
<div class="warn"><b>Almost a third of everything the company owns sits in a stock adjustment account
rather than a warehouse</b> — GHS 1.18M, including two brand-new haematology analysers, an anaesthesia
machine, fifteen hospital beds and 946 crutches. Nothing can be sold from there. Somebody needs to say
where that equipment physically is.</div>
<div class="two">
{panel("Stock that is not moving", thin("<b>Not measured in this demo extract.</b> The finished screen ages every product by its last movement and flags what has not moved in 90 days, with its value."))}
{panel("Expiry", thin("<b>Not recorded in this demo extract.</b> Batch expiry dates drive near-expiry warnings and first-expiry-first-out picking. For a medical supplier this is the panel that matters most, and it needs expiry dates captured at goods-in."))}
</div>'''
