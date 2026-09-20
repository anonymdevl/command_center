# -*- coding: utf-8 -*-
SQ=chr(39)
def _c(v): return f"{v:,.0f}"

# Purchase orders raised and never put through approval — real, from their site
STUCK=[("PUR-ORD-2025-00222","SICHUAN M.K.R CO LTD",398689,"1 Aug 2025","Samuel Adjei"),
 ("PUR-ORD-2024-00009","CYNSEL INNOVATION",278356,"6 Jul 2024","Samuel Adjei"),
 ("PUR-ORD-2024-00023","CYNSEL INNOVATION",94940,"27 Nov 2024","Samuel Adjei"),
 ("PUR-ORD-2025-00008","CYNSEL INNOVATION",72358,"10 Jan 2025","Samuel Adjei"),
 ("PUR-ORD-2024-00020","CYNSEL INNOVATION",54192,"14 Oct 2024","Samuel Adjei"),
 ("PUR-ORD-2025-00224","Costless Ventures",2520,"3 Sep 2025","Solomon Adortsu"),
 ("PUR-ORD-2026-00002","AGMED ENTERPRISE",2000,"18 Mar 2026","Samuel Opoku"),
 ("PUR-ORD-2025-00227","Chison SG PTE. LTD.",400,"29 Sep 2025","Solomon Adortsu"),
 ("PUR-ORD-2025-00226","Costless Ventures",90,"18 Sep 2025","Solomon Adortsu"),
 ("PUR-ORD-2025-00225","CYNSEL INNOVATION",54,"10 Sep 2025","Solomon Adortsu"),
 ("PUR-ORD-2026-00001","CIDA MEDICAL SUPPLIES",33,"17 Mar 2026","Samuel Opoku")]
STUCK_TOTAL=sum(x[2] for x in STUCK)

DECIDED=[("Purchase order","PUR-ORD-2025-00221-1","SICHUAN M.K.R CO LTD",182700,"Samuel Adjei",
  "Approved by CEO","ok","4 of 4 stages","po_big"),
 ("Purchase order","PUR-ORD-2025-00170","TAC MEDICAL",44200,"Samuel Adjei","Approved by CEO","ok","4 of 4 stages",""),
 ("Purchase order","PUR-ORD-2025-00220","CYNSEL INNOVATION",16107,"Samuel Adjei","Approved by CEO","ok","4 of 4 stages",""),
 ("Purchase order","PUR-ORD-2025-00223","SEEMANS MEDICAL SUPPLIES",2400,"Samuel Adjei",
  "Approved by CEO","warn","4 stages, one account, 14 seconds","po223"),
 ("Purchase order","PUR-ORD-2025-00221","SICHUAN M.K.R CO LTD",196220,"Samuel Adjei","Cancelled","cx","withdrawn",""),
 ("Payment","ACC-PAY-2024-03097","UBUNTU ORTHOPAEDIC & SPINE HOSPITAL",1000000,"Bright Yomaah",
  "Approved","ok","received from customer","pay_ubuntu"),
 ("Payment","ACC-PAY-2024-03210","SICHUAN M.K.R CO LTD",808000,"Sandra Oppong","Approved by CEO","ok","paid to supplier",""),
 ("Payment","ACC-PAY-2024-01173","STTARCARE MEDICAL PVT LTD",744000,"Bright Yomaah","Approved by CEO","ok","paid to supplier",""),
 ("Payment","ACC-PAY-2025-03939","EJURA MUNICIPAL HOSPITAL",30555,"Simon Nketiah Sieh",
  "Approved by DIR","warn","raised and approved by one account, 5 seconds","pay3939"),
 ("Payment","ACC-PAY-2025-03088","CYNSEL INNOVATION",1283800,"Samuel Adjei","Cancelled","cx","withdrawn",""),
 ("Payment","ACC-PAY-2025-03526","&mdash;",490000,"Grace Williams","Cancelled","cx","withdrawn","")]

STATES=[("Draft — never submitted",11,"var(--crit)","GHS 903,632 of purchases"),
 ("Approved by CEO",7,"var(--ok)","the full four stages"),
 ("Approved / Approved by DIR",3,"var(--med)","stopped short of the top stage"),
 ("Cancelled",3,"var(--dim)","withdrawn after being raised")]

def stuck_rows():
    out=""
    for ref,party,val,when,who in STUCK:
        heavy=val>50000
        out+=(f'<tr><td><span class="lnk">{ref}</span></td><td>{party}</td>'
              f'<td class="num"{" style=color:var(--crit)" if heavy else ""}>{_c(val)}</td>'
              f'<td style="white-space:nowrap;color:var(--mut)">{when}</td><td>{who}</td>'
              f'<td><span class="tag t-od">never submitted</span></td></tr>')
    out+=(f'<tr style="border-top:2px solid var(--line2)"><td colspan="2"><b>Eleven orders</b></td>'
          f'<td class="num"><b>{_c(STUCK_TOTAL)}</b></td><td colspan="3"></td></tr>')
    return out

def decided_rows():
    tag={"ok":"t-ok","warn":"t-wt","cx":"t-dr"}
    out=""
    for kind,ref,party,val,who,state,flag,note,drill in DECIDED:
        click=(f' onclick="drill({SQ}{drill}{SQ})" style="cursor:pointer"' if drill else '')
        arrow=('<span style="color:var(--accent)">&rsaquo;</span>' if drill else '')
        out+=(f'<tr{click}>'
              f'<td><span class="lnk">{ref}</span>'
              f'<div style="font-size:10.5px;color:var(--dim)">{kind}</div></td>'
              f'<td>{party}<div style="font-size:10.5px;color:var(--dim)">raised by {who}</div></td>'
              f'<td class="num">{_c(val)}</td>'
              f'<td><span class="tag {tag[flag]}">{state}</span>'
              f'<div style="font-size:10.5px;color:var(--mut);margin-top:3px">{note}</div></td>'
              f'<td style="text-align:right">{arrow}</td></tr>')
    return out

def state_rows():
    return "".join(
      f'<tr><td><span style="color:{c}">&#9679;</span> {lab}</td><td class="num">{n}</td>'
      f'<td style="color:var(--mut);font-size:11.5px">{note}</td></tr>' for lab,n,c,note in STATES)
