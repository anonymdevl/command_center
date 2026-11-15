# -*- coding: utf-8 -*-
exec(_src('views_c.py'))

# ============ FINANCE ============
V_FIN=f'''<div class="topbar"><div><h3>Finances</h3>
<div class="when">Full ledger</div></div></div>
<div class="kpis six">
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
<div class="two">
{panel("What we owe suppliers", thin("<b>Unpaid supplier invoices by when they fall due.</b> What is overdue and what falls due in the next 7, 30 and 60 days, against the cash customers are due to pay, so a payment run can be planned rather than guessed."))}
{panel("Cash and bank position", thin("<b>The balance on every bank and cash account in the ledger.</b> Each balance is only as good as the last time the account was checked against the bank statement, so that date is shown beside it."))}
</div>
<div class="two">
{panel("Budget against actual", thin("<b>Spending against the budgets set in ERPNext.</b> Each budget line is compared with what has been posted to it this year, so a breach shows before the money is spent rather than after."))}
{panel("Tax and statutory deadlines", thin("<b>What the ledger says is owed on each tax account.</b> The amount due on the next VAT, withholding or PAYE filing is the balance on its account; the filing dates themselves are not kept in ERPNext."))}
</div>
{panel("Profit on what we sell", thin("<b>What each product group earns over its cost, over the last twelve months.</b> Margin needs the cost of each item against its selling price; lines sold with no recorded cost are counted separately rather than as pure profit."))}'''

# ============ HR ============
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
<div class="two">
{panel("Where people work", bars0(),
 "By department","depts")}
{panel("Where people are", bars0()
 +'<div style="margin-top:12px">'+stacked([("Active",0,"var(--ok)"),("Inactive",0,"var(--med)"),("Left",0,"var(--crit)")])+'</div>',"By branch, and standing","head")}
</div>
{warn0()}
<div class="two">
{panel("Departments are recorded inconsistently",
 '<ul class="bul"></ul>'
 +thin("Departments whose names suggest the same department typed twice. Headcount by department cannot be counted reliably until they are merged."),"","depts")}
{panel("One person, everything about them",
 thin("<b>How much of each person's record ERPNext holds.</b> A single view of an employee is only as complete as what is recorded against them: a login, leave, attendance and appraisals."))}
</div>
<div class="two">
{panel("Leave and attendance", thin("<b>Who is off, what is waiting for approval, and absence marked.</b> From the leave applications and attendance recorded in ERPNext."))}
{panel("Appraisals and training", thin("<b>Reviews completed and training held, over the last twelve months.</b> For engineers working on medical equipment, a lapsed review or certificate is a compliance matter, not an HR nicety."))}
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
 +thin("<b>Seven accounts, all management.</b> No general staff login exists. Outstanding Tasks reaches people "
 "in ERPNext, where they already are."),"","access")}'''

IT_GAPS=f'''<div class="two">
{panel("Is the data current", thin("<b>This copy is deliberately behind.</b> It was taken to 19 August 2025. In service the platform reads changes every few minutes and states on every screen how fresh the figures are."))}
{panel("Backups and recovery", thin("<b>Starts at go-live.</b> Last successful backup, last restore actually tested, and how long it took. A backup that has never been restored is not a backup."))}
</div>'''

V_IT=('<div class="topbar"><div><h3>Systems and Access</h3>'
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
