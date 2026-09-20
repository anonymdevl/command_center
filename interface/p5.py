# -*- coding: utf-8 -*-
exec(_src('p4.py'))

# ---------------- V: OPS ----------------
doms=[("Sales & money owed","7,765","invoices","GHS 9.18M owed, 74% over 3 months","live","sales"),
 ("Buying & suppliers","299","orders","Supplier terms not yet reviewed","live","proc"),
 ("Stock & warehouses","3.77","GHS M","Reserved but unavailable \u00b7 a third off warehouse","live","inv"),
 ("Engineering & installs","30","projects","Three UBUNTU jobs 19 months late","live","eng"),
 ("Customer complaints","11","cases","Seeded for the demonstration","seed","cx"),
 ("Money in & out","14,816","postings","Reconciliation status not confirmed","live","fin"),
 ("People","35","employees","Payroll shown as status only, names hidden","live","hr"),
 ("Systems & access","\u2014","","Measured here \u2014 ERPNext holds no record","none","it"),
 ("Internal audit","\u2014","","New capability, nothing to show yet","none","aud")]
dh=""
for name,fig,unit,note,state,key in doms:
    lab={"live":"Live data","seed":"Seeded","none":"Not yet"}[state]
    fcls={"live":"f-ok","seed":"f-med","none":"f-dim"}[state]
    if unit.startswith("GHS"):
        mag=unit[3:].strip()
        f_html=f'<span class="cx">GHS</span>{fig}' + (f'<span class="mag">{mag}</span>' if mag else "")
    else:
        f_html=f'{fig}' + (f' <small>{unit}</small>' if unit else "")
    dh+=f'''<div class="bk" onclick="go(&#39;{key}&#39;)">
<div class="khead"><div class="l">{name}</div><span class="flag {fcls}">{lab}</span></div>
<div class="n">{f_html}</div><div class="v">{note}</div></div>'''

V_OPS=f'''<div class="topbar"><div><h3>The whole business</h3>
<div class="when">Nine areas · open any one of them</div></div></div>
<div class="grid" style="grid-template-columns:repeat(3,1fr);gap:10px">{dh}</div>
<div class="warn"><b>Two areas are not really in ERPNext yet.</b> Customer complaints held no records at
all until we seeded eleven for this demonstration, and internal audit has no home in ERPNext — it arrives
with this platform. Engineering runs through Projects, but the installations there have no work
breakdown, no owners and no dates. Worth raising before anything is signed.</div>'''

# ---------------- V: ENGINEERING ----------------
V_ENG=f'''<div class="topbar"><div><h3>Engineering and installations</h3>
<div class="when">30 projects · run through the Projects module</div></div></div>
<div class="kpis" style="grid-template-columns:repeat(4,1fr)">
{kpi("Jobs open","14","")}
{kpi("Past their date","6","","oldest is 28 months","dn")}
{kpi("Nobody assigned","11","","of 14 open jobs","dn")}
{kpi("Value at risk","636","k GHS","UBUNTU alone","dn","","openDrawer('ubuntu')")}
</div>
<div class="sect">Jobs past the date we promised</div>
<table class="dt"><thead><tr><th>Job</th><th>Customer</th><th>Promised</th><th>Late by</th>
<th>Progress</th><th>Who owns it</th></tr></thead><tbody>
<tr><td><span class="lnk" onclick="openDrawer('ubuntu')">C-arm installation</span></td>
<td>UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL</td><td>28 Feb 2025</td>
<td style="color:var(--crit)">19 months</td><td>Not started</td><td style="color:var(--high)">Nobody</td></tr>
<tr><td><span class="lnk" onclick="openDrawer('ubuntu')">Theatre setup</span></td>
<td>UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL</td><td>28 Feb 2025</td>
<td style="color:var(--crit)">19 months</td><td>Not started</td><td style="color:var(--high)">Nobody</td></tr>
<tr><td><span class="lnk" onclick="openDrawer('ubuntu')">X-ray installation</span></td>
<td>UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL</td><td>28 Feb 2025</td>
<td style="color:var(--crit)">19 months</td><td>Not started</td><td style="color:var(--high)">Nobody</td></tr>
<tr><td>Lab setup</td><td>SAMKWARTH PHARMACEUTICAL LTD</td><td>20 May 2024</td>
<td style="color:var(--crit)">28 months</td><td>Not started</td><td style="color:var(--high)">Nobody</td></tr>
<tr><td>AGAHF maintenance and servicing</td><td>—</td><td>30 May 2024</td>
<td style="color:var(--crit)">28 months</td><td>56%</td><td style="color:var(--high)">Nobody</td></tr>
</tbody></table>
<div class="warn"><b>The same hospital appears twice in this business.</b> UBUNTU is waiting on three
installations we promised for February last year, and owes us GHS 636,675 that is more than three months
late. Until now those two facts have lived in different parts of the system and nobody has put them together.
<div class="acts"><button class="btn pri" onclick="openDrawer('ubuntu')">See both sides</button></div></div>
<div class="note"><h4>What the records look like underneath</h4><ul>
<li><b>Two jobs are recorded twice</b> — "COMPLETE X-RAY SET UP" and "COMPLTE X-RAY SET UP", same dates,
one a typing error.</li>
<li><b>Job types are typed in free hand</b> — "INSTALLATION", "Installation on Purchase",
"MAINTENANCE AND SERVICING" — so they cannot be counted reliably.</li>
<li><b>Finished jobs still show no progress</b>, and staff leaving the company create jobs in the same
list as customer installations.</li></ul></div>'''

# ---------------- V: CX ----------------
V_CX=f'''<div class="topbar"><div><h3>Customer complaints</h3>
<div class="when">11 cases · seeded for this demonstration</div></div></div>
<div class="banner"><b>These eleven cases were created by us</b> to show how the screen behaves.
Gigmann's ERPNext held no complaint records at all. The customer names are real; the complaints are not.</div>
<div class="kpis" style="grid-template-columns:repeat(4,1fr)">
{kpi("Open","6","","4 of them urgent","dn")}
{kpi("Past due time","6","","up to 3 weeks","dn")}
{kpi("Equipment down","2","","X-ray and autoclave","dn")}
{kpi("Closed","2","","resolved and closed","up")}
</div>
<div class="sect">Open, worst first</div>
<table class="dt"><thead><tr><th>Case</th><th>Customer</th><th>Raised</th><th>Waiting</th><th>Urgency</th></tr></thead><tbody>
<tr><td>X-ray generator tripping — unit down</td><td>ST JOHN OF GOD-SEFWI-ASAFO</td><td>12 Sep</td>
<td style="color:var(--crit)">7 days</td><td><span class="tag t-od">Urgent</span></td></tr>
<tr><td>Autoclave not reaching temperature</td><td>VINEYARD HOSPITAL</td><td>28 Aug</td>
<td style="color:var(--crit)">22 days</td><td><span class="tag t-od">Urgent</span></td></tr>
<tr><td>No response to installation follow-up</td><td>HAIRASH ENTERPRISE</td><td>25 Aug</td>
<td style="color:var(--crit)">25 days</td><td><span class="tag t-od">Urgent</span></td></tr>
<tr><td>Oxygen concentrator alarming</td><td>EJURA MUNICIPAL HOSPITAL</td><td>17 Sep</td>
<td style="color:var(--high)">2 days</td><td><span class="tag t-od">Urgent</span></td></tr>
<tr><td>Monitor probe failed under warranty</td><td>ILEE MEDICAL CENTRE</td><td>15 Sep</td>
<td>4 days</td><td><span class="tag t-wt">Normal</span></td></tr>
<tr><td>Refund requested — invoiced twice</td><td>KING JO MEDICAL SUPPLIES</td><td>1 Sep</td>
<td style="color:var(--high)">18 days</td><td><span class="tag t-wt">Normal</span></td></tr>
</tbody></table>
<div class="warn"><b>Three of these customers also owe us money.</b> HAIRASH owes GHS 737,544 and is
chasing us about an installation. That is worth knowing before anyone rings them about the debt.</div>'''
