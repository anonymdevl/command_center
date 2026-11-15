# -*- coding: utf-8 -*-
exec(_src('views_c.py'))

# ============ FINANCE ============
EXP=[90040]+[0]*3
V_FIN=f'''<div class="topbar"><div><h3>Finances</h3>
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
V_HR=f'''<div class="topbar"><div><h3>HR &amp; Payroll</h3>
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
# Every row and figure on this screen is read when it opens: the business's ERPNext
# accounts (api/panels.py), this platform's own people and its sign-in (api/panels_core.py).
# Nothing about any one business is written here.
def _tbl(*cols):
    th="".join(f'<th{" style=text-align:right" if c.startswith(">") else ""}>{c.lstrip(">")}</th>' for c in cols)
    return f'<table class="dt"><thead><tr>{th}</tr></thead><tbody></tbody></table>'

IT_OV=f'''{panel("Who can get into ERPNext today, and what they can do",
 _tbl("Person","Roles they hold",">How many","Separation of duties","Last seen")
 +thin("Read live from the business&#39;s ERPNext. A conflict is a pair of duties one account should "
 "not hold together, such as raising a purchase and approving its payment. None of this is an "
 "accusation; it is what the permission records currently say."),
 "Reading the accounts&hellip;","access")}
<div class="warn" hidden></div>'''

IT_DETAIL=f'''{panel("Who can sign in to this platform",
 _tbl("Person","Access here","Status","Last signed in")
 +thin("This platform has its own sign-in, separate from ERPNext. Only the people listed here can open it, "
 "and only an administrator can add or remove them, under Settings &rarr; People."),
 "Reading the platform&#39;s people&hellip;","identity")}
{panel("How signing in works",
 '<table class="dt"><thead><tr><th style="width:190px">Rule</th><th>What it does</th></tr></thead><tbody>'
 '<tr><td>Its own accounts</td><td>Each person signs in with their email and a password of at least ten characters. An ERPNext login does not open this platform.</td></tr>'
 '<tr><td>Managers</td><td>See every screen for the businesses connected here, and act only in ERPNext under their own linked key.</td></tr>'
 '<tr><td>Administrators</td><td>Also manage the people, the businesses, the keys and the alert rules.</td></tr>'
 '<tr><td>Failed attempts</td><td>Five wrong passwords for one account from one address lock that pair out for fifteen minutes; twenty from one address, or for one account, lock those out too.</td></tr>'
 '<tr><td>Sessions</td><td>A sign-in lasts twelve hours unless the platform is set otherwise; deactivating a person ends their sessions at once.</td></tr>'
 '</tbody></table>',"","identity")}
{panel("Accounts that are switched off",
 _tbl("Person","Roles still attached",">How many","Status","Last seen")
 +thin("A switched-off ERPNext account cannot sign in, but its roles stay attached, so re-enabling it restores everything it had."),
 "Reading the accounts&hellip;","access")}
{panel("This platform&#39;s own access",
 _tbl("Role",">People","What they can reach"),"","access")}'''

IT_GAPS=f'''<div class="two">
{panel("Is the data current",
 _tbl("Records","Covers up to","Last read","Status")
 +thin("The platform reads what changed in ERPNext every fifteen minutes and everything again once a week."),"")}
{panel("Backups and recovery",
 _tbl("Backup","Taken","Size")
 +thin("The platform&#39;s own database is backed up every night and the last fourteen days are kept. "
 "Copy them off the server now and then: a backup kept on the same machine is lost with it."),"")}
</div>'''

V_IT=('<div class="topbar"><div><h3>Systems and Access</h3>'
 '<div class="when">Read live from ERPNext and from this platform</div></div></div>'
 +f'''<div class="kpis six">
{kpi("Staff accounts","—","","","flat","","access")}
{kpi("Role conflicts","—","","","flat","","conflicts")}
{kpi("5 manager roles","—","","","flat","","roles5")}
{kpi("Departments","—","","","flat","","depts")}
{kpi("Disabled","—","","","flat","","disabled")}
{kpi("Last refreshed","—","","","flat","","fresh")}
</div>'''
 +'<div class="tabbar" data-g="tit">'
 '<button class="tab on" onclick="tab(this,&#39;tit&#39;,0)">Who can get in</button>'
 '<button class="tab" onclick="tab(this,&#39;tit&#39;,1)">This platform</button>'
 '<button class="tab" onclick="tab(this,&#39;tit&#39;,2)">Data and backups</button></div>'
 '<div class="tabpane on" data-g="tit" data-i="0">'+IT_OV+'</div>'
 '<div class="tabpane" data-g="tit" data-i="1">'+IT_DETAIL+'</div>'
 '<div class="tabpane" data-g="tit" data-i="2">'+IT_GAPS+'</div>')
