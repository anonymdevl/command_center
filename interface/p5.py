# -*- coding: utf-8 -*-
exec(_src('p4.py'))

# ---------------- V: OPS ----------------
# Every figure is read when the screen opens (TILE_KPIS.ops in legacy/hydrate.js); the
# footnotes say what each counts. Nothing about any one business is written here.
doms=[("Sales & money owed","owed to us","sales"),
 ("Buying & suppliers","owed to suppliers","proc"),
 ("Stock & warehouses","value on hand","inv"),
 ("Engineering & installs","open jobs","eng"),
 ("Customer Service &amp; Issues","open complaints and service cases","cx"),
 ("Money in & out","payments and journals","fin"),
 ("People","everyone on the books","hr"),
 ("Systems & access","active ERPNext accounts","it"),
 ("Internal Audit","open alerts to review","aud")]
dh=""
for name,note,key in doms:
    dh+=f'''<div class="bk" data-dept="{key}" onclick="go(&#39;{key}&#39;)">
<div class="khead"><div class="l">{name}</div><span class="flag f-ok">Live data</span></div>
<div class="n">—</div><div class="v">{note}</div></div>'''

# The front page (16 Nov 2026, the approved mockup's B over A): the area that most needs
# attention leads, the next three stand beside it, and the rest are a ruled register.
# The nine tiles are the same tiles as before -- same labels, figures, flags and go()
# -- and start in the register; legacy/overview.js moves each into its place once the
# figures and the open alerts are read. It moves them, never copies or rebuilds them,
# so everything hydrate.js and core.js write into a tile stays where it is.
V_OPS=f'''<div class="topbar"><div><h3>Business Overview</h3>
<div class="when">Nine areas · open any one of them</div></div></div>
<div class="ov" id="ov">
<div class="ov-front"><div class="ov-lead" id="ov-lead"></div><div class="ov-sec" id="ov-sec"></div></div>
<div class="ov-reg"><div class="ov-rows" id="ov-rows"><div class="ov-rh" aria-hidden="true">
<span>Department</span><span>Headline</span><span>Status</span><span>What It Says</span></div>
{dh}</div></div></div>
<div class="warn" hidden></div>'''

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
