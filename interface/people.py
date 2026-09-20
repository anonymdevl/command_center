# -*- coding: utf-8 -*-
# Real ERPNext users on the client's site, with the roles they actually hold.
USERS=[
 ("Simon Nketiah Sieh","symstars@gmail.com",1,"Mar 2026",
  ["HR Manager","Accounts Manager","Accounts User","Stock Manager","Purchase Manager"]),
 ("Samuel Opoku","kumasizonalmanager@gmail.com",1,"Apr 2026",
  ["Accounts Manager","Accounts User","Sales Manager","HR Manager","Projects Manager"]),
 ("Samuel Adjei","adjeisamueldamptey@gmail.com",1,"Aug 2025",
  ["Accounts User","HR Manager","Stock Manager","Purchase Manager","Projects Manager"]),
 ("Powersoft Helpdesk","demo@powersoftsystem.com",1,"Aug 2025",
  ["System Manager","HR Manager","Accounts Manager","Accounts User","Projects Manager"]),
 ("Solomon Adortsu","procurement.gigmed@gmail.com",1,"Sep 2025",["Stock Manager","Purchase Manager"]),
 ("Keziah Ackah-Blay","receivable.gigmed@gmail.com",1,"Aug 2025",["Accounts Manager","Accounts User"]),
 ("Grace Williams","sales.gigmed@gmail.com",1,"Aug 2025",["Sales Manager","Accounts User"]),
 ("Edith Viku","gigmannhr@gmail.com",1,"Mar 2026",["HR Manager"]),
 ("Alex Adjei","auditors.gigmed@gmail.com",1,"Aug 2025",["Auditor","Accounts Manager"]),
 ("John-Paul Iwuoha","consultants.gigmed@gmail.com",1,"Aug 2025",
  ["Purchase Manager","Accounts Manager","Accounts User","Projects Manager"]),
 ("Solomon Boateng","gigmannwarehouse@gmail.com",1,"Aug 2025",["Purchase Manager"]),
 ("Obed Asamoah","scrillex444@gmail.com",1,"Aug 2025",["Sales Manager","Purchase Manager","Projects Manager"]),
 ("Elijah Angsomwine","gigmed.payables@gmail.com",1,"Aug 2025",[]),
 ("Victoria Serwaa Asare-Kumah","kcs.gigmed@gmail.com",1,"Aug 2025",[]),
 ("Bright Yomaah","yomaahbright@gmail.com",0,"Jun 2025",
  ["Accounts Manager","HR Manager","Stock Manager","Purchase Manager","Accounts User"]),
 ("Thomas Billa","billay4k90@yahoo.com",0,"Mar 2024",["Stock Manager","Purchase Manager"]),
 ("Sandra Oppong","sandyoppong75@gmail.com",0,"Jul 2025",["Accounts User"]),
 ("Sandra Oppong","oppongkwame537@gmail.com",0,"Feb 2024",["Sales Manager","Accounts User"]),
 ("Michael","michael@powersoftsystem.com",0,"Jul 2024",
  ["Accounts Manager","Stock Manager","Auditor","Accounts User"]),
]
VENDOR={"demo@powersoftsystem.com","michael@powersoftsystem.com","Administrator"}
def is_vendor(em): return em in VENDOR or em.endswith("@powersoftsystem.com")

# Role pairs that should not sit on one person
SOD=[("Purchase Manager","Accounts Manager","can raise a purchase and approve its payment"),
     ("Stock Manager","Accounts Manager","can adjust stock and post the accounting for it"),
     ("HR Manager","Accounts Manager","can change pay and approve the payment of it")]

def sod_hits(roles):
    return [w for a,b,w in SOD if a in roles and b in roles]

def user_rows(enabled_only=True):
    out=""
    for nm,em,en,last,roles in USERS:
        if enabled_only and not en: continue
        if is_vendor(em): continue
        hits=sod_hits(roles)
        rs=" · ".join(roles) if roles else "<span style='color:var(--dim)'>none</span>"
        flag=(f'<span class="tag t-od">{len(hits)} conflict{"s" if len(hits)>1 else ""}</span>'
              if hits else ('<span class="tag t-ok">clear</span>' if roles else
                            '<span class="tag t-dr">no roles</span>'))
        note=("<div style='font-size:10.5px;color:var(--crit);margin-top:3px'>"
              +"; ".join(hits)+"</div>") if hits else ""
        out+=(f'<tr><td>{nm}<div style="font-size:10.5px;color:var(--dim)">{em}</div></td>'
              f'<td style="font-size:11.5px;color:var(--mut)">{rs}{note}</td>'
              f'<td class="num">{len(roles)}</td>'
              f'<td>{flag}</td><td style="color:var(--mut);white-space:nowrap">{last}</td></tr>')
    return out

def disabled_rows():
    out=""
    for nm,em,en,last,roles in USERS:
        if en: continue
        if is_vendor(em): continue
        out+=(f'<tr><td>{nm}<div style="font-size:10.5px;color:var(--dim)">{em}</div></td>'
              f'<td style="font-size:11.5px;color:var(--mut)">{" · ".join(roles) or "none"}</td>'
              f'<td class="num">{len(roles)}</td><td><span class="tag t-ok">Sign-in blocked</span></td>'
              f'<td style="color:var(--mut);white-space:nowrap">{last}</td></tr>')
    return out

ACTIVE=[u for u in USERS if u[2] and not is_vendor(u[1])]
CONFLICTED=[u for u in ACTIVE if sod_hits(u[4])]
VENDOR_ACCTS=[u for u in USERS if is_vendor(u[1])]+[("Administrator","Administrator",1,"Today",
  ["System Manager","Accounts Manager","Accounts User","Sales Manager","Stock Manager",
   "Purchase Manager","HR Manager","Projects Manager","Auditor"])]

def vendor_rows():
    out=""
    for nm,em,en,last,roles in VENDOR_ACCTS:
        st=('<span class="tag t-wt">active</span>' if en else '<span class="tag t-ok">sign-in blocked</span>')
        out+=(f'<tr><td>{nm}<div style="font-size:10.5px;color:var(--dim)">{em}</div></td>'
              f'<td style="font-size:11px;color:var(--mut)">{" · ".join(roles) if roles else "none"}</td>'
              f'<td>{len(roles)}</td><td>{st}</td>'
              f'<td style="color:var(--mut);white-space:nowrap">{last}</td></tr>')
    return out


# ---- Identity resolved from ERPNext, not configured here ----
# Employee -> designation / reports_to (who leads) ; Employee.user_id -> User -> Has Role (what they may do)
EMPLOYEES=[
 ("HR-EMP-00001","Samuel Damptey Adjei","CEO","Directorate","Sunyani",None,None,"Active"),
 ("HR-EMP-00002","Simon Yaw Nketiah Sieh","Director, HR/Administration","Directorate","Sunyani",
   "symstars@gmail.com","HR-EMP-00001","Active"),
 ("HR-EMP-00008","Obed Asamoah","Sales officer","Sales and Marketing","Kumasi",
   "scrillex444@gmail.com",None,"Active"),
 ("HR-EMP-00010","Sandra Serwaa Oppong","Customer Service Assistant","Customer Service","Sunyani",
   "sandyoppong75@gmail.com",None,"Active"),
 ("HR-EMP-00005","Thomas Kwame Billa","Operations Manager","Operations","Sunyani",
   "billay4k90@yahoo.com",None,"Left"),
 ("HR-EMP-00007","Bright Yomaah","Finance officer","Finance","Sunyani",
   "yomaahbright@gmail.com",None,"Left"),
]
# How an ERPNext role becomes access here. Order matters: first match that applies wins the label.
DERIVE=[("Chief Executive","Employee designation is CEO, or nobody above them in the reporting tree"),
        ("Platform administrator","Holds System Manager"),
        ("Internal Audit","Holds Auditor"),
        ("Finance","Holds Accounts Manager"),
        ("HR","Holds HR Manager"),
        ("Sales","Holds Sales Manager"),
        ("Buying and stock","Holds Purchase Manager or Stock Manager"),
        ("No access","Holds none of the above — the platform gives them nothing")]

def derive_access(roles, designation=None, is_root=False):
    out=[]
    if designation=="CEO" or is_root: out.append("Chief Executive")
    if "System Manager" in roles: out.append("Platform administrator")
    if "Auditor" in roles: out.append("Internal Audit")
    if "Accounts Manager" in roles: out.append("Finance")
    if "HR Manager" in roles: out.append("HR")
    if "Sales Manager" in roles: out.append("Sales")
    if ("Purchase Manager" in roles or "Stock Manager" in roles) and "Finance" not in out:
        out.append("Buying and stock")
    return out or ["No access"]

ROLES_BY_EMAIL={em:roles for nm,em,en,last,roles in USERS}
NAME_BY_EMAIL={em:nm for nm,em,en,last,roles in USERS}
ENABLED_BY_EMAIL={em:en for nm,em,en,last,roles in USERS}

def identity_rows():
    out=""
    seen=set()
    for eid,nm,desig,dept,branch,uid,rep,status in EMPLOYEES:
        roles=ROLES_BY_EMAIL.get(uid,[]) if uid else []
        acc=derive_access(roles,desig,rep is None and desig=="CEO")
        linked = bool(uid)
        if uid: seen.add(uid)
        link=('<span class="tag t-ok">linked</span>' if linked
              else '<span class="tag t-od">no account linked</span>')
        st=('' if status=="Active" else '<span class="tag t-dr">has left</span>')
        out+=(f'<tr><td>{nm}{st}<div style="font-size:10.5px;color:var(--dim)">{eid} &middot; {desig}</div></td>'
              f'<td style="color:var(--mut)">{dept}<div style="font-size:10.5px">{branch}</div></td>'
              f'<td style="font-size:11px;color:var(--mut)">{uid or "&mdash;"}</td>'
              f'<td style="font-size:11px">{" · ".join(acc)}</td><td>{link}</td></tr>')
    for nm,em,en,last,roles in USERS:
        if em in seen or not en or is_vendor(em): continue
        acc=derive_access(roles)
        out+=(f'<tr><td>{nm}<div style="font-size:10.5px;color:var(--dim)">no employee record</div></td>'
              f'<td style="color:var(--dim)">&mdash;</td>'
              f'<td style="font-size:11px;color:var(--mut)">{em}</td>'
              f'<td style="font-size:11px">{" · ".join(acc)}</td>'
              f'<td><span class="tag t-wt">no employee linked</span></td></tr>')
    return out

def derive_rows():
    return "".join(f'<tr><td><b>{a}</b></td><td style="color:var(--mut)">{b}</td></tr>' for a,b in DERIVE)

# People offered in the switcher: real users, access derived
SWITCH=[]
for eid,nm,desig,dept,branch,uid,rep,status in EMPLOYEES:
    if status!="Active": continue
    roles=ROLES_BY_EMAIL.get(uid,[]) if uid else []
    SWITCH.append((nm,desig,derive_access(roles,desig,rep is None and desig=="CEO"),uid))
for nm,em,en,last,roles in USERS:
    if not en: continue
    if any(s[3]==em for s in SWITCH): continue
    if is_vendor(em): continue
    SWITCH.append((nm,"no employee record",derive_access(roles),em))
