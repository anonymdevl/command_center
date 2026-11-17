# -*- coding: utf-8 -*-
exec(_src('views_a.py'))

# ============ PROCUREMENT ============
V_PROC=f'''<div class="topbar"><div><h3>Buying and Suppliers</h3>
<div class="when"></div></div></div>
<div class="kpis six">
{kpi("Purchase Orders","—","","","flat","","po")}
{kpi("Top 14 Purchase Orders","—","","","flat","","spend")}
{kpi("Top Supplier","—","","","flat","","supp")}
{kpi("Top 2 Suppliers","—","","","flat","","supp")}
{kpi("Longest Wait","—","","","flat","","lead")}
{kpi("No Required By Date","—","","","flat","","nodate")}
</div>
<div class="two">
{panel("Purchase Orders by Supplier", bars0(),
 "14 largest Purchase Orders","supp")}
{panel("Supplier Lead Time", bars0(),
 "Average days, Transaction Date to Required By","lead")}
</div>
{warn0()}
<div class="two">
{panel("Open Purchase Orders",
 dtable(["Order","Supplier",("Value$",True),"Status"])
 +thin("Which of the 14 largest are still To Receive or To Bill."))}
{panel("Purchase Invoice Checks",
 thin("<b>Supplier invoices still to be paid, checked against the order and the goods received.</b> "
 "Each unpaid Purchase Invoice should rest on a purchase order and a Purchase Receipt; any that does not is listed here before it is paid."))}
</div>
<div class="two">
{panel("Supplier Performance", thin("<b>Delivered on time, and goods turned away, per supplier.</b> Each Purchase Receipt is compared with the date its purchase order asked for, so a supplier that is always late shows up before the next order is placed."))}
{panel("Unreconciled Supplier Payments", thin("<b>Supplier payments with an Unallocated Amount, by supplier.</b> Advances before goods arrive are normal for an importer."))}
</div>
{warn0()}
{cover0()}'''

# ============ INVENTORY ============
# Stock Balance and Stock Movements are record tables drawn by frontend/src/legacy/stock.js
# from api/stock.py (search, warehouse, dates, Excel). .ppanel, not .panel, so the panels'
# renderer (legacy/panels.js) leaves them alone. Heading only: no line under it. Each is a
# tab of its own (data-tab: tidy.py tabify), after Overview and Detail.
def stock_section(key, title):
    return (f'<div class="ppanel" data-tab="{title}" data-sk="{key}"><div class="ph"><div>'
            f'<b>{title}</b></div></div><div class="pp-body"></div></div>')

V_INV=f'''<div class="topbar"><div><h3>Stock &amp; Warehouses</h3>
<div class="when"></div></div></div>
<div class="kpis six">
{kpi("Stock Value","—","","","flat","","stockval")}
{kpi("Off warehouse","—","","","flat","","recon")}
{kpi("Reserved Qty","—","","","flat","","over")}
{kpi("Worst Shortfall","—","","","flat","","worst")}
{kpi("Lines with Reserved Qty","—","","","flat","","reserved")}
{kpi("Batches Near Expiry","—","","","flat","","expiry")}
</div>
<div class="two">
{panel("Stock Value by Warehouse", bars0(),
 "","stockval")}
{panel("Reserved against what is available",
 dtable(["Item","Where",("Reserved Qty",True),("Available",True),("Short By",True)]),"Where the promise exceeds the stock","over")}
</div>
{warn0()}
{cover0()}
<div class="two">
{panel("Stock Ageing, No Movement 90 Days", thin("<b>Products holding stock that have not moved in ninety days.</b> Every product is aged by its last stock movement, with the value still sitting in stock."))}
{panel("Batch Expiry", thin("<b>Batches that expire soon, or already have.</b> Batch expiry dates drive near-expiry warnings and first-expiry-first-out picking. For a medical supplier this is the panel that matters most."))}
</div>
{stock_section("balance", "Stock Balance")}
{stock_section("movements", "Stock Movements")}'''
