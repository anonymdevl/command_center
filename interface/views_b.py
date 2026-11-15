# -*- coding: utf-8 -*-
exec(_src('views_a.py'))

# ============ PROCUREMENT ============
V_PROC=f'''<div class="topbar"><div><h3>Buying and Suppliers</h3>
<div class="when">Purchase orders and the suppliers they go to</div></div></div>
<div class="kpis six">
{kpi("Purchase orders","—","","","flat","","po")}
{kpi("Spend, top 14","—","","","flat","","spend")}
{kpi("Top supplier","—","","","flat","","supp")}
{kpi("Top 2 suppliers","—","","","flat","","supp")}
{kpi("Longest wait","—","","","flat","","lead")}
{kpi("No due date","—","","","flat","","nodate")}
</div>
<div class="two">
{panel("Where the money goes", bars0(),
 "Fourteen largest orders","supp")}
{panel("How long each supplier takes", bars0(),
 "Average days from order to promised delivery · click for every order","lead")}
</div>
{warn0()}
<div class="two">
{panel("Orders still open",
 dtable(["Order","Supplier",("Value$",True),"Where it is"])
 +thin("Which of the fourteen largest orders are still to be received or billed."))}
{panel("Checks before we pay",
 thin("<b>Supplier invoices still to be paid, checked against the order and the goods received.</b> "
 "Each unpaid supplier invoice should rest on a purchase order and a goods receipt; any that does not is listed here before it is paid."))}
</div>
<div class="two">
{panel("Supplier performance", thin("<b>Delivered on time, and goods turned away, per supplier.</b> Each goods receipt is compared with the date its purchase order asked for, so a supplier that is always late shows up before the next order is placed."))}
{panel("Money paid to suppliers in advance", thin("<b>Payments to suppliers not yet matched to an invoice.</b> Advances paid before the goods arrive are a normal exposure for an importer; this is how much is out there, and with whom."))}
</div>'''

# ============ INVENTORY ============
V_INV=f'''<div class="topbar"><div><h3>Stock &amp; Warehouses</h3>
<div class="when">What is held, where, and what is promised against it</div></div></div>
<div class="kpis six">
{kpi("Stock we hold","—","","","flat","","stockval")}
{kpi("Off warehouse","—","","","flat","","recon")}
{kpi("Reserved, unavail.","—","","","flat","","over")}
{kpi("Worst shortfall","—","","","flat","","worst")}
{kpi("Lines promised","—","","","flat","","reserved")}
{kpi("Near expiry","—","","","flat","","expiry")}
</div>
<div class="two">
{panel("Where the value sits", bars0(),
 "By location","stockval")}
{panel("Reserved against what is available",
 dtable(["Product","Where",("Reserved",True),("Available",True),("Short by",True)]),"Where the promise exceeds the stock","over")}
</div>
{warn0()}
<div class="two">
{panel("Stock that is not moving", thin("<b>Products holding stock that have not moved in ninety days.</b> Every product is aged by its last stock movement, with the value still sitting on the shelf."))}
{panel("Expiry", thin("<b>Batches that expire soon, or already have.</b> Batch expiry dates drive near-expiry warnings and first-expiry-first-out picking. For a medical supplier this is the panel that matters most."))}
</div>'''
