# -*- coding: utf-8 -*-
exec(_src('views_b.py'))

# ============ ENGINEERING ============
ENG_KPIS=f'''<div class="kpis six">
{kpi("Money held up","—","","","flat","","heldup")}
{kpi("Past due date","—","","","flat","","late")}
{kpi("Longest wait","—","","","flat","","late")}
{kpi("Jobs open","—","","","flat","","unassigned")}
{kpi("Engineers","—","","","flat","","capacity")}
{kpi("Jobs costed","—","","","flat","","jobcost")}
</div>'''

ENG_OV=f'''{panel("What the late jobs are costing us",
 dtable(["Customer","What they are waiting for","Promised","Late by",("What they owe us",True),""])
 +thin("Engineering is not a cost centre here &mdash; it is where sold revenue gets stuck. "
 "Until an installation is finished the customer has little reason to settle, and we have no reason to expect them to."),
 "Money the business has earned but cannot collect until the work is done","heldup")}
{warn0()}
{panel("Can we actually deliver the work we are holding?",
 bars0()+thin("Open jobs, the jobs someone is assigned to, and the engineers available to do them."),"","capacity")}'''

ENG_DETAIL=f'''{panel("Every job past its promised date",
 dtable(["Job","Customer","Promised","Late by","Progress","Assigned to",""]),
 "Click a job to see its record","late")}
{panel("Every open job",
 dtable(["Job","Customer","Type","Status"]),"Open jobs, most overdue first","jobs")}
{panel("Why these numbers probably understate the problem",
 '<ul class="bul"></ul>'
 +thin("Where the job records themselves make the figures above less reliable than they look."))}'''

ENG_GAPS=f'''<div class="two">
{panel("What engineering earns", thin("<b>What each project has billed against what it has cost.</b> Parts issued, hours booked and purchases linked to a project add up to its cost; its invoices to what it earned."))}
{panel("Warranty and repeat failures", thin("<b>Warranty claims by product.</b> Which models keep coming back, and for whom &mdash; the numbers that say whether a product line is worth selling."))}
</div>
{panel("Maintenance we should be selling", thin("<b>Service visits scheduled after an installation.</b> Every installation should create the next service visit; recurring maintenance revenue is only asked for when it is scheduled."))}'''

V_ENG=('<div class="topbar"><div><h3>Project Insights</h3>'
 '<div class="when">Where sold revenue gets stuck</div></div></div>'
 +ENG_KPIS+
 '<div class="tabbar" data-g="teng">'
 '<button class="tab on" onclick="tab(this,&#39;teng&#39;,0)">Overview</button>'
 '<button class="tab" onclick="tab(this,&#39;teng&#39;,1)">Every job</button>'
 '<button class="tab" onclick="tab(this,&#39;teng&#39;,2)">Not yet measured</button></div>'
 '<div class="tabpane on" data-g="teng" data-i="0">'+ENG_OV+'</div>'
 '<div class="tabpane" data-g="teng" data-i="1">'+ENG_DETAIL+'</div>'
 '<div class="tabpane" data-g="teng" data-i="2">'+ENG_GAPS+'</div>')

# ============ CUSTOMER EXPERIENCE ============
V_CX=f'''<div class="topbar"><div><h3>Customer Service &amp; Issues</h3>
<div class="when">Cases customers have raised with us</div></div></div>
<div class="banner"><b>Every case here is an Issue in ERPNext.</b> A complaint, a query or a
fault a customer raises is recorded there; this screen shows them as they stand, longest wait first.</div>
<div class="kpis six">
{kpi("Open","—","","","flat","","cases")}
{kpi("Past due time","—","","","flat","","sla")}
{kpi("Equipment down","—","","","flat","","down")}
{kpi("Average wait","—","","","flat","","sla")}
{kpi("Also owe us","—","","","flat","","crossover")}
{kpi("Closed","—","","","flat","","cases")}
</div>
<div class="two">
{panel("Open cases, longest wait first",
 dtable(["Case","Customer","Waiting","Urgency",""]),"","cases")}
{panel("What they are complaining about",
 bars0()+thin("Cases grouped by the type they were given."),
 "All cases","causes")}
</div>
{warn0()}
<div class="two">
{panel("Why the same problems keep happening", thin("<b>The same problem, from the same customer, more than once.</b> Cases are grouped by customer and by type, so a machine that keeps failing shows up as a pattern rather than as separate annoyances."))}
{panel("Did we actually fix it", thin("<b>Closed cases, and whether anyone wrote down what fixed them.</b> A case closed with nothing recorded cannot be checked with the customer later."))}
</div>'''
