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
# A check-up report (16 Nov 2026, approved mockup-health.html): the verdict, then the six
# questions as ruled findings, worst first, each with what it was counted from and its
# last eight weeks. Every figure is the one the screen always showed (legacy/home.js
# renderHealthTiles; kpi score_* and live_governance score_*); the weeks are the stored
# snapshots (command_center/health.py). Nothing here is drawn as a sample: each row says
# "Reading" until its figure arrives. Styled in shell.py (.hh-*).
fams=[("score_deliver","Can we deliver what we sold?"),("score_paid","Are we getting paid?"),
 ("score_paperwork","Is the paperwork finished?"),("score_approvals","Were the right people asked?"),
 ("score_records","Are our records clean?"),("score_access","Who can see what?")]
_sq='<span class="hh-wk"></span>'*8
fh="".join(f'''<div class="hh-row" data-q="{k}"><span class="hh-sq" aria-hidden="true"></span>
<div class="hh-q"><div class="l">{nm}</div><div class="hh-n">Reading&hellip;</div><div class="hh-src"></div></div>
<div class="hh-strip" role="img" aria-label="Last eight weeks: reading">{_sq}</div>
<div class="hh-now">&mdash;</div><span class="flag f-dim hh-status">Reading</span></div>''' for k,nm in fams)

V_HEALTH=f'''<div class="topbar"><div><h3>Business Health</h3>
<div class="when">Six questions, asked of the business every morning</div></div></div>
<div class="hh-report"><div class="hh-verdict">
<div class="hh-gauge"><div class="hh-ring" id="hh-ring"><div class="hh-ring-n" id="hh-score">&mdash;</div></div>
<div class="hh-cap">Overall Business Health</div><div class="hh-delta" id="hh-delta" hidden></div></div>
<div class="hh-word"><p class="hh-say" id="hh-say">Working it out&hellip;</p>
<p class="hh-note">This is not a score about the software.
It measures whether the records the business runs on can be trusted this week.</p>
<div class="hh-tally" id="hh-count"></div>
<p class="hh-trend" id="hh-trend">&nbsp;</p></div></div>
<p class="hh-assure"><span class="hh-seal" aria-hidden="true"></span>Every figure here is counted from your own ERPNext records &mdash; nothing is estimated or made up.</p></div>
<div class="hh-findings"><div class="hh-row hh-cols" aria-hidden="true"><span></span><span>The six questions, worst first</span>
<span>Last 8 weeks</span><span>Now</span><span></span></div>
<div class="hh-list" id="hh-rows">{fh}</div>
<p class="hh-legend" id="hh-legend">Each square is one week, the last reading that week, oldest on the left; an outlined square is a week with nothing stored yet.</p></div>
<div class="panel loads" id="loads"><div class="loads-h"><div><h4>The data behind these figures</h4>
<p id="loads-sub">When each kind of record was last read from ERPNext</p></div>
<button type="button" class="btn pri" id="loads-refresh">Refresh now</button></div>
<div id="loads-facts"><div class="home-wait">Reading the load history…</div></div>
<button type="button" class="lnk loads-more" id="loads-more" aria-expanded="false">Show the load history</button>
<div id="loads-hist" hidden></div></div>
<div class="sect" style="margin-top:20px"><span>What is going wrong, largest first</span></div>
<div class="alert-live-list"><div class="work-empty"><b>Reading the alerts&hellip;</b></div></div>
<div class="note" id="hh-ask" hidden><h4>What you would be asked first</h4><ul></ul></div>'''
