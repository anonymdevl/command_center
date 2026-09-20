# -*- coding: utf-8 -*-
exec(_src('views_c.py'))

# ============ FINANCE ============
EXP=[90040]+[0]*3
V_FIN=f'''<div class="topbar"><div><h3>Money in and out</h3>
<div class="when">Full ledger · GHS · to 19 August 2025</div></div></div>
<div class="kpis six">
{kpi("Owed to us","9.18","M GHS","74% over 3 months late","dn","","ar")}
{kpi("Unpaid invoices","806","","GHS 9.18M between them","dn","","ar")}
{kpi("Last full month","1.55","M GHS","July 2025","up","","rev")}
{kpi("Best month","3.19","M GHS","June 2025","up","","rev")}
{kpi("Never issued","88","","not in any total","flat","","drafts")}
{kpi("Bank checks","—","","status not confirmed","flat","review","bank")}
</div>
<div class="two">
{panel("Money coming in", line_chart(REV_LABELS,[{"data":REV}],h=155,fmt=lambda v:'GHS '+g(v)),
 "Monthly, eleven months to August 2025","rev")}
{panel("Working capital tied up",
 bar_chart([("Owed to us, over 3 months",4592482,"var(--crit)"),
            ("Stock outside any warehouse",1175920,"var(--crit)"),
            ("Stock in warehouses",2594050,"var(--accent)"),
            ("Orders taken, not despatched",84950,"var(--high)")],fmt=lambda v:g(v))
 +thin("<b>GHS 5.77M is money the business cannot presently use</b> — debts over three months old plus equipment parked outside every warehouse. Against a stock holding of GHS 3.77M, that is the number worth moving."),
 "GHS","workingcap")}
</div>
<div class="two">
{panel("What we owe suppliers", thin("<b>Not summarised in this demo extract.</b> The finished screen shows what is due in the next 7, 30 and 60 days against the cash expected in, so a payment run can be planned rather than guessed."))}
{panel("Cash and bank position", thin("<b>Present in the ledger, not yet confirmed.</b> Balances exist, but whether the bank accounts have recently been checked against them is unknown — and every cash figure on this platform depends on that answer. It is the first thing to establish."))}
</div>
<div class="two">
{panel("Budget against actual", thin("<b>No budgets recorded in this demo extract.</b> Once budgets are set by department the finished screen shows variance with the entries behind it, and flags a breach before the spend happens rather than after."))}
{panel("Tax and statutory deadlines", thin("<b>Not tracked anywhere in the system today.</b> VAT, import duty and filing dates live in people's heads. The finished screen carries them with owners and reminders."))}
</div>
{panel("Profit on what we sell", thin("<b>Cannot be calculated from this demo extract.</b> Margin needs the cost of each item against its selling price. Costs are held, but no engineering job carries a cost at all, so service margin is invisible — that is the gap worth closing first, because installations are where margin usually leaks."))}'''

# ============ HR ============
V_HR=f'''<div class="topbar"><div><h3>People</h3>
<div class="when">35 on the books · 24 active · names and pay hidden unless you hold HR</div></div></div>
<div class="banner"><b>You are seeing this as Chief Executive.</b> Individual names, salaries and conduct
records are hidden from every role except HR. The assistant cannot read them on your behalf either —
it is not told to decline, the information never reaches it.</div>
<div class="kpis six">
{kpi("On the books","35","","all employment records","flat","","head")}
{kpi("Active","24","","of 35 on the books","flat","","head")}
{kpi("Left","8","","7 months average stay","dn","review","turnover")}
{kpi("Departments","10","","some duplicated","flat","review","depts")}
{kpi("Engineers","3","","for the whole country","dn","","capacity")}
{kpi("Payroll","—","","status only, never calculated here","flat","","payroll")}
</div>
<div class="two">
{panel("Where people work", bar_chart([(d,n,"var(--accent)") for d,n in DEPTS],fmt=lambda v:g(v)),
 "By department","depts")}
{panel("Where people are", bar_chart([(b,n,"var(--accent)") for b,n in BRANCH],fmt=lambda v:g(v))
 +'<div style="margin-top:12px">'+stacked(STAFF)+'</div>',"By branch, and standing","head")}
</div>
<div class="warn"><b>Eight of thirty-five have left — close to a quarter of the payroll.</b> Customer
Service has lost the most. The company also employs only three engineers, all titled sales engineers,
which is worth holding next to the three installations that are nineteen months late.</div>
<div class="two">
{panel("Departments are recorded inconsistently",
 '<ul class="bul"><li>"Operations Dept" and "Operations  - GMSL" are the same department, typed twice.</li>'
 '<li>"Procurement &amp; Inventory - GMSL" and "Procurement Inventory &amp; Logistics Department - GMSL" likewise.</li>'
 '<li>"Medical Engineering Dept" and "PROJECT AND ENGINEERING DEPT - GMSL" appear to overlap.</li></ul>'
 +thin("Headcount by department cannot be counted reliably until these are merged. It is an hour of tidying that makes every HR figure trustworthy."),"","depts")}
{panel("One person, everything about them",
 thin("<b>The finished screen gives a single view per employee</b> — role, branch, start date, leave taken and left, attendance exceptions, appraisal history, training and certificates with expiry, equipment issued, system access, and the documents on file. "
 "It opens only for HR and the CEO, and logs who looked. This demo extract holds employment records and exit paperwork but no leave, attendance or appraisal entries, so there is nothing to populate it with here."))}
</div>
<div class="two">
{panel("Leave and attendance", thin("<b>No leave or attendance records in this demo extract.</b> The finished screen shows who is off this week, unapproved absence, overtime outside policy, and leave balances that will be lost at year end."))}
{panel("Appraisals and training", thin("<b>No appraisal records in this demo extract.</b> The finished screen tracks review completion by department, flags overdue reviews, and warns before a professional certificate expires — which for engineers working on medical equipment is a compliance matter, not an HR nicety."))}
</div>'''

# ============ IT ============
IT_OV=f'''{panel("Who can get into ERPNext today, and what they can do",
 '<table class="dt"><thead><tr><th>Person</th><th>Roles they hold</th><th style="text-align:right">How many</th>'
 '<th>Separation of duties</th><th>Last seen</th></tr></thead><tbody>'+user_rows()+'</tbody></table>'
 +thin("Read live from their ERPNext. <b>Three active accounts hold role combinations that let one person "
 "both start a transaction and approve it.</b> None of this is an accusation; it is what the permission "
 "records currently say."),
 "13 active Gigmann accounts","access")}
<div class="warn"><b>Simon Nketiah Sieh holds five manager roles across HR, finance, stock and buying.</b>
That single account can raise a purchase and approve its payment, adjust stock and post the accounting for
it, and change pay and approve paying it. In a company of 24 active staff some overlap is unavoidable &mdash;
but it should be a decision somebody took, not something nobody noticed.</div>'''

IT_DETAIL=f'''{panel("How the platform works out who you are",
 '<table class="dt"><thead><tr><th>Person</th><th>Where they work</th><th>Their ERPNext account</th>'
 '<th>What this platform gives them</th><th>Link</th></tr></thead><tbody>'+identity_rows()+'</tbody></table>'
 +thin("Nothing here is typed in by us. The platform reads the employee records for who does what and who "
 "reports to whom, then reads each linked account for what they are allowed to do, and works out access from "
 "the two. <b>Several people can hold the same access &mdash; it is not one person per role.</b>"),
 "Resolved live from ERPNext","identity")}
{panel("The rule it applies",
 '<table class="dt"><thead><tr><th style="width:190px">Access here</th><th>Is given to anyone who&hellip;</th></tr></thead><tbody>'
 +derive_rows()+'</tbody></table>'
 +thin("The rules are configuration, not code. If Gigmann wants Sales Managers to see buying as well, "
 "that is a line changed by an administrator, and the change is recorded."),"","identity")}
<div class="warn"><b>Only five of thirty-five employee records are linked to a login</b>, and the Chief
Executive is one of the thirty that are not. The platform can still tell you Samuel Damptey Adjei is the
Chief Executive &mdash; his record says so, and nobody sits above him in the reporting tree &mdash; but it
cannot let him sign in until his employee record and his account are joined up. That is one field per person.</div>
{panel("Accounts that are switched off",
 '<table class="dt"><thead><tr><th>Person</th><th>Roles still attached</th><th style="text-align:right">How many</th>'
 '<th>Status</th><th>Last seen</th></tr></thead><tbody>'+disabled_rows()+'</tbody></table>'
 +thin("<b>Offboarding is being done properly</b> &mdash; every departed person checked has had sign-in blocked. "
 "Worth knowing: the roles stay attached, so re-enabling an account restores everything it had. "
 "Sandra Oppong also appears twice under two addresses, which is a records problem rather than a security one."),
 "5 accounts","access")}
{panel("This platform&#39;s own access",
 '<table class="dt"><thead><tr><th>Role</th><th>People</th><th>What they can reach</th></tr></thead><tbody>'
 '<tr><td>Chief Executive</td><td>1</td><td>Everything</td></tr>'
 '<tr><td>Finance Director</td><td>1</td><td>Money, buying, stock, approvals</td></tr>'
 '<tr><td>Head of Sales</td><td>1</td><td>Sales, stock, engineering, complaints</td></tr>'
 '<tr><td>HR Director</td><td>1</td><td>People, including the restricted records</td></tr>'
 '<tr><td>Internal Audit</td><td>1</td><td>Read-only everywhere, plus the trail</td></tr>'
 '<tr><td>Platform administrator</td><td>2</td><td>Settings and thresholds &middot; approves nothing</td></tr>'
 '</tbody></table>'
 +thin("<b>Seven accounts, all management.</b> No general staff login exists. Work handed out reaches people "
 "in ERPNext, where they already are."),"","access")}'''

IT_GAPS=f'''<div class="two">
{panel("Is the data current", thin("<b>This copy is deliberately behind.</b> It was taken to 19 August 2025. In service the platform reads changes every few minutes and states on every screen how fresh the figures are."))}
{panel("Backups and recovery", thin("<b>Starts at go-live.</b> Last successful backup, last restore actually tested, and how long it took. A backup that has never been restored is not a backup."))}
</div>'''

V_IT=('<div class="topbar"><div><h3>Systems and access</h3>'
 '<div class="when">Read live from ERPNext &middot; 13 Gigmann accounts &middot; 3 with role conflicts</div></div></div>'
 +f'''<div class="kpis six">
{kpi("Staff accounts","13","","active in ERPNext","flat","","access")}
{kpi("Role conflicts","3","","one person, both sides","dn","review","conflicts")}
{kpi("5 manager roles","3","","of 13 accounts","dn","","roles5")}
{kpi("Departments","8","","across 3 branches","flat","","depts")}
{kpi("Disabled","4","","blocked correctly","up","","disabled")}
{kpi("Last refreshed","06:58","","this morning","flat","","fresh")}
</div>'''
 +'<div class="tabbar" data-g="tit">'
 '<button class="tab on" onclick="tab(this,&#39;tit&#39;,0)">Who can get in</button>'
 '<button class="tab" onclick="tab(this,&#39;tit&#39;,1)">Detail</button>'
 '<button class="tab" onclick="tab(this,&#39;tit&#39;,2)">Not yet measured</button></div>'
 '<div class="tabpane on" data-g="tit" data-i="0">'+IT_OV+'</div>'
 '<div class="tabpane" data-g="tit" data-i="1">'+IT_DETAIL+'</div>'
 '<div class="tabpane" data-g="tit" data-i="2">'+IT_GAPS+'</div>')
