# -*- coding: utf-8 -*-
exec(_src('views_d.py'))

# Internal Audit. Every figure, row and finding is read when the screen opens (api/panels.py
# and api/panels_core.py): nothing about any one business is written here.
def _atbl(*cols):
    th="".join(f'<th{" style=text-align:right" if c.startswith(">") else ""}>{c.lstrip(">")}</th>' for c in cols)
    return f'<table class="dt"><thead><tr>{th}</tr></thead><tbody></tbody></table>'

V_AUD_OVERVIEW=f'''<div class="kpis six">
{kpi("Open findings","—","","","flat","","find")}
{kpi("Raise today","—","","","flat","","raise")}
{kpi("Overdue actions","—","","","flat","","find")}
{kpi("Repeat findings","—","","","flat","","find")}
{kpi("Unsupported","—","","","flat","","drafts")}
{kpi("Overall Business Health","—","","","flat","","score")}
</div>
{panel("What an auditor would raise on day one",
 _atbl("Finding","Risk","Area","")
 +thin("Found in the records this morning: the open alerts and the checks an auditor runs first. "
 "Raise it opens a new Non Conformance in ERPNext with the finding filled in."),
 "Reading the records&hellip;","find")}
<div class="two">
{panel("How a finding works", '<ul class="bul">'
 '<li>A finding is a <b>Non Conformance</b> in ERPNext: what was found, against which procedure, and the corrective and preventive action.</li>'
 '<li>What will be done, by whom and by when is a <b>Quality Action</b>, one resolution per step, each with the person responsible and a completion date.</li>'
 '<li>A finding is closed by setting it to Resolved; this screen counts what is still open and what is past its date.</li>'
 '<li>A finding on a procedure that was found wanting before is counted as a repeat.</li></ul>')}
{panel("Corrective actions",
 _atbl("Action","Responsible","Complete by","Status"),"","find")}
</div>'''

V_AUD_TRAIL=f'''<div class="kpis" style="grid-template-columns:repeat(4,1fr);margin-bottom:14px">
{kpi("Changes logged","—","","","flat","","trail")}
{kpi("On business docs","—","","","flat","","trail")}
{kpi("Earliest entry","—","","","flat","","trail")}
{kpi("Can be deleted","—","","","flat","","trail")}
</div>
{panel("The latest changes",
 _atbl("When","Who","What kind","What happened","Which record")
 +thin("Read from the change history in the business&#39;s own ERPNext: each change to a document, "
 "who made it and when. Open a record to see every field that changed, its value before and after."),
 "Reading the change history&hellip;","trail")}
<div class="warn" hidden></div>
{panel("How much history there is",
 _atbl("What was changed",">Times recorded")
 +thin("<b>Every individual change is kept, not a summary.</b> One invoice edited four times appears four "
 "times, each with the field that changed, its value before and after, who made it and when. "
 "That is what makes it useful to an auditor rather than merely reassuring."),
 "In their ERPNext today","trail")}
{panel("What this platform adds to it",
 '<ul class="bul">'
 '<li><b>Every change an administrator makes here</b> &mdash; people, businesses, keys &mdash; is recorded with who and when, under Settings &rarr; Changes. A secret&#39;s value never is.</li>'
 '<li><b>Every alert</b> keeps who acknowledged, assigned, deferred or dismissed it, and the reason given.</li>'
 '<li><b>Every action taken from this platform</b> &mdash; an approval, a task handed out &mdash; is made in ERPNext under the manager&#39;s own account, so ERPNext&#39;s own history records it as theirs.</li></ul>'
 +thin("The assistant reads only: it cannot create, change, approve or delete anything in ERPNext."))}'''

V_AUD_APPROVALS=f'''<div class="kpis" style="grid-template-columns:repeat(4,1fr);margin-bottom:14px">
{kpi("Unsubmitted","—","","","flat","","stuck")}
{kpi("Oldest of those","—","","","flat","","stuck")}
{kpi("Self-approved","—","","","flat","","selfapp")}
{kpi("Withdrawn","—","","","flat","","cancelled")}
</div>
{panel("Decisions taken",
 '<div class="scrollbox">'+_atbl("Reference","Party",">Value","Where it ended","")+'</div>'
 +thin("The largest purchase orders and payments submitted or withdrawn. Each reference opens the document in ERPNext, with its history."),
 "Largest by value &middot; scroll for more","selfapp")}
{panel("Where approvals currently sit",
 _atbl("Stage",">How many","Note")
 +thin("Every purchase order and payment, by the stage it has reached. The questions are whether "
 "anything gets stuck before the approvals, and whether the people signing are separate from the people asking."),
 "Purchases and payments","stuck")}
<div class="warn" hidden></div>
{panel("Raised and never submitted",
 _atbl("Order","Supplier",">Value","Raised","By","Stage")
 +thin("A weekly look at anything raised and not submitted within seven days catches these before they are forgotten."),"","stuck")}'''

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
<div class="when"></div></div></div>
<div class="askbox"><svg class="askbox-i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 3.5l1.7 4.8 4.8 1.7-4.8 1.7L11 16.5l-1.7-4.8L4.5 10l4.8-1.7z"/><path d="M18.5 14.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/></svg><input id="askin" placeholder="Ask anything about the business — in your own words" autocomplete="off"
 onkeyup="if(event.key==='Enter')runSearch(this.value)"></div>
<div class="sugg" id="asksugg">
<button class="btn" onclick="runSearch('Who owes us the most, and how long have they owed it?')">Who owes us the most?</button>
<button class="btn" onclick="runSearch('How did sales trend over the last 12 months, and where are we heading?')">How are sales trending?</button>
<button class="btn" onclick="runSearch('Which suppliers do we depend on most, and what if one stopped?')">Which suppliers do we depend on?</button>
</div>
<div class="askconvs" id="askconvs" hidden></div>
<div id="sout2"></div>
<div class="note"><h4>Two Things Worth Watching</h4><ul>
<li>It shows <b>what it checked</b>, step by step as it works, and lists every lookup under the answer. Every figure comes from the records or from ERPNext's own reports.</li>
<li>It reads; it never writes. <b>It has no way to create, change, approve or delete anything in ERPNext</b> — every action on these screens is yours, taken as you.</li></ul></div>'''
