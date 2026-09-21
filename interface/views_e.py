# -*- coding: utf-8 -*-
exec(_src('views_d.py'))

V_AUD_OVERVIEW=f'''<div class="kpis six">
{kpi("Open findings","0","","nothing recorded yet","flat","","find")}
{kpi("Raise today","6","","from Business Health","dn","","raise")}
{kpi("Overdue actions","0","","nothing tracked yet","flat")}
{kpi("Repeat findings","0","","no history to compare","flat")}
{kpi("Unsupported","88","","invoices never issued","dn","","drafts")}
{kpi("Control score","44","/100","four of six questions failing","dn","","score")}
</div>
{panel("What an auditor would raise on day one",
 '<table class="dt"><thead><tr><th>Finding</th><th>Risk</th><th>Area</th><th></th></tr></thead><tbody>'
 +"".join(f'<tr><td>{f}</td><td><span class="tag {t}">{r}</span></td><td style="color:var(--mut)">{a}</td>'
          f'<td><button class="btn">Raise it</button></td></tr>' for f,r,t,a in [
  ("Customers are promised stock the company does not hold, across 491 products","Critical","t-od","Stock"),
  ("Nearly a third of stock value sits outside every warehouse","Critical","t-od","Stock"),
  ("The entire GHS 9.18M owed is over three months old with no collection activity","Critical","t-od","Money owed"),
  ("Almost all buying depends on two overseas suppliers","High","t-wt","Buying"),
  ("Three customer installations are nineteen months past their promised date","High","t-wt","Engineering"),
  ("88 invoices were written and never issued","Medium","t-wt","Money in")])+'</tbody></table>',
 "Every one of these was found in the records on the first morning","find")}
<div class="two">
{panel("How a finding works", '<ul class="bul">'
 '<li>A finding records what was found, the evidence, how serious it is and <b>who owns fixing it</b>.</li>'
 '<li>The owner writes back what they will do and by when.</li>'
 '<li><b>The person who fixed it cannot be the person who signs it off.</b> That rule is enforced, not requested.</li>'
 '<li>Overdue and repeat findings escalate on their own.</li></ul>')}
{panel("Corrective actions", thin("<b>Nothing open yet.</b> Once a finding is raised it carries an owner, a date, the evidence required to close it, and an independent verifier. None of that exists in ERPNext today."))}
</div>'''

V_AUD_TRAIL=f'''<div class="kpis" style="grid-template-columns:repeat(4,1fr);margin-bottom:14px">
{kpi("Changes logged","91,133","","since 5 February 2024","flat","","trail")}
{kpi("On business docs","46,975","","invoices, orders, payments, stock","flat","","trail")}
{kpi("Earliest entry","5 Feb","2024","19 months of history","flat","","trail")}
{kpi("Can be deleted","No","","not even by an administrator","up","","trail")}
</div>
<div class="filters">
<input id="afq" placeholder="Search the trail &mdash; person, record, anything" onkeyup="filterTrail()">
<select id="afk" onchange="filterTrail()"><option value="">Every kind of event</option>
<option value="connect">Set-up</option><option value="read">Read</option>
<option value="create">Record created</option><option value="change">Record changed</option>
<option value="approve">Approval</option><option value="ask">Question asked</option>
<option value="perm">Permission change</option></select>
<select id="afu" onchange="filterTrail()"><option value="">Everyone</option>
<option value="Samuel Opoku">Samuel Opoku</option>
<option value="Grace Williams">Grace Williams</option>
<option value="Samuel Adjei">Samuel Adjei</option>
<option value="Solomon Boateng">Solomon Boateng</option>
<option value="Solomon Adortsu">Solomon Adortsu</option>
<option value="Simon Nketiah Sieh">Simon Nketiah Sieh</option>
<option value="System Administration">System Administration</option></select>
<span class="immut">&#128274; Written once &middot; cannot be edited or deleted</span>
<span class="tcount" id="afc"></span></div>
<table class="dt" id="atrail"><thead><tr><th>When</th><th>Who</th><th>What kind</th>
<th>What happened</th><th>Which record</th><th></th></tr></thead><tbody>{trail_rows()}</tbody></table>
<div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;
font-size:11.5px;color:var(--dim)">
<span>Rows with an arrow open the change itself &mdash; field, value before, value after. Showing the most recent 21 of 91,133; paged, not trimmed &mdash;
older entries load as you scroll back, and any date range can be opened directly.</span>
<span><button class="btn">Load older</button></span></div>
<div class="warn" style="margin-top:14px"><b>This is a real trail, not a mock-up.</b> The business entries
are actual changes made by Gigmann staff, read from the change history in their own ERPNext. The set-up
entries are the work of configuring this platform, which is why they are all dated today &mdash; the site
was built this morning. <b>Two lines explain things you have seen elsewhere:</b> the Ejura order still
undespatched, and the A1 Medicalsupplies invoice now sitting in Approvals.</div>
{panel("How much history there is",
 '<table class="dt"><thead><tr><th>What was changed</th><th style="text-align:right">Times recorded</th>'
 '</tr></thead><tbody>'+depth_rows()+'</tbody></table>'
 +thin("<b>Every individual change is kept, not a summary.</b> One invoice edited four times appears four "
 "times, each with the field that changed, its value before and after, who made it and when. "
 "That is what makes it useful to an auditor rather than merely reassuring."),
 "In their ERPNext today","trail")}
{panel("What this platform adds to it",
 '<ul class="bul">'
 '<li><b>Every sign-in</b>, successful or refused, with the account and the time.</li>'
 '<li><b>Every approval</b> &mdash; who asked, who decided, what they decided, which records were attached, and any comment.</li>'
 '<li><b>Every question put to the assistant</b>, the records it read to answer, and any action it took on someone&#39;s behalf.</li>'
 '<li><b>Every change to who can see what</b>, and who made it.</li>'
 '<li><b>Every threshold and rule change</b> an administrator makes.</li></ul>'
 +thin("ERPNext already records what changed on a document. What it does not record is who looked, who "
 "approved, who was refused, and what was asked of the assistant. Those are added here and kept to the same "
 "standard &mdash; written once, with each entry carrying a fingerprint of the one before it, so removing a "
 "line from the database breaks the chain visibly."))}'''

V_AUD_APPROVALS=f'''<div class="kpis" style="grid-template-columns:repeat(4,1fr);margin-bottom:14px">
{kpi("Unsubmitted","903,632","GHS","11 purchase orders","dn","review","stuck")}
{kpi("Oldest of those","26","months","July 2024","dn","","stuck")}
{kpi("Self-approved","2","","found in the change history","dn","review","selfapp")}
{kpi("Withdrawn","3","","two of them over GHS 490,000","flat","","cancelled")}
</div>
{panel("Decisions taken",
 '<div class="scrollbox"><table class="dt"><thead><tr><th>Reference</th><th>Party</th>'
 '<th style="text-align:right">Value GHS</th><th>Where it ended</th><th></th>'
 '</tr></thead><tbody>'+decided_rows()+'</tbody></table></div>'
 +thin("Rows with an arrow open the approval itself &mdash; each stage, who moved it and how long they took."),
 "Largest by value &middot; scroll for more","selfapp")}
{panel("Where approvals currently sit",
 '<table class="dt"><thead><tr><th>Stage</th><th style="text-align:right">How many</th><th>Note</th></tr></thead><tbody>'
 +state_rows()+'</tbody></table>'
 +thin("Gigmann runs a four-stage check on purchases &mdash; <b>operations manager, director, then chief "
 "executive</b> &mdash; and a shorter one on payments. The stages exist and are used. The questions are "
 "whether anything gets stuck before them, and whether the people signing are separate from the people asking."),
 "Purchases and payments","stuck")}
<div class="warn"><b>GHS 903,632 of purchase orders were raised and never submitted for approval.</b>
Five of them are over GHS 50,000 and the oldest has been sitting since July 2024. They are not rejected and
not withdrawn &mdash; simply never sent. Nobody is waiting on them because nobody knows they exist.
<div class="acts"><button class="btn pri" onclick="explain({SQ}stuck{SQ})">See all eleven</button>
<button class="btn">Raise as a finding</button></div></div>
{panel("Raised and never submitted",
 '<table class="dt"><thead><tr><th>Order</th><th>Supplier</th><th style="text-align:right">Value GHS</th>'
 '<th>Raised</th><th>By</th><th>Stage</th></tr></thead><tbody>'+stuck_rows()+'</tbody></table>'
 +thin("This is the cheapest thing on the whole platform to fix. A weekly list of anything raised and not "
 "submitted within seven days would have caught every one of these."),"","stuck")}'''

V_AUD=('<div class="topbar"><div><h3>Internal Audit</h3>'
 '<div class="when">Findings, corrective actions, and the record of everything that has happened</div></div></div>'
 '<div class="tabbar" data-g="taud">'
 '<button class="tab on" onclick="tab(this,&#39;taud&#39;,0)">Overview</button>'
 '<button class="tab" onclick="tab(this,&#39;taud&#39;,1)">Approval history</button>'
 '<button class="tab" onclick="tab(this,&#39;taud&#39;,2)">Audit trail</button></div>'
 '<div class="tabpane on" data-g="taud" data-i="0">'+V_AUD_OVERVIEW+'</div>'
 '<div class="tabpane" data-g="taud" data-i="1">'+V_AUD_APPROVALS+'</div>'
 '<div class="tabpane" data-g="taud" data-i="2">'+V_AUD_TRAIL+'</div>')

# ============ SEARCH (agentic) ============
V_SEARCH=f'''<div class="topbar"><div><h3>Find anything</h3>
<div class="when">Ask in your own words · it looks through the records and shows its working</div></div></div>
<div class="askbox">⌕<input id="sin" placeholder="Try: has UBUNTU ever paid us?" autocomplete="off"
 onkeyup="if(event.key==='Enter')runSearch(this.value)"></div>
<div class="sugg">
<button class="btn" onclick="runSearch('Has UBUNTU ever paid us?')">Has UBUNTU ever paid us?</button>
<button class="btn" onclick="runSearch('Which customers owe us money and are also waiting on us?')">Who owes us and is also waiting on us?</button>
<button class="btn" onclick="runSearch('What happens if SICHUAN stops supplying?')">What if SICHUAN stops supplying?</button>
<button class="btn" onclick="runSearch('Find the delivery note for the Ejura order')">Delivery note for the Ejura order</button>
</div>
<div id="sout"></div>'''

V_ASK=f'''<div class="topbar"><div><h3>Ask AI</h3>
<div class="when">Answers come from the records, and always say which ones</div></div></div>
<div class="askbox">⌕<input id="askin" placeholder="Ask anything about the business" autocomplete="off"
 onkeyup="if(event.key==='Enter')runSearch(this.value)"></div>
<div class="sugg">
<button class="btn" onclick="runSearch('Why is the Ejura order still open?')">Why is the Ejura order still open?</button>
<button class="btn" onclick="runSearch('Who owes us the most and have they ever paid?')">Who owes us the most?</button>
<button class="btn" onclick="runSearch('What should I say to UBUNTU?')">What should I say to UBUNTU?</button>
<button class="btn" onclick="runSearch('Issue a credit note for A1 Medicalsupplies')">Issue a credit note</button>
</div>
<div id="sout2"></div>
<div class="note"><h4>Two things worth watching</h4><ul>
<li>It shows <b>what it checked</b> before it answers. Every figure came out of a query; the wording around it is written, the numbers are not.</li>
<li>Ask it to issue a credit note and it refuses — <b>not because it was told to, but because no such function exists on the platform</b>.</li></ul></div>'''
