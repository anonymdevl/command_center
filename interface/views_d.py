# -*- coding: utf-8 -*-
exec(_src('views_c.py'))
exec(_src('statements.py'))

# ============ FINANCE ============
V_FIN=f'''<div class="topbar"><div><h3>Finances</h3>
<div class="when">General Ledger</div></div></div>
{fs_block()}
<div class="kpis six ribbon">
{kpi("Accounts Receivable","—","","","flat","","ar")}
{kpi("Unpaid Sales Invoices","—","","","flat","","ar")}
{kpi("Invoiced, Last Full Month","—","","","flat","","rev")}
{kpi("Best Month Invoiced","—","","","flat","","rev")}
{kpi("Draft Sales Invoices","—","","","flat","","drafts")}
{kpi("Bank Reconciled","—","","","flat","","bank")}
</div>
<div class="two">
{panel("Payments Received", trend0(155),
 "Monthly","rev")}
{panel("Working Capital Tied Up",
 bars0()+thin("Receivables over 90 days, Stock Value and Sales Orders To Deliver."),
 "","workingcap")}
</div>
{warn0()}
{warn0()}
{panel("Accounts Receivable and Payable",
 '<div class="dt-scroll">'+dtable(["Party",("Invoice Outstanding$",True),("Party Ledger Balance$",True),("Difference$",True),"Why",
 ("Not Yet Due",True),("1–30 Days",True),("31–60 Days",True),("61–90 Days",True),("Over 90 Days",True)])+'</div>',
 "Party Ledger Balance vs Invoice Outstanding","ledger")}
<div class="two">
{panel("Accounts Payable Ageing", thin("<b>Supplier Ledger Balance by Due Date:</b> overdue, and due in 7, 30 and 60 days, after unreconciled payments are set against the oldest Purchase Invoices, against what customers are due to pay."))}
{panel("Bank and Cash Balances", thin("<b>General Ledger balance of every Account with Account Type Bank or Cash, with its last Bank Reconciliation.</b>"))}
</div>
<div class="two">
{panel("Budget Variance", thin("<b>Actual against each Budget line for this Fiscal Year.</b>"))}
{panel("Tax Account Balances", thin("<b>General Ledger balance of each Account with Account Type Tax.</b> Filing dates are not kept in ERPNext."))}
</div>
{panel("Gross Profit by Item Group", thin("<b>Gross Profit by Item Group, last 12 months.</b> Lines with no Valuation Rate are shown separately."))}'''

# ============ HR ============
# People Lookup and Leave are not chart panels: frontend/src/legacy/people.js draws them
# from api/people.py (search, the profile in the drawer, every balance). They are
# .ppanel, not .panel, so the panels' renderer (legacy/panels.js) leaves them alone.
def pp_section(key, title, sub):
    return (f'<div class="ppanel" data-pp="{key}"><div class="ph"><div><b>{title}</b>'
            f'<span>{sub}</span></div></div><div class="pp-body"></div></div>')

HR_LOOKUP = pp_section("lookup", "People Lookup",
    "Search Employees, then open their profile")
HR_LEAVE = ('<div class="two">'
    + pp_section("away", "Away Today and This Week", "Approved Leave Applications")
    + pp_section("pending", "Waiting for Approval", "Open Leave Applications, longest wait first")
    + '</div>'
    + pp_section("balances", "Leave Balances", "Employee Leave Balance, by Leave Type")
    + pp_section("bydept", "Leave Taken by Department", "Days taken this year, to date"))

V_HR=f'''<div class="topbar"><div><h3>HR &amp; Payroll</h3>
<div class="when">All Employees · pay is never read here</div></div></div>
<div class="banner"><b>Pay is never read by this screen.</b> It shows people by department, branch and
standing, and when payroll was last run &mdash; never what anyone is paid. Salary records stay in ERPNext,
under its own permissions.</div>
<div class="kpis six">
{kpi("All Employees","—","","","flat","","head")}
{kpi("Active","—","","","flat","","head")}
{kpi("Left","—","","","flat","","turnover")}
{kpi("Departments","—","","","flat","","depts")}
{kpi("Engineers","—","","","flat","","capacity")}
{kpi("Payroll","—","","","flat","","payroll")}
</div>
<div class="tabbar" data-g="thr">
<button class="tab on" onclick="tab(this,&#39;thr&#39;,0)">Overview</button>
<button class="tab" onclick="tab(this,&#39;thr&#39;,1)">People</button>
<button class="tab" onclick="tab(this,&#39;thr&#39;,2)">Leave</button>
<button class="tab" onclick="tab(this,&#39;thr&#39;,3)">Detail</button></div>
<div class="tabpane on" data-g="thr" data-i="0">
<div class="two">
{panel("Employees by Department", bars0(),
 "","depts")}
{panel("Employees by Branch and Status", bars0()
 +'<div style="margin-top:12px">'+stacked([("Active",0,"var(--ok)"),("Inactive",0,"var(--med)"),("Left",0,"var(--crit)")])+'</div>',"","head")}
</div>
{warn0()}
</div>
<div class="tabpane" data-g="thr" data-i="1">
{HR_LOOKUP}
</div>
<div class="tabpane" data-g="thr" data-i="2">
{HR_LEAVE}
</div>
<div class="tabpane" data-g="thr" data-i="3">
<div class="two">
{panel("Duplicate Departments",
 '<ul class="bul"></ul>'
 +thin("Departments whose names suggest the same department typed twice. Headcount by department cannot be counted reliably until they are merged."),"","depts")}
{panel("Appraisals and Training", thin("<b>Reviews completed and training held, over the last twelve months.</b> For engineers working on medical equipment, a lapsed review or certificate is a compliance matter, not an HR nicety."))}
</div>
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
 +thin("The platform reads what changed in ERPNext every two minutes and everything again once a week; open screens refresh themselves every minute."),"")}
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
