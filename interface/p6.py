# -*- coding: utf-8 -*-
exec(_src('p5.py'))

V_MYDAY=f'''<div class="topbar"><div><h3>My day</h3>
<div class="when">Friday 19 September 2026 · only what is waiting on you</div></div></div>
<div class="grid" style="grid-template-columns:repeat(4,1fr)">
<div class="bk" onclick="go('approvals')"><div class="n" style="color:var(--crit)">3</div><div class="l">Awaiting you</div><div class="v">GHS 124,300 involved</div></div>
<div class="bk"><div class="n" style="color:var(--high)">5</div><div class="l">Due today</div><div class="v">before close of business</div></div>
<div class="bk" onclick="go('delegation')"><div class="n">2</div><div class="l">Evidence to check</div><div class="v">high-risk handovers</div></div>
<div class="bk"><div class="n" style="color:var(--crit)">4</div><div class="l">Promises unkept</div><div class="v">oldest is 19 months</div></div></div>
<div class="sect">Awaiting you</div>
{alert("crit","Credit note — A1 MEDICALSUPPLIES","Finance Manager has approved it · above GHS 10,000 it needs you",
 "Approve, reject, or ask for more.","11,000","GHS","Invoice","20250819090603609383","You","2 hours",
 "openDrawer('a1')",["Approve","Reject","Open the pack"])}
<div class="sect" style="margin-top:20px">Promises made to customers that have passed</div>
<table class="dt"><thead><tr><th>What was promised</th><th>To</th><th>By when</th><th>Late by</th><th></th></tr></thead><tbody>
<tr><td>Confirm the C-arm installation date</td><td>UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL</td>
<td>28 Feb 2025</td><td style="color:var(--crit)">19 months</td>
<td><button class="btn" onclick="openDrawer('ubuntu')">Open</button></td></tr>
<tr><td>Answer on the theatre setup schedule</td><td>UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL</td>
<td>28 Feb 2025</td><td style="color:var(--crit)">19 months</td>
<td><button class="btn" onclick="openDrawer('ubuntu')">Open</button></td></tr>
<tr><td>Talk to them about a payment plan</td><td>HAIRASH ENTERPRISE</td><td>26 Sep 2026</td>
<td style="color:var(--high)">due today</td><td><button class="btn" onclick="go('delegation')">Open</button></td></tr>
<tr><td>Sign off the AGAHF servicing job</td><td>Internal — Engineering</td><td>30 May 2024</td>
<td style="color:var(--crit)">28 months</td><td><button class="btn" onclick="go('eng')">Open</button></td></tr>
</tbody></table>'''

V_REPORTS=f'''<div class="topbar"><div><h3>Reports</h3>
<div class="when">Nine reports · built from the records, never typed up by hand</div></div></div>
<table class="dt"><thead><tr><th>Report</th><th>Checked against</th><th>When it runs</th><th>Last run</th><th></th></tr></thead><tbody>
<tr><td><b>Daily brief</b><div style="font-size:11px;color:var(--mut)">What moved, what is wrong, what needs deciding</div></td>
<td style="color:var(--mut)">The alert and task records</td><td style="color:var(--mut)">06:00 every day</td>
<td><span class="tag t-ok">✓ Agrees</span></td><td><button class="btn">Run</button></td></tr>
<tr><td><b>Sales and money owed</b><div style="font-size:11px;color:var(--mut)">Orders, invoicing, collections, who owes what, discounts, biggest customers</div></td>
<td style="color:var(--mut)">Customer account balances</td><td style="color:var(--mut)">Monday 07:00</td>
<td><span class="tag t-ok">✓ Agrees</span></td><td><button class="btn">Run</button></td></tr>
<tr><td><b>Buying and stock</b><div style="font-size:11px;color:var(--mut)">Open orders, suppliers, availability, ageing, money tied up</div></td>
<td style="color:var(--mut)">Stock and supplier balances</td><td style="color:var(--mut)">Weekly</td>
<td><span class="tag t-wt">! 3 differences</span></td><td><button class="btn">Run</button></td></tr>
<tr><td><b>Weekly management report</b></td><td style="color:var(--mut)">Each area's own numbers</td>
<td style="color:var(--mut)">Monday 07:00</td><td><span class="tag t-ok">✓ Agrees</span></td><td><button class="btn">Run</button></td></tr>
<tr><td><b>Monthly report</b></td><td style="color:var(--mut)">The accounts</td><td style="color:var(--mut)">1st working day</td>
<td><span class="tag t-ok">✓ Agrees</span></td><td><button class="btn">Run</button></td></tr>
<tr><td><b>Engineering</b></td><td style="color:var(--mut)">Job costs against the accounts</td>
<td style="color:var(--mut)">Weekly</td><td><span class="tag t-wt">! Costs not linked</span></td><td><button class="btn">Run</button></td></tr>
<tr><td><b>People</b><div style="font-size:11px;color:var(--mut)">Headcount, recruitment, attendance, payroll status</div></td>
<td style="color:var(--mut)">The HR records</td><td style="color:var(--mut)">Monthly</td>
<td><span class="tag t-ok">✓ Names hidden</span></td><td><button class="btn">Run</button></td></tr>
<tr><td><b>Compliance and audit</b></td><td style="color:var(--mut)">The compliance records</td>
<td style="color:var(--mut)">Monthly</td><td><span class="tag t-dr">– Arrives with the platform</span></td><td><button class="btn">Run</button></td></tr>
<tr><td><b>Board report</b></td><td style="color:var(--mut)">The accounts and the risk records</td>
<td style="color:var(--mut)">On request</td><td><span class="tag t-od">⛔ Needs approval to send</span></td><td><button class="btn">Run</button></td></tr>
</tbody></table>
<div class="note"><h4>Why each report says what it was checked against</h4><ul>
<li>Every report is compared against the figures in ERPNext before it is published. If it does not agree,
it still comes out — <b>marked as not agreeing, with the difference shown</b>. It is never quietly presented as correct.</li>
<li>The board report cannot be sent outside the company without an approval.</li></ul></div>'''

V_SEARCH=f'''<div class="topbar"><div><h3>Find anything</h3>
<div class="when">Records and documents · you only ever see what you are allowed to see</div></div></div>
<div class="askbox">⌕<input placeholder="Try: delivery note for the Ejura order" autocomplete="off"
 onkeyup="if(event.key==='Enter')showSearch()"></div>
<div style="display:flex;gap:6px;margin-bottom:14px"><button class="btn" onclick="showSearch()">Search</button></div>
<div id="searchout"></div>
<div class="sect" style="margin-top:20px">What is actually filed against each kind of record</div>
<div class="grid" style="grid-template-columns:repeat(4,1fr);gap:10px">
<div class="bk"><div style="display:flex;justify-content:space-between"><div style="font-size:12.5px;font-weight:560">Customers and sales</div><span style="font-size:15px;font-weight:640;color:var(--ok)">2</span></div>
<div style="font-size:10.5px;color:var(--mut);margin-top:5px">Quotes, agreements, delivery notes, invoices, receipts</div></div>
<div class="bk"><div style="display:flex;justify-content:space-between"><div style="font-size:12.5px;font-weight:560">Suppliers and buying</div><span style="font-size:15px;font-weight:640;color:var(--ok)">3</span></div>
<div style="font-size:10.5px;color:var(--mut);margin-top:5px">Quotes, orders, invoices, payment proof, warranties</div></div>
<div class="bk"><div style="display:flex;justify-content:space-between"><div style="font-size:12.5px;font-weight:560">Stock and equipment</div><span style="font-size:15px;font-weight:640;color:var(--dim)">0</span></div>
<div style="font-size:10.5px;color:var(--mut);margin-top:5px">Inspections, transfers, count sheets, write-off approvals</div></div>
<div class="bk"><div style="display:flex;justify-content:space-between"><div style="font-size:12.5px;font-weight:560">Engineering jobs</div><span style="font-size:15px;font-weight:640;color:var(--dim)">0</span></div>
<div style="font-size:10.5px;color:var(--mut);margin-top:5px">Estimates, checklists, photos, reports, customer sign-off</div></div>
<div class="bk"><div style="display:flex;justify-content:space-between"><div style="font-size:12.5px;font-weight:560">Staff</div><span style="font-size:15px;font-weight:640;color:var(--ok)">24</span></div>
<div style="font-size:10.5px;color:var(--mut);margin-top:5px">Contracts, qualifications, appraisals, handovers · <b style="color:var(--high)">restricted</b></div></div>
<div class="bk"><div style="display:flex;justify-content:space-between"><div style="font-size:12.5px;font-weight:560">Projects</div><span style="font-size:15px;font-weight:640;color:var(--dim)">0</span></div>
<div style="font-size:10.5px;color:var(--mut);margin-top:5px">Contracts, drawings, permits, certificates</div></div>
<div class="bk"><div style="display:flex;justify-content:space-between"><div style="font-size:12.5px;font-weight:560">Board and governance</div><span style="font-size:15px;font-weight:640;color:var(--dim)">0</span></div>
<div style="font-size:10.5px;color:var(--mut);margin-top:5px">Papers, policies, minutes, audit reports · <b style="color:var(--high)">restricted</b></div></div>
</div>
<div class="warn"><b>There is almost nothing filed.</b> Across the whole business there are 29 documents
attached to records — 24 of them staff files and 5 commercial. Alongside them sit roughly 38,000 small
image files left behind by email signatures. Searching will work from the first day; there is very little
for it to find until documents start being attached, and that is a change of habit rather than something
to build.</div>'''

V_RISK=f'''<div class="topbar"><div><h3>Risk and compliance</h3>
<div class="when">Ordered by how soon it bites, not by category</div></div></div>
<div class="grid" style="grid-template-columns:repeat(5,1fr)">
<div class="bk"><div class="n" style="color:var(--crit)">2</div><div class="l">Overdue</div><div class="v">deadlines already passed</div></div>
<div class="bk"><div class="n" style="color:var(--high)">3</div><div class="l">Within 1 month</div><div class="v">prepare now</div></div>
<div class="bk"><div class="n">5</div><div class="l">Within 3 months</div><div class="v">time to prepare</div></div>
<div class="bk"><div class="n" style="color:var(--dim)">0</div><div class="l">Findings</div><div class="v">arrives with the platform</div></div>
<div class="bk" onclick="go('health')"><div class="n" style="color:var(--high)">4</div><div class="l">Going wrong</div><div class="v">from Control Health</div></div></div>
<div class="sect">Obligations and deadlines</div>
<table class="dt"><thead><tr><th>What</th><th>Kind</th><th>Whose</th><th>When</th><th>Where it stands</th><th>Proof on file</th></tr></thead><tbody>
<tr><td>Radiation registration for the X-ray installations</td><td>Regulator</td><td>Engineering</td>
<td style="color:var(--crit)">Passed</td><td><span class="tag t-od">Overdue</span></td><td style="color:var(--high)">None</td></tr>
<tr><td>Import permit for medical devices</td><td>Regulator</td><td>Buying</td><td>Not recorded</td>
<td><span class="tag t-od">Not being tracked</span></td><td style="color:var(--high)">None</td></tr>
<tr><td>VAT return</td><td>Tax</td><td>Finance</td><td>Monthly</td><td><span class="tag t-ok">On time</span></td><td>In the accounts</td></tr>
<tr><td>Bank accounts checked against our records</td><td>Financial control</td><td>Finance</td><td>Monthly</td>
<td><span class="tag t-wt">Unknown</span></td><td style="color:var(--high)">Not confirmed</td></tr>
<tr><td>Warranties we owe on equipment we installed</td><td>Commercial</td><td>Engineering</td><td>Per contract</td>
<td><span class="tag t-wt">Not being tracked</span></td><td style="color:var(--high)">None</td></tr>
</tbody></table>
<div class="sect" style="margin-top:20px">Carried over from Control Health</div>
{alert("crit","We have promised customers stock we do not physically have, across 491 products",
 "Nobody has been made responsible for this.","Give it an owner today.","491","products",
 "Stock position","reserved but unavailable","Nobody yet","ongoing","openDrawer('stock')",
 ["Raise as a finding","Give it an owner"])}
{alert("high","UBUNTU has been waiting for three installations since February last year",
 "They also owe us GHS 636,675. We have not delivered and they have not paid.",
 "One conversation, both subjects.","636,675","GHS at risk","Projects","PROJ-0028 / 0029 / 0030",
 "Engineering","19 months","openDrawer('ubuntu')",["Raise as a finding","Give it an owner","Escalate"])}
<div class="note"><h4>Why several lines say "not being tracked"</h4><ul>
<li>There is no register of licences, permits or warranty obligations anywhere in ERPNext today.</li>
<li>Saying so is the honest answer. <b>A compliance screen that shows only what it happens to know about
suggests everything else is fine</b> — which is the opposite of the truth.</li></ul></div>'''
