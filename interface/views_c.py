# -*- coding: utf-8 -*-
exec(_src('views_b.py'))

# ============ ENGINEERING ============
ENG_KPIS=f'''<div class="kpis six">
{kpi("Money held up","636","k GHS","UBUNTU alone","dn","","ubuntu")}
{kpi("Past due date","6","","oldest 28 months","dn","","late")}
{kpi("Longest wait","28","months","Samkwarth lab setup","dn","","late")}
{kpi("Jobs open","14","","11 with nobody on them","dn","","unassigned")}
{kpi("Engineers","3","","for the whole country","dn","","capacity")}
{kpi("Jobs costed","0","","of 14","dn","review","jobcost")}
</div>'''

ENG_OV=f'''{panel("What the late jobs are costing us",
 '<table class="dt"><thead><tr><th>Customer</th><th>What they are waiting for</th>'
 '<th>Promised</th><th>Late by</th><th style="text-align:right">What they owe us</th><th></th></tr></thead><tbody>'
 '<tr><td>UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL</td><td>C-arm, theatre setup and X-ray installations</td>'
 '<td style="white-space:nowrap">28 Feb 2025</td><td style="color:var(--crit);white-space:nowrap">19 months</td>'
 '<td class="num" style="color:var(--crit)">636,675</td>'
 '<td><button class="btn" onclick="openDrawer(&#39;ubuntu&#39;)">Both sides</button></td></tr>'
 '<tr><td>SAMKWARTH PHARMACEUTICAL LTD</td><td>Laboratory setup</td>'
 '<td style="white-space:nowrap">20 May 2024</td><td style="color:var(--crit);white-space:nowrap">28 months</td>'
 '<td class="num" style="color:var(--dim)">not in the ten largest</td><td></td></tr>'
 '<tr><td style="color:var(--mut)">AGAHF</td><td>Maintenance and servicing, 56% done</td>'
 '<td style="white-space:nowrap">30 May 2024</td><td style="color:var(--crit);white-space:nowrap">28 months</td>'
 '<td class="num" style="color:var(--dim)">&mdash;</td><td></td></tr>'
 '</tbody></table>'
 +thin("Engineering is not a cost centre here &mdash; it is where sold revenue gets stuck. "
 "Until an installation is finished the customer has little reason to settle, and we have no reason to expect them to."),
 "Money the business has earned but cannot collect until the work is done","ubuntu")}
<div class="warn"><b>UBUNTU appears twice in this business and nobody has put the two halves together.</b>
They are waiting on three installations promised for February last year, and they owe GHS 636,675 that is
more than three months late. Asking for the money without mentioning the installations is a difficult call.
<div class="acts"><button class="btn pri" onclick="openDrawer({SQ}ubuntu{SQ})">See both sides</button>
<button class="btn" onclick="ask2({SQ}What should I say to UBUNTU?{SQ})">Ask what to say</button></div></div>
{panel("Can we actually deliver the work we are holding?",
 bar_chart([("Open jobs",14,"var(--high)"),("Jobs with someone on them",3,"var(--ok)"),
            ("Engineers available",3,"var(--accent)")],fmt=lambda v:g(v))
 +thin("Three engineers, fourteen open jobs, eleven of them with nobody assigned. "
 "The nineteen-month delays are a <b>capacity</b> problem. Hiring one more engineer is a different "
 "decision from chasing the existing three."),"","capacity")}'''

ENG_DETAIL=f'''{panel("Every job past its promised date",
 '<table class="dt"><thead><tr><th>Job</th><th>Customer</th><th>Promised</th><th>Late by</th>'
 '<th>Progress</th><th>Assigned to</th><th></th></tr></thead><tbody>'
 +"".join(f'<tr><td><span class="lnk" onclick="openDrawer({SQ}{d}{SQ})">{j}</span></td><td>{c}</td>'
          f'<td style="white-space:nowrap">{p}</td>'
          f'<td style="color:var(--crit);white-space:nowrap">{l}</td><td>{pr}</td>'
          f'<td style="color:var(--high)">Nobody</td>'
          f'<td><button class="btn" onclick="ask2({SQ}Why is the {short} job still open?{SQ})">Ask why</button></td></tr>'
  for j,c,p,l,pr,d,short in [
  ("C-arm installation","UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL","28 Feb 2025","19 months","Not started","ubuntu","C-arm"),
  ("Theatre setup","UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL","28 Feb 2025","19 months","Not started","ubuntu","theatre setup"),
  ("X-ray installation","UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL","28 Feb 2025","19 months","Not started","ubuntu","X-ray"),
  ("Lab setup","SAMKWARTH PHARMACEUTICAL LTD","20 May 2024","28 months","Not started","order","lab setup"),
  ("AGAHF maintenance and servicing","&mdash;","30 May 2024","28 months","56%","order","AGAHF maintenance")])+'</tbody></table>',
 "Click a job to see both sides of that customer","late")}
{panel("Every open job",
 '<table class="dt"><thead><tr><th>Job</th><th>Customer</th><th>Type</th><th>Status</th></tr></thead><tbody>'
 '<tr><td>C-arm installation</td><td>UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL</td><td style="color:var(--mut)">Installation</td><td><span class="tag t-od">19 months late</span></td></tr>'
 '<tr><td>Theatre setup</td><td>UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL</td><td style="color:var(--mut)">Installation</td><td><span class="tag t-od">19 months late</span></td></tr>'
 '<tr><td>X-ray installation</td><td>UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL</td><td style="color:var(--mut)">Installation</td><td><span class="tag t-od">19 months late</span></td></tr>'
 '<tr><td>Lab setup</td><td>SAMKWARTH PHARMACEUTICAL LTD</td><td style="color:var(--mut)">Installation</td><td><span class="tag t-od">28 months late</span></td></tr>'
 '<tr><td>AGAHF maintenance and servicing</td><td style="color:var(--mut)">&mdash;</td><td style="color:var(--mut)">Maintenance</td><td><span class="tag t-od">28 months late</span></td></tr>'
 '<tr><td>St Josep Hospital &mdash; Oseikojokrom</td><td style="color:var(--mut)">&mdash;</td><td style="color:var(--mut)">Not set</td><td><span class="tag t-wt">No dates at all</span></td></tr>'
 '<tr><td>Complete X-ray set up</td><td style="color:var(--mut)">&mdash;</td><td style="color:var(--mut)">Installation on purchase</td><td><span class="tag t-wt">Recorded twice</span></td></tr>'
 '<tr><td>Complte X-ray set up</td><td style="color:var(--mut)">&mdash;</td><td style="color:var(--mut)">Installation on purchase</td><td><span class="tag t-wt">Recorded twice</span></td></tr>'
 '</tbody></table>',"14 open of 30 projects in total","jobs")}
{panel("Why these numbers probably understate the problem",
 '<ul class="bul"><li><b>Two jobs are recorded twice</b> &mdash; the same X-ray setup, one spelled wrong. Counted as two, it is one.</li>'
 '<li><b>Job types are typed by hand</b>, so "INSTALLATION" and "Installation on Purchase" do not group together.</li>'
 '<li><b>Finished jobs still show no progress</b>, so completion rates read worse than reality.</li>'
 '<li><b>Staff departures sit in the same list as customer installations</b>, so a plain count of projects is meaningless.</li></ul>'
 +thin("This matters for a management screen because it means <b>the real position cannot currently be measured</b>, "
 "only estimated. Tidying the job types is an afternoon of work and makes every figure above trustworthy."))}'''

ENG_GAPS=f'''<div class="two">
{panel("What engineering earns", thin("<b>Cannot be calculated from this demo extract.</b> No job carries a cost, so nobody knows whether installations make money or lose it. ERPNext already holds the fields for this &mdash; parts, hours and billing simply are not being linked to the job."))}
{panel("Warranty and repeat failures", thin("<b>Not recorded in this demo extract.</b> What each installed machine has cost under warranty, and which models keep coming back &mdash; the numbers that say whether a product line is worth selling."))}
</div>
{panel("Maintenance we should be selling", thin("<b>Not scheduled in this demo extract.</b> Every installation should create the next service visit when it closes. None currently does, so recurring maintenance revenue is simply not being asked for."))}'''

V_ENG=('<div class="topbar"><div><h3>Project Insights</h3>'
 '<div class="when">Where sold revenue gets stuck &middot; 30 jobs &middot; 3 engineers</div></div></div>'
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
<div class="when">11 cases · seeded for this demonstration</div></div></div>
<div class="banner"><b>These eleven cases were created by us.</b> Gigmann's copy held no complaint records
at all. The customer names are real; the complaints are not. Everything else on this screen is how the
finished product behaves.</div>
<div class="kpis six">
{kpi("Open","6","","4 of them urgent","dn","","cases")}
{kpi("Past due time","6","","up to 25 days","dn","","sla")}
{kpi("Equipment down","2","","X-ray and autoclave","dn","","down")}
{kpi("Average wait","12","days","on open cases","dn","","sla")}
{kpi("Also owe us","3","","of 6 open","dn","care","crossover")}
{kpi("Closed","2","","resolved and closed","up","","cases")}
</div>
<div class="two">
{panel("Open cases, longest wait first",
 '<table class="dt"><thead><tr><th>Case</th><th>Customer</th><th>Waiting</th><th>Urgency</th><th></th></tr></thead><tbody>'
 +"".join(f'<tr><td>{c}</td><td>{cu}</td><td style="color:{col}">{w}</td>'
          f'<td><span class="tag {tg}">{u}</span></td>'
          f'<td><button class="btn" onclick="ask2({SQ}Tell me about the {short} case{SQ})">Ask</button></td></tr>'
  for c,cu,w,col,u,tg,short in [
  ("No response to installation follow-up","HAIRASH ENTERPRISE","25 days","var(--crit)","Urgent","t-od","HAIRASH"),
  ("Autoclave not reaching temperature","VINEYARD HOSPITAL","22 days","var(--crit)","Urgent","t-od","autoclave"),
  ("Refund requested — invoiced twice","KING JO MEDICAL SUPPLIES","18 days","var(--high)","Normal","t-wt","refund"),
  ("X-ray generator tripping — unit down","ST JOHN OF GOD-SEFWI-ASAFO","7 days","var(--high)","Urgent","t-od","X-ray generator"),
  ("Monitor probe failed under warranty","ILEE MEDICAL CENTRE","4 days","var(--mut)","Normal","t-wt","monitor probe"),
  ("Oxygen concentrator alarming","EJURA MUNICIPAL HOSPITAL","2 days","var(--mut)","Urgent","t-od","oxygen concentrator")])
 +'</tbody></table>',"","cases")}
{panel("What they are complaining about",
 bar_chart([("Equipment fault",4,"var(--crit)"),("Delivery or quantity",2,"var(--high)"),
            ("Billing",2,"var(--med)"),("No response from us",1,"var(--crit)"),("Product quality",2,"var(--accent)")],fmt=lambda v:g(v))
 +thin("Four of eleven are equipment faults, and two of those leave a hospital unable to use the machine. Those are the ones that damage a reputation."),
 "All eleven cases","causes")}
</div>
<div class="warn"><b>Three of the six open complaints are from customers who also owe us money.</b>
HAIRASH owes GHS 737,544 and has been waiting 25 days for an answer about an installation. Anyone ringing
them about the debt needs to know that first.
<div class="acts"><button class="btn pri" onclick="ask2('Which customers owe us money and are also waiting on us?')">Show me all of them</button></div></div>
<div class="two">
{panel("Why the same problems keep happening", thin("<b>Needs more history than this demo extract holds.</b> With a full year of cases the finished screen groups complaints by product and by cause, so a machine that keeps failing shows up as a pattern rather than as eleven separate annoyances."))}
{panel("Did we actually fix it", thin("<b>Not recorded in this demo extract.</b> The finished screen will not let a case close until the customer has confirmed they are satisfied — so 'resolved' means resolved for them, not for us."))}
</div>'''
