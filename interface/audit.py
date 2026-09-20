SQ=chr(39)
# -*- coding: utf-8 -*-
# Real events from this engagement against biomed.ultrasoft-systems.com, 19 Sept 2026.
TRAIL=[
# --- platform setup, 19 Sep 2026, by the team that configured it ---
("19 Sep 2026","16:40","System Administration","connect","Profiling completed","Command Center","all nine areas","Record volumes and gaps recorded for the design",""),
("19 Sep 2026","15:28","System Administration","create","Records created","Task","TASK-2026-00001 to 00011","Work breakdown added to three installation projects",""),
("19 Sep 2026","15:21","System Administration","create","Records created","Issue","ISS-2026-00001 to 00011","Demonstration complaints, marked as such",""),
("19 Sep 2026","14:33","System Administration","read","Stock position read","Bin","704 valued records","GHS 3,769,970 across six locations",""),
("19 Sep 2026","14:02","System Administration","connect","Connection registered","Command Center Connection","Gigmann ERPNext","Read access established",""),
# --- real business activity by Gigmann staff, from the ERPNext change history ---
("18 Mar 2026","13:19","Samuel Opoku","change","Supplier invoice amended","Purchase Invoice","ACC-PINV-2026-00001","Changed twice within five seconds",""),
("2 Sep 2025","17:07","Solomon Adortsu","change","Supplier invoice amended","Purchase Invoice","ACC-PINV-2025-00245","",""),
("19 Aug 2025","09:55","Samuel Opoku","change","Customer invoice amended","Sales Invoice","20250818112136763389","",""),
("19 Aug 2025","09:53","Solomon Boateng","change","Stock movement recorded","Stock Entry","MAT-STE-2025-00866","",""),
("19 Aug 2025","09:52","Samuel Opoku","create","Customer added","Customer","AL MAL MEDICAL SERVICES","New account opened",""),
("19 Aug 2025","09:52","Solomon Boateng","change","Supplier invoice amended","Purchase Invoice","ACC-PINV-2025-00244","",""),
("19 Aug 2025","09:50","Samuel Adjei","change","Purchase order taken through every approval stage","Purchase Order","PUR-ORD-2025-00223","All four stages completed by one account in fourteen seconds","po223"),
("19 Aug 2025","09:17","Grace Williams","change","Customer invoice amended","Sales Invoice","20250819091749594497","BANY HOSPITAL &mdash; still unpaid",""),
("19 Aug 2025","09:17","Samuel Opoku","change","Customer order amended","Sales Order","SAL-ORD-2025-00910","EJURA &mdash; still not despatched","so910"),
("19 Aug 2025","09:08","Grace Williams","change","Customer order amended","Sales Order","SAL-ORD-2025-00906-1","",""),
("19 Aug 2025","09:07","Grace Williams","change","Customer order amended","Sales Order","SAL-ORD-2025-00906","",""),
("19 Aug 2025","09:06","Grace Williams","change","Customer invoice amended","Sales Invoice","20250819090606665214","Dormaa West &mdash; still unpaid",""),
("19 Aug 2025","09:06","Samuel Opoku","change","Customer invoice issued","Sales Invoice","20250819090603609383","A1 MEDICALSUPPLIES &mdash; the credit note now awaiting approval","inv_a1"),
("19 Aug 2025","09:05","Grace Williams","change","Customer order amended","Sales Order","SAL-ORD-2025-00911","",""),
("19 Aug 2025","09:02","Solomon Boateng","change","Stock movement recorded","Stock Entry","MAT-STE-2025-00865","",""),
("19 Aug 2025","09:00","Simon Nketiah Sieh","change","Payment recorded and approved","Payment Entry","ACC-PAY-2025-03939","Raised and approved by the same account, five seconds apart","pay3939"),
]
KIND={"connect":("Set-up","var(--accent)"),"read":("Read","var(--dim)"),
      "create":("Record created","var(--ok)"),"change":("Record changed","var(--high)"),
      "approve":("Approval","var(--med)"),"ask":("Question asked","var(--accent)"),
      "perm":("Permission change","var(--crit)")}

def trail_rows():
    out=""
    for d,t,who,k,what,where,which,detail,drill in TRAIL:
        lab,col=KIND[k]
        blob=(who+" "+what+" "+where+" "+which+" "+detail).lower()
        det=(f'<div style="font-size:10.5px;color:var(--mut);margin-top:2px">{detail}</div>'
             if detail else '')
        click=(f' onclick="drill({SQ}{drill}{SQ})" style="cursor:pointer"' if drill else '')
        arrow=('<span style="color:var(--accent);font-size:11px">&rsaquo;</span>' if drill else '')
        out+=(f'<tr data-k="{k}" data-u="{who}" data-s="{blob}"{click}>'
              f'<td style="white-space:nowrap;color:var(--mut)">{d}'
              f'<div style="font-size:10.5px">{t}</div></td>'
              f'<td style="white-space:nowrap">{who}</td>'
              f'<td><span class="tag" style="color:{col};background:transparent;'
              f'border:1px solid {col};white-space:nowrap">{lab}</span></td>'
              f'<td>{what}{det}</td>'
              f'<td style="color:var(--mut)">{where}'
              f'<div style="font-size:10.5px">{which}</div></td>'
              f'<td style="text-align:right">{arrow}</td></tr>')
    return out

TRAIL_DEPTH=[("Customer payments","Payment Entry",13550),
 ("Customer invoices","Sales Invoice",12362),
 ("Customer orders","Sales Order",4900),
 ("Stock movements","Stock Entry",1565),
 ("Purchase orders","Purchase Order",1322),
 ("Everything else on business records","",13276)]
TRAIL_TOTAL=91133
TRAIL_BUSINESS=46975
TRAIL_FROM="5 February 2024"

def depth_rows():
    out=""
    for lab,dt,n in TRAIL_DEPTH:
        out+=(f'<tr><td>{lab}{f"<div style=font-size:10.5px;color:var(--dim)>{dt}</div>" if dt else ""}</td>'
              f'<td class="num">{n:,}</td></tr>')
    out+=(f'<tr style="border-top:2px solid var(--line2)"><td><b>Changes to business records</b></td>'
          f'<td class="num"><b>{TRAIL_BUSINESS:,}</b></td></tr>'
          f'<tr><td style="color:var(--mut)">Settings, permissions and system changes</td>'
          f'<td class="num" style="color:var(--mut)">{TRAIL_TOTAL-TRAIL_BUSINESS:,}</td></tr>'
          f'<tr><td><b>Everything recorded</b></td><td class="num"><b>{TRAIL_TOTAL:,}</b></td></tr>')
    return out

AUDIT_CSS="""
.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center}
.filters input{background:var(--surface);border:1px solid var(--line2);color:var(--ink);
 border-radius:7px;padding:6px 11px;font:13px var(--sans);min-width:230px;outline:none}
.filters input:focus{border-color:var(--accent)}
.filters select{background:var(--surface);border:1px solid var(--line2);color:var(--ink);
 border-radius:7px;padding:6px 9px;font:12px var(--sans);cursor:pointer}
.tcount{font-size:11.5px;color:var(--dim);margin-left:auto}
.immut{display:inline-flex;align-items:center;gap:6px;background:var(--ok-bg);
 border:1px solid var(--ok-line);color:var(--ok);border-radius:6px;padding:3px 9px;font-size:11px}
"""

# ---- field-level drill, from the real change records ----
def _chg(rows):
    out='<table class="dt drt"><thead><tr><th>What changed</th><th>From</th><th>To</th></tr></thead><tbody>'
    for f,a,b in rows:
        out+=(f'<tr><td>{f}</td><td style="color:var(--mut)">{a}</td>'
              f'<td style="color:var(--ink)">{b}</td></tr>')
    return out+'</tbody></table>'

def _step(t,who,rows,note=""):
    return (f'<div style="margin-bottom:14px"><div style="font-size:12px;font-weight:600">{t} '
            f'<span style="color:var(--dim);font-weight:400">&middot; {who}</span></div>'
            +(f'<div style="font-size:11px;color:var(--high);margin:3px 0 5px">{note}</div>' if note else '')
            +_chg(rows)+'</div>')

DRILL={
"po223": ('Purchase order','PUR-ORD-2025-00223',
 'Four changes on 19 August 2025, between 09:50:02 and 09:50:16.',
 _step("09:50:02","Samuel Adjei",[("Approval stage","Draft","Pending OPM Approval")])
 +_step("09:50:06","Samuel Adjei",[("Approval stage","Pending OPM Approval","Pending DIR Approval")])
 +_step("09:50:12","Samuel Adjei",[("Approval stage","Pending DIR Approval","Pending CEO Approval")])
 +_step("09:50:16","Samuel Adjei",[("Approval stage","Pending CEO Approval","Approved by CEO"),
                                    ("Status","Draft","To Receive and Bill"),
                                    ("Confirmed","No","Yes")]),
 "Gigmann already runs a four-stage approval on purchase orders: operations manager, director, then chief "
 "executive. On this order <b>one account completed all four stages in fourteen seconds</b>. The control "
 "exists and was followed on paper; nobody separate to the requester actually reviewed it."),

"pay3939": ('Payment','ACC-PAY-2025-03939',
 'Two changes on 19 August 2025, five seconds apart.',
 _step("09:00:47","Simon Nketiah Sieh",
   [("Approval stage","Draft","Pending DIR Approval"),
    ("Remarks","Amount GHS 30555 received from EJURA MUNICIPAL HOSPITAL","Amount GHS 30555.0 received from EJURA MUNICIPAL HOSPITAL")])
 +_step("09:00:51","Simon Nketiah Sieh",
   [("Approval stage","Pending DIR Approval","Approved by DIR"),
    ("Status","Draft","Submitted"),("Confirmed","No","Yes"),
    ("Invoice still outstanding","31,500","945")]),
 "GHS 30,555 received from EJURA MUNICIPAL HOSPITAL, settling all but GHS 945 of that invoice. "
 "The same account raised it and approved it, five seconds apart. Simon Nketiah Sieh holds both the "
 "accounts and director roles, so the system allowed it."),

"inv_a1": ('Customer invoice','20250819090603609383',
 'One change on 19 August 2025 at 09:06.',
 _step("09:06:17","Samuel Opoku",
   [("Posting time","09:06:05","09:06:13"),("Status","Draft","Unpaid"),("Confirmed","No","Yes")]),
 "The A1 MEDICALSUPPLIES invoice for GHS 11,000, issued and left unpaid. This is the same invoice now "
 "sitting in Approvals with a credit note request against it."),

"so910": ('Customer order','SAL-ORD-2025-00910',
 'One change on 19 August 2025 at 09:17.',
 _step("09:17:34","Samuel Opoku",[("Status","Draft","To Deliver and Bill"),("Confirmed","No","Yes")]),
 "EJURA MUNICIPAL HOSPITAL, GHS 65,100. Confirmed that morning and nothing has happened to it since "
 "&mdash; no despatch, no invoice."),
}

DRILL["po_big"]=('Purchase order','PUR-ORD-2025-00221-1',
 'SICHUAN M.K.R CO LTD, GHS 182,700. Raised 1 August 2025.',
 _step("Stage 1","Samuel Adjei",[("Approval stage","Draft","Pending OPM Approval")])
 +_step("Stage 2","Samuel Adjei",[("Approval stage","Pending OPM Approval","Pending DIR Approval")])
 +_step("Stage 3","Samuel Adjei",[("Approval stage","Pending DIR Approval","Pending CEO Approval")])
 +_step("Stage 4","Samuel Adjei",[("Approval stage","Pending CEO Approval","Approved by CEO"),
                                   ("Status","Draft","To Receive and Bill")]),
 "The largest approved purchase in the period. It went through all four stages, and the same account "
 "moved it at every one. The goods are still to be received.")
DRILL["pay_ubuntu"]=('Payment','ACC-PAY-2024-03097',
 'UBUNTU ORTHOPAEDIC & SPINE HOSPITAL, GHS 1,000,000 received. 25 October 2024.',
 _step("Recorded and approved","Bright Yomaah",
   [("Approval stage","Draft","Approved"),("Status","Draft","Submitted")]),
 "Worth holding next to their current balance. <b>UBUNTU has paid Gigmann a million cedis before</b>, so "
 "the GHS 636,675 outstanding is unlikely to be about ability to pay. They are also waiting on three "
 "installations promised nineteen months ago.")

def drill_html(k):
    kind,ref,when,body,note=DRILL[k]
    return (f'<div class="dhead"><div><div class="dt">{kind} &middot; change history</div><h4>{ref}</h4></div>'
            f'<button class="btn" onclick="closeDrawer()">Close &#10005;</button></div>'
            f'<p style="font-size:12.5px;color:var(--mut);margin-bottom:12px">{when}</p>'
            f'{body}'
            f'<div class="warn" style="margin-top:4px">{note}</div>'
            f'<div class="acts" style="margin-top:14px"><button class="btn pri">Open in ERPNext &#8599;</button>'
            f'<button class="btn">Raise as a finding</button></div>')
