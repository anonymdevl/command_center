# -*- coding: utf-8 -*-
exec(_src('p2.py'))

# ---------------- V: SALES ----------------
buck=[("2","Awaiting stock","GHS 18,450"),("1","Awaiting purchase","GHS 65,100"),
 ("4","Awaiting despatch","GHS 84,950"),("4","Awaiting invoice","GHS 84,950"),
 ("0","Awaiting install","—"),("4","Awaiting payment","GHS 13,537")]
bh="".join(f'<div class="bk"><div class="n">{n}</div><div class="l">{l}</div><div class="v">{v}</div></div>' for n,l,v in buck)
orows=""
for nm,c,amt in [("SAL-ORD-2025-00910","EJURA MUNICIPAL HOSPITAL",65100),
                 ("SAL-ORD-2025-00909","ROSSY'S SUPPLY",16700),
                 ("SAL-ORD-2025-00906-1","ST MARYS HOSPITAL (DROBO)",1750),
                 ("SAL-ORD-2025-00907","LILIAN ACHIAA",1400)]:
    dr="openDrawer('ejura')" if "00910" in nm else "openDrawer('order')"
    orows+=f'''<tr><td><span class="lnk" onclick="{dr}">{nm}</span></td><td>{c}</td>
<td class="num">{g(amt)}</td><td><span class="tag t-wt">Not despatched</span></td>
<td class="num" style="color:var(--dim)">None of it</td></tr>'''
arrows="".join(f'''<tr><td>{c}</td><td class="num" style="color:var(--dim)">—</td>
<td class="num" style="color:var(--dim)">—</td><td class="num" style="color:var(--dim)">—</td>
<td class="num" style="color:var(--crit)">{g(v)}</td><td class="num">{g(v)}</td></tr>''' for c,v in AR)

V_SALES=f'''<div class="topbar"><div><h3>Sales and money owed to us</h3>
<div class="when">7,765 invoices · 911 orders · 806 still unpaid</div></div></div>
<div class="kpis" style="grid-template-columns:repeat(5,1fr)">
{kpi("Owed to us","9.18","M GHS","74% over 3 months late","dn")}
{kpi("Unpaid invoices","806","","GHS 9.18M between them","dn")}
{kpi("Not despatched","4","","GHS 84,950","dn")}
{kpi("Largest debt","737","k GHS","HAIRASH ENTERPRISE","dn")}
{kpi("Never issued","88","","not in any total","flat")}
</div>
<div class="sect">Where orders are held up</div>
<div class="grid" style="grid-template-columns:repeat(6,1fr)">{bh}</div>
<div class="sect" style="margin-top:20px">Orders taken but not yet despatched</div>
<table class="dt"><thead><tr><th>Order</th><th>Customer</th><th style="text-align:right">Value GHS</th>
<th>Status</th><th style="text-align:right">Despatched</th></tr></thead><tbody>{orows}</tbody></table>
<div class="sect" style="margin-top:20px">Who owes us money, and for how long</div>
<table class="dt"><thead><tr><th>Customer</th><th style="text-align:right">Under 1 month</th>
<th style="text-align:right">1–2 months</th><th style="text-align:right">2–3 months</th>
<th style="text-align:right">Over 3 months</th><th style="text-align:right">Total GHS</th></tr></thead>
<tbody>{arrows}<tr style="border-top:2px solid var(--line2)">
<td><b>Ten largest</b></td>
<td class="num" style="color:var(--dim)">—</td><td class="num" style="color:var(--dim)">—</td>
<td class="num" style="color:var(--dim)">—</td><td class="num" style="color:var(--crit)"><b>4,592,482</b></td>
<td class="num"><b>4,592,482</b></td></tr>
<tr style="border-top:1px solid var(--line2)"><td><b>All 806 unpaid invoices</b></td>
<td class="num">499,078</td><td class="num">1,511,117</td><td class="num">390,231</td>
<td class="num" style="color:var(--crit)"><b>6,777,143</b></td>
<td class="num"><b>9,177,569</b></td></tr></tbody></table>
<div class="warn"><b>Almost three quarters of the money is beyond three months.</b> GHS 6.78M of the
GHS 9.18M owed has been outstanding more than ninety days. The remaining GHS 2.40M, across 159
invoices, is still inside that window — so collection has slowed badly rather than stopped.
<br><br>The ten largest customers alone account for GHS 4.59M, exactly half of everything owed.
That concentration is its own risk: a payment plan with ten hospitals moves half the balance.
<br><br><b>Ageing is measured as at 19 August 2025</b>, the last date this data covers. Measured
against today it would all fall into the oldest band, which would say nothing about how they
collect.</div>'''

# ---------------- V: HEALTH ----------------
fams=[("Can we deliver what we sold?",38,"high","491 products reserved but unavailable"),
 ("Are we getting paid?",22,"crit","GHS 9.18M owed, 74% over three months"),
 ("Is the paperwork finished?",71,"med","88 invoices written but never issued"),
 ("Were the right people asked?",31,"crit","Approvals completed by whoever raised them"),
 ("Are our records clean?",None,"na","Not yet reviewed"),
 ("Who can see what?",None,"na","Starts measuring at go-live")]
fh=""
for nm,sc,sev,note in fams:
    if sc is None:
        val='<span style="color:var(--dim)">\u2014</span>'
        bar='<div class="bar"></div>'
        flag='<span class="flag f-dim">Not scored</span>'
    else:
        col={"crit":"var(--crit)","high":"var(--high)","med":"var(--med)"}[sev]
        val=f'<span style="color:{col}">{sc}</span><small>/100</small>'
        bar=f'<div class="bar"><i style="width:{sc}%;background:{col}"></i></div>'
        flag={"crit":'<span class="flag f-crit">Critical</span>',
              "high":'<span class="flag f-high">High</span>',
              "med":'<span class="flag f-med">Watch</span>'}[sev]
    fh+=f'''<div class="bk q">
<div class="khead"><div class="l">{nm}</div>{flag}</div>
<div class="n">{val}</div>{bar}<div class="v">{note}</div></div>'''

V_HEALTH=f'''<div class="topbar"><div><h3>Control Health</h3>
<div class="when">Six questions, asked of the business every morning</div></div></div>
<div style="display:grid;grid-template-columns:190px 1fr;gap:16px;align-items:center;
background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--crit);
border-radius:10px;padding:16px 18px;margin-bottom:16px">
<div style="text-align:center"><div style="font-size:42px;font-weight:700;color:var(--crit);line-height:1">39</div>
<div style="font-size:10.5px;color:var(--dim);letter-spacing:.06em;text-transform:uppercase;margin-top:2px">Control health</div>
<div style="font-size:10.5px;color:var(--crit);margin-top:5px">▼ 6 since last week</div></div>
<div><div style="font-size:13.5px;line-height:1.6">Three things are going badly.
<b>We cannot reliably deliver what we have sold</b> — 491 products are promised to customers but not
on the shelf, and a third of everything we own is not in any warehouse.
<b>We are not being paid</b> — the full GHS 9.18M owed is more than three months late, with nothing at
all in the earlier stages. <b>And approvals are being completed by whoever raised them</b> — the
four-stage check on purchase orders exists, and the change history shows single accounts walking
straight through it in seconds.</div>
<div style="font-size:11.5px;color:var(--mut);margin-top:9px">This is not a score about the software.
It measures whether the records the business runs on can be trusted this week.</div></div></div>
<div class="sect">The six questions</div>
<div class="grid" style="grid-template-columns:repeat(3,1fr);gap:10px">{fh}</div>
<div class="sect" style="margin-top:20px"><span>What is going wrong, largest first</span></div>
{alert("crit","We have promised customers stock we do not physically have, across 491 products",
 "Any of those orders can fail the moment the warehouse goes to pick it.",
 "Freeze new commitments on the worst lines until a count is done.",
 "491","products","Stock position","Central, Kumasi, Accra","Stock Manager","ongoing","openDrawer('stock')",
 ["Assign","Request evidence","Raise as a finding","Defer","Escalate","Dismiss"])}
{alert("crit","We have committed 40,080 syringes to customers. There are 139 in the building.",
 "The same is true of 10ml syringes and infusion sets — everyday items we sell constantly.",
 "Stop quoting these lines until the count is confirmed.",
 "39,941","short","Stock position","Central Warehouse","Stock Manager","ongoing","openDrawer('stock')",
 ["Assign","Request evidence","Raise as a finding","Defer","Escalate","Dismiss"])}
{alert("high","Almost a third of everything we own is not in any warehouse",
 "GHS 1.18M of real equipment sits in a stock-adjustment account. Nobody can sell it from there.",
 "Decide where this equipment physically is, then move it onto a sellable location.",
 "1,175,920","GHS","Stock adjustment account","207 product lines","Stock Manager","unknown","openDrawer('recon')",
 ["Assign","Request evidence","Raise as a finding","Defer","Escalate","Dismiss"])}
{alert("crit","GHS 6.78M of the 9.18M owed is more than three months late",
 "Ten customers hold all of it. Nothing is sitting in the earlier stages.",
 "Pick the three largest and agree payment dates this week.",
 "6,777,143","GHS owed","Customer accounts","647 invoices","Finance","over 3 months","openDrawer('ar')",
 ["Assign","Request evidence","Raise as a finding","Defer","Escalate","Dismiss"])}
{alert("high","UBUNTU has been waiting for three installations since February last year",
 "The same hospital owes us GHS 636,675. We have not delivered and they have not paid — one story, not two.",
 "Send an engineer and open the payment conversation in the same call.",
 "636,675","GHS at risk","Projects","PROJ-0028 / 0029 / 0030","Engineering","19 months","openDrawer('ubuntu')",
 ["Assign","Request evidence","Raise as a finding","Defer","Escalate","Dismiss"])}
{alert("crit","Purchase orders are being approved by the person who raised them",
 "Gigmann already runs a four-stage check on purchases — operations manager, director, then chief executive. The change history shows single accounts completing all four stages in fourteen seconds.",
 "Decide who is genuinely separate from the requester, and set the approval routes to match.",
 "4","stages, one account","Purchase order","PUR-ORD-2025-00223","Nobody yet","19 Aug 2025","",
 ["Assign","Request evidence","Raise as a finding","Defer","Escalate","Dismiss"])}
{alert("med","88 invoices were written but never issued",
 "That revenue is in nobody's figures, and nobody is chasing it.",
 "Ask Sales to issue or void them by Friday.",
 "88","invoices","Unissued invoices","Sales","Sales","varies","",
 ["Assign","Request evidence","Raise as a finding","Defer","Escalate","Dismiss"])}
<div class="note"><h4>What you would be asked first</h4><ul>
<li>We have promised 40,080 syringes and hold 139. How did that happen?</li>
<li>Of the ten customers owing us GHS 9.18M, which has ever paid a bill that size?</li>
<li>Why is GHS 1.18M of equipment sitting outside every warehouse?</li></ul></div>'''
