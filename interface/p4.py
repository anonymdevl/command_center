# -*- coding: utf-8 -*-
exec(_src('p3.py'))

# ---------------- V: ASK ----------------
V_ASK=f'''<div class="topbar"><div><h3>Ask the business</h3>
<div class="when">Answers come from the records, and always say which ones</div></div></div>
<div class="askbox">⌕<input id="askin" placeholder="Try: why is the Ejura order still open?" autocomplete="off"></div>
<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px">
<button class="btn" onclick="ask(0)">Why is the Ejura order still open?</button>
<button class="btn" onclick="ask(1)">Who owes us the most and have they ever paid?</button>
<button class="btn" onclick="ask(2)">Issue a credit note for A1 Medicalsupplies</button></div>
<div id="answers"></div>
<div class="note"><h4>Two things to watch on this screen</h4><ul>
<li>Every figure in an answer came out of a query. The wording around it is written; <b>the numbers are not</b>.</li>
<li>The third question is refused. Not because it was told to refuse — <b>there is no function on the
platform that can issue a credit note</b>, however the request is phrased.</li></ul></div>'''

ANSWERS = [
 {"q":"Why is the Ejura order still open?",
  "html":f'''<div class="ans"><p>EJURA MUNICIPAL HOSPITAL placed a <b>GHS 65,100</b> order on 19 August 2025.
Nothing has left the warehouse and nothing has been invoiced since.</p>
<p>Nothing has been despatched, and until it is we cannot invoice. That is why this order shows as
waiting on both despatch and payment — they are the same hold-up, not two.</p>
<p>It is the largest order we have taken and not fulfilled. The three others still open come to
GHS 19,850 between them.</p>
<div class="srcs"><span class="chip src" onclick="openDrawer('ejura')">Sales order · <b>SAL-ORD-2025-00910</b></span>
<span class="chip">Customer · <b>EJURA MUNICIPAL HOSPITAL</b></span>
<span class="chip">3 other open orders examined</span></div></div>'''},
 {"q":"Who owes us the most and have they ever paid?",
  "html":f'''<div class="ans"><p><b>HAIRASH ENTERPRISE</b> owes the most: <b>GHS 737,544</b>, all of it more than
three months late.</p>
<p>No payment has ever been matched against any of their invoices. That is different from paying late —
there is no record of them paying us at all against this balance.</p>
<p>Behind them: UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL at GHS 636,675 and A.S Hospitex at GHS 541,841.
UBUNTU is also waiting on three installations we have not delivered, so that conversation has two sides to it.</p>
<div class="srcs"><span class="chip src" onclick="openDrawer('ar')">Customer accounts · <b>10 customers</b></span>
<span class="chip src" onclick="openDrawer('ubuntu')">Projects · <b>PROJ-0028 / 0029 / 0030</b></span>
<span class="chip">806 unpaid invoices examined</span></div></div>'''},
 {"q":"Issue a credit note for A1 Medicalsupplies",
  "html":f'''<div class="gate"><div class="gt">⛔ I cannot do this — it needs a person to approve it</div>
<p>Issuing or changing a credit note affects what a customer owes. There is no function available to me
that performs it, whatever the request says.</p>
<p style="margin-top:8px">I have prepared the request instead. It carries the invoice, the customer's
balance and the proposed amount, and it is waiting for the <b>Finance Manager</b> in Approvals.</p>
<div class="acts"><button class="btn pri" onclick="go('approvals')">Open the request</button>
<button class="btn">Cancel it</button></div></div>'''}]

# ---------------- V: APPROVALS ----------------
V_APPROVALS=f'''<div class="topbar"><div><h3>Approvals</h3>
<div class="when">3 waiting on you · 2 you have passed to someone else</div></div></div>
<div class="alert high"><div class="arow"><div>
<div class="awhat">Credit note — A1 MEDICALSUPPLIES</div>
<div class="awhy">Raised on your behalf by the assistant · needs Finance Manager, then you</div>
<div class="asw">→ Approve, reject, or ask for more before it goes further.</div></div>
<div class="afig"><span class="cx">GHS</span>11,000</div></div>
<div class="ameta"><span class="chip">Type <b>Refunds and credit</b></span>
<span class="chip">Value band <b>10,001 – 100,000</b></span>
<span class="chip">Route <b>Finance Manager → Chief Executive</b></span>
<span class="chip">Raised <b>2 hours ago</b></span></div>
<div style="background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin-top:10px">
<div style="font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);font-weight:600;margin-bottom:8px">Everything you need to decide</div>
<table class="dt"><tbody>
<tr><td style="color:var(--mut);width:180px">Invoice</td><td><span class="lnk" onclick="openDrawer('a1')">20250819090603609383</span></td></tr>
<tr><td style="color:var(--mut)">What they owe in total</td><td>GHS 11,000 — one invoice, due 19 Aug, nothing older</td></tr>
<tr><td style="color:var(--mut)">The original order</td><td>SAL-ORD-2025-00905 · fully despatched</td></tr>
<tr><td style="color:var(--mut)">Supporting documents</td><td style="color:var(--high)">None attached</td></tr>
<tr><td style="color:var(--mut)">Credit notes before this</td><td>None for this customer</td></tr>
</tbody></table></div>
<div class="acts"><button class="btn pri">Approve</button><button class="btn dgr">Reject</button>
<button class="btn">Ask for more</button><button class="btn">Pass to someone else</button></div></div>
<div class="alert med"><div class="arow"><div>
<div class="awhat">Purchase order — medical consumables restock</div>
<div class="awhy">Department head has approved · Finance Manager still to look</div>
<div class="asw">→ Nothing needed from you yet.</div></div>
<div class="afig"><span class="cx">GHS</span>48,200</div></div>
<div class="ameta"><span class="chip">Type <b>Purchases</b></span>
<span class="chip">Route <b>Dept head ✓ → Finance Manager</b></span>
<span class="chip">Raised <b>1 day ago</b></span></div></div>
<div class="note"><h4>Where the decision is actually enforced</h4><ul>
<li>Approving here drives the approval inside ERPNext. The control lives in the system that holds the
money, not in this dashboard.</li>
<li>Every decision records who asked, who decided, when, what they decided, which records were attached
and any comment — and that record cannot afterwards be edited.</li></ul></div>'''

# ---------------- V: DELEGATION ----------------
V_DELEG=f'''<div class="topbar"><div><h3>Outstanding Tasks</h3>
<div class="when">12 open · 3 late · 1 sent back more than once · 2 high risk</div></div></div>
<div class="grid" style="grid-template-columns:repeat(4,1fr)">
<div class="bk"><div class="n">12</div><div class="l">Still open</div><div class="v">work you handed out</div></div>
<div class="bk"><div class="n" style="color:var(--crit)">3</div><div class="l">Late</div><div class="v">past the date you set</div></div>
<div class="bk"><div class="n" style="color:var(--high)">1</div><div class="l">Reopened twice+</div><div class="v">sent back more than once</div></div>
<div class="bk"><div class="n" style="color:var(--high)">2</div><div class="l">High risk</div><div class="v">money or compliance</div></div></div>
<div class="sect">Chasing payment from HAIRASH ENTERPRISE</div>
<div class="alert high"><div class="arow"><div>
<div class="awhat">Get a payment plan from HAIRASH ENTERPRISE</div>
<div class="awhy">Came from the alert about money owed · GHS 737,544 outstanding, all over three months late</div>
<div class="asw">→ K. Mensah says it is done. It is not closed until you accept the evidence.</div></div>
<div class="afig"><span class="cx">GHS</span>737,544</div></div>
<div class="ameta"><span class="chip">Came from <b>An alert</b></span>
<span class="chip">Given to <b>K. Mensah</b></span><span class="chip">Department <b>Credit Control</b></span>
<span class="chip">Due <b>26 Sep 2026</b></span></div>
<div class="tstate"><div class="ts done">Handed out</div><div class="ts done">Accepted</div>
<div class="ts done">Being worked on</div><div class="ts now">Waiting on you</div><div class="ts">Closed</div></div>
<div style="background:var(--high-bg);border:1px solid var(--high-line);border-radius:8px;padding:11px 13px">
<div style="font-size:12px;font-weight:620;color:var(--high);margin-bottom:5px">Marking it done is not the same as finishing it</div>
<div style="font-size:12.5px;color:var(--mut);line-height:1.55">You asked for
<b style="color:var(--ink)">a signed payment plan with dates on it</b>. K. Mensah marked this complete on
22 September and attached call notes. Call notes are not a signed plan, so it stays with you until you say otherwise.</div>
<div class="ameta"><span class="chip">1 attachment · <b>call-notes.pdf</b></span></div>
<div class="acts"><button class="btn pri">Accept it</button><button class="btn dgr">Send it back</button>
<button class="btn">Ask for more</button></div></div></div>
<div class="note"><h4>Where the work actually happens</h4><ul>
<li>This platform is for management. <b>K. Mensah does not have a login here.</b></li>
<li>The task was written into ERPNext, where she already works, and her evidence came back the same way.
Only the decision to accept or reject it happens on this screen.</li></ul></div>'''
