# -*- coding: utf-8 -*-
exec(_src('views_c.py'))
exec(_src('statements.py'))

# ============ FINANCE ============
V_FIN=f'''<div class="topbar"><div><h3>Finances</h3>
<div class="when">Full ledger</div></div></div>
{fs_block()}
<div class="kpis six ribbon">
{kpi("Owed to us","—","","","flat","","ar")}
{kpi("Unpaid invoices","—","","","flat","","ar")}
{kpi("Last full month","—","","","flat","","rev")}
{kpi("Best month","—","","","flat","","rev")}
{kpi("Never issued","—","","","flat","","drafts")}
{kpi("Bank checks","—","","","flat","","bank")}
</div>
<div class="two">
{panel("Money coming in", trend0(155),
 "Monthly","rev")}
{panel("Working capital tied up",
 bars0()+thin("Money the business cannot presently use: debts over three months old, stock on the shelves and orders not yet despatched."),
 "","workingcap")}
</div>
{warn0()}
{warn0()}
{panel("Receivables and payables",
 '<div class="dt-scroll">'+dtable(["Customer or Supplier",("On Open Invoices$",True),("Ledger Balance$",True),("Difference$",True),"Why",
 ("Not Yet Due",True),("1–30 Days",True),("31–60 Days",True),("61–90 Days",True),("Over 90 Days",True)])+'</div>',
 "What each really owes by the ledger, beside the open invoices and bills","ledger")}
<div class="two">
{panel("What we owe suppliers", thin("<b>What the ledger says we owe suppliers, by when it falls due.</b> What is overdue and what falls due in the next 7, 30 and 60 days, after payments not yet matched are set against the oldest bills, against the cash customers are due to pay, so a payment run can be planned rather than guessed."))}
{panel("Cash and bank position", thin("<b>The balance on every bank and cash account in the ledger.</b> Each balance is only as good as the last time the account was checked against the bank statement, so that date is shown beside it."))}
</div>
<div class="two">
{panel("Budget against actual", thin("<b>Spending against the budgets set in ERPNext.</b> Each budget line is compared with what has been posted to it this year, so a breach shows before the money is spent rather than after."))}
{panel("Tax and statutory deadlines", thin("<b>What the ledger says is owed on each tax account.</b> The amount due on the next VAT, withholding or PAYE filing is the balance on its account; the filing dates themselves are not kept in ERPNext."))}
</div>
{panel("Profit on what we sell", thin("<b>What each product group earns over its cost, over the last twelve months.</b> Margin needs the cost of each item against its selling price; lines sold with no recorded cost are counted separately rather than as pure profit."))}'''

# ============ HR ============
# People Lookup and Leave are not chart panels: frontend/src/legacy/people.js draws them
# from api/people.py (search, the profile in the drawer, every balance). They are
# .ppanel, not .panel, so the panels' renderer (legacy/panels.js) leaves them alone.
def pp_section(key, title, sub):
    return (f'<div class="ppanel" data-pp="{key}"><div class="ph"><div><b>{title}</b>'
            f'<span>{sub}</span></div></div><div class="pp-body"></div></div>')

HR_LOOKUP = pp_section("lookup", "People Lookup",
    "Search anyone on the books, then open their profile")
HR_LEAVE = ('<div class="two">'
    + pp_section("away", "Away Today and This Week", "Approved leave, from the leave applications")
    + pp_section("pending", "Waiting for Approval", "Leave requests not yet approved, longest wait first")
    + '</div>'
    + pp_section("balances", "Leave Balances", "Every active person, by leave type, as ERPNext counts it")
    + pp_section("bydept", "Leave Taken by Department", "Days taken this year, to date"))

V_HR=f'''<div class="topbar"><div><h3>HR &amp; Payroll</h3>
<div class="when">Everyone on the books · pay is never read here</div></div></div>
<div class="banner"><b>Pay is never read by this screen.</b> It shows people by department, branch and
standing, and when payroll was last run &mdash; never what anyone is paid. Salary records stay in ERPNext,
under its own permissions.</div>
<div class="kpis six">
{kpi("On the books","—","","","flat","","head")}
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
{panel("Where people work", bars0(),
 "By department","depts")}
{panel("Where people are", bars0()
 +'<div style="margin-top:12px">'+stacked([("Active",0,"var(--ok)"),("Inactive",0,"var(--med)"),("Left",0,"var(--crit)")])+'</div>',"By branch, and standing","head")}
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
{panel("Departments are recorded inconsistently",
 '<ul class="bul"></ul>'
 +thin("Departments whose names suggest the same department typed twice. Headcount by department cannot be counted reliably until they are merged."),"","depts")}
{panel("Appraisals and training", thin("<b>Reviews completed and training held, over the last twelve months.</b> For engineers working on medical equipment, a lapsed review or certificate is a compliance matter, not an HR nicety."))}
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
