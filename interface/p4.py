# -*- coding: utf-8 -*-
exec(_src('p3.py'))

# ---------------- V: ASK ----------------
V_ASK=f'''<div class="topbar"><div><h3>Ask the business</h3>
<div class="when">Answers come from the records, and always say which ones</div></div></div>
<div class="askbox">⌕<input id="askin" placeholder="Try: why is the Ejura order still open?" autocomplete="off"></div>
<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px">
<button class="btn" onclick="ask(0)">Why is the Ejura order still open?</button>
<button class="btn" onclick="ask(1)">Who owes us the most and have they ever paid?</button></div>
<div id="answers"></div>
<div class="note"><h4>Two things to watch on this screen</h4><ul>
<li>Every figure in an answer came out of a query. The wording around it is written; <b>the numbers are not</b>.</li>
<li>It reads; it never writes. <b>There is no function on the platform that can create, change or
delete anything in ERPNext</b>, however a request is phrased.</li></ul></div>'''

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
<div class="when">Reading what is waiting on you&hellip;</div></div></div>
<div class="work-list"><div class="work-empty"><b>Reading your approvals&hellip;</b></div></div>
<div class="note"><h4>Where the decision is actually enforced</h4><ul>
<li>Approving here drives the approval inside ERPNext. The control lives in the system that holds the
money, not in this dashboard.</li>
<li>Every decision is taken in ERPNext under your own account, so the document&#39;s own history records
who decided, what they decided and when.</li></ul></div>'''

# ---------------- V: DELEGATION ----------------
V_DELEG=f'''<div class="topbar"><div><h3>Outstanding Tasks</h3>
<div class="when">Reading the work you handed out&hellip;</div></div></div>
<div class="grid" style="grid-template-columns:repeat(4,1fr)">
<div class="bk"><div class="n">—</div><div class="l">Still open</div><div class="v">work you handed out</div></div>
<div class="bk"><div class="n">—</div><div class="l">Late</div><div class="v">past the date you set</div></div>
<div class="bk"><div class="n">—</div><div class="l">Reopened twice+</div><div class="v">sent back more than once</div></div>
<div class="bk"><div class="n">—</div><div class="l">High risk</div><div class="v">marked high priority</div></div></div>
<div class="note"><h4>Where the work actually happens</h4><ul>
<li>This platform is for management. <b>The people you hand work to do not need a login here.</b></li>
<li>Each task is a To-Do in ERPNext, where they already work, and they mark it done there.
Only the decision to accept or reject it happens on this screen.</li></ul></div>'''
