# -*- coding: utf-8 -*-
import json, sys
sys.path.insert(0,IFACE)
# 1. OLD generator first: shell CSS, command/brief/myday/ops/health/approvals/delegation/reports/risk, DRAWERS
exec(_src('p1.py'))
exec(_src('accents.py'))
exec(_src('signals.py'))
CSS = CSS + '\n/* ============ ACCENT VARIANTS ============ */\n' + css() + SIGNAL_CSS + APPEAR_CSS
exec(_src('p7.py'))
_OLD_ANSWERS=ANSWERS
exec(_src('audit.py'))
exec(_src('approvals.py'))
exec(_src('people.py'))
# 2. NEW deep views SECOND so they override the thin ones
exec(_src('views_e.py'))
exec(_src('brain.py'))
exec(_src('explain.py'))
exec(_src('records.py'))
exec(_src('tidy.py'))

EXTRA_CSS = CHART_CSS + TIDY_CSS + AUDIT_CSS + """
.tod{flex:none;overflow:visible}
.todray{animation:todspin 22s linear infinite;transform-origin:24px 24px}
.todcore{animation:todbreathe 3.4s ease-in-out infinite;transform-origin:24px 24px}
.todrise{animation:todrise 4.5s ease-in-out infinite;transform-origin:24px 34px}
.todglow{animation:todglow 3.8s ease-in-out infinite}
.todstar{animation:todtwinkle 2.6s ease-in-out infinite}
.todstar:nth-of-type(2){animation-delay:.8s}
.todstar:nth-of-type(3){animation-delay:1.6s}
@keyframes todspin{to{transform:rotate(360deg)}}
@keyframes todbreathe{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}
@keyframes todrise{0%,100%{transform:translateY(1.5px)}50%{transform:translateY(-1.5px)}}
@keyframes todglow{0%,100%{opacity:.55}50%{opacity:1}}
@keyframes todtwinkle{0%,100%{opacity:.25}50%{opacity:1}}

.live{display:inline-flex;align-items:center;gap:7px;background:var(--ok-bg);
 border:1px solid var(--ok-line);border-radius:7px;padding:4px 10px;font-size:11px;
 color:var(--ok);font-weight:550;white-space:nowrap}
.live .dot{width:7px;height:7px;border-radius:50%;background:var(--ok);flex:none;
 animation:blink 1.6s ease-in-out infinite;box-shadow:0 0 0 0 var(--ok-glow)}
@keyframes blink{0%,100%{opacity:1;box-shadow:0 0 0 0 var(--ok-glow)}
 70%{opacity:.85;box-shadow:0 0 0 6px transparent}}
.live small{color:var(--dim);font-weight:400;font-size:10px}
@media(prefers-reduced-motion:reduce){
 .todray,.todcore,.todrise,.todglow,.todstar,.live .dot{animation:none}}
.who{display:flex;align-items:center;gap:8px;padding-left:12px;border-left:1px solid var(--line)}
.av{width:30px;height:30px;border-radius:50%;background:linear-gradient(135deg,#4c8dff,#8b5cf6);
 display:grid;place-items:center;font:600 11.5px var(--sans);color:#fff;flex:none}
.whosel{background:none;border:none;color:var(--ink);font:600 12px var(--sans);
 padding:0 15px 0 0;margin:0;cursor:pointer;outline:none;-webkit-appearance:none;appearance:none;
 line-height:1.25;display:block;max-width:180px;text-overflow:ellipsis;white-space:nowrap}
.whosel:hover{color:var(--accent)}
.whosel option{background:var(--raised);color:#e8edf6;font-weight:400}
.who{position:relative;cursor:pointer}
.who::after{content:"\\25BE";position:absolute;right:0;top:8px;font-size:9px;color:var(--dim);pointer-events:none}
.whotxt span{font-size:10px;color:var(--dim);display:block;line-height:1.2}

@media(max-width:900px){.who .whotxt{display:none}}

.kpis.six{grid-template-columns:repeat(6,1fr)}
.kpi.clickable:hover{border-color:var(--accent);cursor:pointer}
.panel{background:transparent;margin-bottom:16px}
.ph{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.ph b{font-size:13px;font-weight:600}
.ph span{font-size:11px;color:var(--dim);margin-left:9px}
.ph.clickable{cursor:pointer}
.ph.clickable:hover b{color:var(--accent)}
.pmore{font-size:10.5px;color:var(--accent);white-space:nowrap}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.grid.six{display:grid;grid-template-columns:repeat(6,1fr);gap:9px}
.bul{margin-left:17px;font-size:12.5px;color:var(--mut)}
.bul li{margin:5px 0}.bul b{color:var(--ink)}
.sugg{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
/* The answer, and what it was checked against. One screen asks the questions now:
   "Find anything" and "Ask the business" were two doors to one room, and the designed
   placeholder on Find anything was already a question rather than a keyword. */
.askans{padding:14px 16px 4px;font-size:14px;line-height:1.62}
.askchecked{padding:10px 16px 14px;border-top:1px solid var(--line);margin-top:10px}
.askchecked-t{display:block;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;
color:var(--accent);font-weight:650;margin-bottom:6px}
.askchecked ul{margin:0;padding-left:16px}
.askchecked ul li{font-size:12px;color:var(--mut);line-height:1.66}
.askchecked .sugg{margin:8px 0 0}
.step{display:flex;gap:9px;align-items:center;font-size:12px;color:var(--mut);padding:4px 0}
.spin{width:11px;height:11px;border:1.5px solid var(--line2);border-top-color:var(--accent);
 border-radius:50%;animation:sp .7s linear infinite;flex:none}
.step.done .spin{border:none;width:11px;height:11px}
.step.done .spin::before{content:"✓";color:var(--ok);font-size:11px}
@keyframes sp{to{transform:rotate(360deg)}}
.drawer{width:640px}
.drt{font-size:11.5px}
.drt th{font-size:9.5px;white-space:normal}
.drt td{padding:6px 8px}
.drfoot{font-size:11.5px;color:var(--mut);margin-top:8px;line-height:1.5}
.exbox{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:10px 0}
@media(max-width:1100px){.kpis.six{grid-template-columns:repeat(3,1fr)}.two{grid-template-columns:1fr}
 .grid.six{grid-template-columns:repeat(3,1fr)}}
"""

NAVGROUPS=[
 ("Your day",[("command","Home","",["ceo","fin","sales","audit","hr"]),
              ("brief","Executive Summary","5",["ceo","fin","sales","audit","hr"]),
              ("myday","Today","",["ceo","fin","sales","audit","hr"])]),
 ("Run the business",[("ops","Business Overview","",["ceo","fin","sales","audit","hr"]),
              ("health","Business Health","6",["ceo","fin","audit"]),
              ("risk","Risk and Compliance","",["ceo","fin","audit"])]),
 ("Decide and delegate",[("approvals","Approvals","3",["ceo","fin"]),
              ("delegation","Outstanding Tasks","",["ceo","fin","sales","audit","hr"])]),
 ("Ask and find",[("ask","Ask AI","",["ceo","fin","sales","audit","hr"]),
              ("reports","Reports","",["ceo","fin","sales","audit","hr"])]),
 ("Areas of the business",[("sales","Sales and Payments",["ceo","fin","sales","audit"]),
              ("proc","Buying and Suppliers",["ceo","fin","audit"]),
              ("inv","Stock & Warehouses",["ceo","fin","sales","audit"]),
              ("eng","Project Insights",["ceo","sales","audit"]),
              ("cx","Customer Service & Issues",["ceo","sales","audit"]),
              ("fin","Finances",["ceo","fin","audit"]),
              ("hr","HR & Payroll",["ceo","hr","audit"]),
              ("it","Systems and Access",["ceo","audit"]),
              ("aud","Internal Audit",["ceo","audit"])])]
NAV=[]; DOMS=[]
for gname,items in NAVGROUPS:
    for it in items:
        if len(it)==4: NAV.append(it)
        else: DOMS.append(it)
GROUP_OF={}
for gname,items in NAVGROUPS:
    for it in items: GROUP_OF[it[0]]=gname
navh=""
for gi,(gname,items) in enumerate(NAVGROUPS):
    rows=""
    sub=" sub" if gname=="Areas of the business" else ""
    for it in items:
        if len(it)==4: k,lab,b,r=it
        else: k,lab,r=it; b=""
        bdg=f'<span class="bdg">{b}</span>' if b else ""
        rows+=(f'<div class="navi{sub}" data-nav="{k}" data-roles="{",".join(r)}" '
               f'onclick="go({SQ}{k}{SQ})"><span>{lab}</span>{bdg}</div>')
    navh+=f'<div class="navgrp" data-grp="{gi}"><div class="navsec">{gname}</div>{rows}</div>'
VIEWS={"command":V_COMMAND,"brief":V_BRIEF,"myday":V_MYDAY,"ops":V_OPS,"health":V_HEALTH,
 "approvals":V_APPROVALS,"delegation":V_DELEG,"ask":V_ASK,"reports":V_REPORTS,"risk":V_RISK,
 "sales":V_SALES,"proc":V_PROC,"inv":V_INV,"eng":V_ENG,"cx":V_CX,
 "fin":V_FIN,"hr":V_HR,"it":V_IT,"aud":V_AUD}
ROLE_OF={k:r for k,lab,b,r in NAV}; ROLE_OF.update({k:r for k,lab,r in DOMS})
for _k in ["sales","proc","inv","cx","fin","hr","health","risk"]:
    VIEWS[_k]=tabify(VIEWS[_k], ov_count=2)

viewh="".join(f'<div class="view" id="v-{k}" data-roles="{",".join(ROLE_OF[k])}">{v}</div>' for k,v in VIEWS.items())

def drawer_html(d):
    rows="".join(f"<dt>{a}</dt><dd>{b}</dd>" for a,b in d["rows"])
    ch=""
    for i,(t,s,done) in enumerate(d["chain"]):
        line='<span class="cline"></span>' if i<len(d["chain"])-1 else ''
        dot='cdot' if done else 'cdot pend'
        col='' if done else ' style="color:var(--high)"'
        ch+=f'<div class="cstep"><span class="{dot}"></span>{line}<div><div class="ct">{t}</div><div class="cs"{col}>{s}</div></div></div>'
    pr="".join(f"<dt>{a}</dt><dd>{b}</dd>" for a,b in d["prov"])
    return (f'<div class="dhead"><div><div class="dt">{d["kind"]}</div><h4>{d["name"]}</h4></div>'
            f'<button class="btn" onclick="closeDrawer()">Close ✕</button></div>'
            f'<dl class="kv" style="margin-bottom:14px">{rows}</dl>'
            f'<div class="sect">How far it got</div><div class="chain">{ch}</div>'
            f'<div class="sect">Where this comes from</div>'
            f'<div class="exbox"><dl class="kv" style="margin-bottom:0;grid-template-columns:130px 1fr;font-size:12px">{pr}</dl></div>'
            f'<div class="acts" style="margin-top:14px"><button class="btn pri">Open in ERPNext ↗</button>'
            f'<button class="btn">Hand this to someone</button>'
            f'<button class="btn" onclick="closeDrawer();go(\'ask\')">Ask about it</button></div>')
DR={k:drawer_html(v) for k,v in DRAWERS.items()}

def ex_html(k):
    t,sub,rows,foot=EX[k]
    r="".join(f"<dt>{a}</dt><dd>{b}</dd>" for a,b in rows)
    rec=RECORDS.get(k,"")
    if rec:
        recblock='<div class="sect" style="margin-top:16px">The records behind it</div>'+rec
    else:
        recblock=('<div class="sect" style="margin-top:16px">The records behind it</div>'
                  '<div class="thin">Nothing to list for this one in the demo extract.</div>')
    return (f'<div class="dhead"><div><div class="dt">Where this comes from</div><h4>{t}</h4></div>'
            f'<button class="btn" onclick="closeDrawer()">Close &#10005;</button></div>'
            f'<p style="font-size:13px;color:var(--mut);margin-bottom:10px">{sub}</p>'
            f'<div style="font-size:12.5px;line-height:1.6;margin-bottom:4px">{foot}</div>'
            + recblock +
            '<div class="sect" style="margin-top:16px">How it is put together</div>'
            f'<div class="exbox"><dl class="kv" style="margin-bottom:0;grid-template-columns:135px 1fr;font-size:12px">{r}</dl></div>'
            '<div class="acts" style="margin-top:14px"><button class="btn pri">Open in ERPNext &#8599;</button>'
            '<button class="btn">Hand this to someone</button>'
            '<button class="btn" onclick="closeDrawer();go(&#39;ask&#39;)">Ask about this</button></div>')
EXH={k:ex_html(k) for k in EX}
DRH={k:drill_html(k) for k in DRILL}
print("explainers:",len(EXH),"drawers:",len(DR),"views:",len(VIEWS))

ROLEKEY={"Chief Executive":"ceo","Finance":"fin","Sales":"sales","HR":"hr","Internal Audit":"audit"}
PEOPLE_JS={}; _opts=[]
for _i,(nm,desig,acc,uid) in enumerate(SWITCH):
    keys=[ROLEKEY[a] for a in acc if a in ROLEKEY]
    if not keys: continue
    pid="p%d"%_i
    ini="".join(w[0] for w in nm.split()[:2]).upper()
    where = desig if desig!="no employee record" else "No employee record"
    PEOPLE_JS[pid]={"name":nm,"init":ini,"role":keys[0],
                    "dept":where+" \u00b7 "+", ".join(acc)}
    _opts.append(f'<option value="{pid}">{nm}</option>')
def switch_options(): return "".join(_opts)
BODY=f"""
<div class="shell">
<div class="topnav">
<div class="brand"><div class="logo">IC</div><div><b>Intelligent Command Center</b><span>Executive platform</span></div></div>
<span class="lbl">Business</span>
<select class="sel" id="entity"><option>Gigmann Medical Supplies Ltd · GHS</option>
<option disabled>Adehyeman Specialist Hospital — not connected</option>
<option disabled>Adehyeman Pharmacy — not connected</option>
<option disabled>All businesses together — needs 2 or more</option></select>
<span class="spacer"></span>
<div class="appear"><button class="themebtn" id="tb" onclick="toggleAppear(event)" title="Appearance">&#9681;</button>
<div class="appearmenu" id="am" onclick="event.stopPropagation()">
<div class="amsec">Theme</div>
<div class="seg" id="segtheme"><button data-v="light" onclick="applyTheme(&#39;light&#39;)">Light</button><button data-v="dark" onclick="applyTheme(&#39;dark&#39;)">Dark</button></div>
<div class="amsec">Accent</div>
<div class="swatches">{swatches(ACCENTS)}</div><div class="swname" id="swn"></div>
<div class="amsec">Signal strength</div>
<div class="seg" id="segsig"><button data-v="vivid" onclick="setSignal(&#39;vivid&#39;)">Vivid</button><button data-v="muted" onclick="setSignal(&#39;muted&#39;)">Muted</button><button data-v="quiet" onclick="setSignal(&#39;quiet&#39;)">Quiet</button></div>
</div></div>
<span class="live"><span class="dot"></span>ERPNext connected <small>biomed.ultrasoft-systems.com</small></span>
<span class="asof">● Figures as at 19 Aug 2025</span>
<div class="who"><div class="av" id="av">CE</div><div class="whotxt">
<select class="whosel" id="role" onchange="setRole()">{switch_options()}</select>
<span id="whorole"></span></div></div></div>
<div class="body"><div class="side">{navh}</div>
<div class="main" id="main">
<div class="view" id="v-denied" data-roles="ceo,fin,sales,audit,hr"><div class="denied"><div class="big">⛔</div>
<h4>Not available to your role</h4><p>You are signed in as a role that has not been granted this area.
Nothing is hidden on the screen — the figures were never fetched. Access is granted per role and per
business, and nobody gains it by default.</p><div class="acts" style="justify-content:center;margin-top:16px">
<button class="btn pri" onclick="go('command')">Back to Command</button></div></div></div>
{viewh}</div></div></div>
<div class="scrim" id="scrim" onclick="closeDrawer()"></div>
<div class="drawer" id="drawer"></div>
<script>
const DRAWERS={json.dumps(DR)}, EXPL={json.dumps(EXH)}, BRAIN={json.dumps(BRAIN)}, DRILL={json.dumps(DRH)};
// Replace these with the real people before the demo.
const PEOPLE={json.dumps(PEOPLE_JS)};
let role='ceo', who='p0';
const SUN='<svg class="tod" viewBox="0 0 48 48" fill="none">'
 +'<g class="todray" stroke="var(--sun)" stroke-width="2.4" stroke-linecap="round">'
 +'<path d="M24 4v6M24 38v6M4 24h6M38 24h6M9.9 9.9l4.3 4.3M33.8 33.8l4.3 4.3M38.1 9.9l-4.3 4.3M14.2 33.8l-4.3 4.3"/></g>'
 +'<circle class="todcore" cx="24" cy="24" r="9" fill="var(--sun)"/></svg>';
const DAWN='<svg class="tod" viewBox="0 0 48 48" fill="none">'
 +'<g class="todrise"><path d="M13 34a11 11 0 0 1 22 0Z" fill="var(--dawn)"/>'
 +'<g class="todglow" stroke="var(--sun)" stroke-width="2.2" stroke-linecap="round">'
 +'<path d="M24 8v5M8.6 16.6l3.5 3.5M39.4 16.6L35.9 20.1"/></g></g>'
 +'<path d="M6 34h36" stroke="var(--dawn)" stroke-width="2.4" stroke-linecap="round"/>'
 +'<path d="M11 40h26" stroke="var(--dawn)" stroke-width="2.2" stroke-linecap="round" opacity=".45"/></svg>';
const MOON='<svg class="tod" viewBox="0 0 48 48" fill="none">'
 +'<path class="todcore" d="M31 6a18 18 0 1 0 11 32A19 19 0 0 1 31 6Z" fill="var(--moon)"/>'
 +'<circle class="todstar" cx="12" cy="13" r="1.7" fill="var(--star)"/>'
 +'<circle class="todstar" cx="20" cy="7" r="1.2" fill="var(--star)"/>'
 +'<circle class="todstar" cx="9" cy="21" r="1.2" fill="var(--star)"/></svg>';
function greet(){{
  const h=new Date().getHours(), p=PEOPLE[who]||Object.values(PEOPLE)[0];
  let word='Good morning', icon=DAWN;
  if(h>=12&&h<17){{word='Good afternoon'; icon=SUN;}}
  else if(h>=17||h<5){{word='Good evening'; icon=MOON;}}
  const g=document.getElementById('greet');
  if(g) g.innerHTML='<div><div>'+word+', '+p.name+'</div>'
    +'<div class="when" style="font-weight:400">'
    +new Date().toLocaleDateString('en-GB',{{weekday:'long',day:'numeric',month:'long',year:'numeric'}})
    +' &middot; '+new Date().toLocaleTimeString('en-GB',{{hour:'2-digit',minute:'2-digit'}})+'</div></div>'+icon;
  const av=document.getElementById('av'), wr=document.getElementById('whorole');
  if(av) av.textContent=p.init; if(wr) wr.textContent=p.dept;
}}
const GROUP_OF={json.dumps(GROUP_OF)};
function setEyebrow(k){{
  const v=document.getElementById('v-'+k); if(!v) return;
  const tb=v.querySelector('.topbar > div'); if(!tb) return;
  let e=tb.querySelector('.eyebrow');
  const g=GROUP_OF[k]; if(!g) return;
  if(!e){{ e=document.createElement('span'); e.className='eyebrow'; tb.insertBefore(e,tb.firstChild); }}
  e.textContent=g;
}}
function go(k){{const v=document.getElementById('v-'+k); if(!v) return;
 if(!(v.dataset.roles||'').split(',').includes(role)){{k='denied';}}
 document.querySelectorAll('.view').forEach(e=>e.classList.remove('on'));
 document.getElementById('v-'+k).classList.add('on');
 document.querySelectorAll('.navi').forEach(e=>e.classList.toggle('on',e.dataset.nav===k));
 setEyebrow(k); document.getElementById('main').scrollTop=0; closeDrawer();}}
function setRole(){{
 who=document.getElementById('role').value;
 role=(PEOPLE[who]||{{}}).role||'ceo';
 greet();
 document.querySelectorAll('.navi').forEach(e=>e.classList.toggle('hide',
   !(e.dataset.roles||'').split(',').includes(role)));
 const cur=document.querySelector('.view.on');
 if(!cur||!(cur.dataset.roles||'').split(',').includes(role)) go('command');}}
function openDrawer(k){{const d=DRAWERS[k]; if(!d) return; show(d);}}
function explain(k){{const d=EXPL[k]; if(!d) return; show(d);}}
function drill(k){{const d=DRILL[k]; if(!d) return; show(d);}}
function show(html){{document.getElementById('drawer').innerHTML=html;
 document.getElementById('drawer').classList.add('on');
 document.getElementById('scrim').classList.add('on');}}
function closeDrawer(){{document.getElementById('drawer').classList.remove('on');
 document.getElementById('scrim').classList.remove('on');}}
function ask2(q){{go('ask'); setTimeout(()=>runSearch(q),120);}}
function match(q){{q=q.toLowerCase(); let best=null,bs=0;
 for(const b of BRAIN){{let s=0; for(const k of b.k) if(q.includes(k)) s++;
  if(s>bs){{bs=s;best=b;}} }}
 return bs>0?best:null;}}
function runSearch(q){{
 const out=document.getElementById('sout')||document.getElementById('sout2');
 const inp=document.getElementById('sin')||document.getElementById('askin');
 if(inp) inp.value=q;
 const b=match(q);
 if(!b){{out.innerHTML='<div class="ans"><p>I could not find anything for that in this prototype. '
   +'The finished platform searches every record; here only a handful of questions are wired up. '
   +'Try one of the suggestions above.</p></div>'+out.innerHTML; return;}}
 const id='r'+Date.now();
 out.innerHTML='<div class="ans" id="'+id+'"><div id="'+id+'s"></div></div>'+out.innerHTML;
 const sc=document.getElementById(id+'s');
 let i=0;
 (function next(){{
   if(i<b.steps.length){{
     sc.innerHTML+='<div class="step" id="'+id+'st'+i+'"><span class="spin"></span>'+b.steps[i]+'</div>';
     const cur=i; i++;
     setTimeout(()=>{{const e=document.getElementById(id+'st'+cur); if(e)e.classList.add('done'); next();}},430);
   }} else {{
     setTimeout(()=>{{
       let h='';
       if(b.gate){{h='<div class="gate"><div class="gt">⛔ I cannot do this — it needs a person to approve it</div>'
         +'<p>Issuing or changing a credit note affects what a customer owes. There is no function available '
         +'to me that performs it, whatever the request says.</p>'
         +'<p style="margin-top:8px">I have prepared the request instead. It carries the invoice, the '
         +'customer balance and the proposed amount, and it is waiting for the <b>Finance Manager</b> in Approvals.</p>'
         +'<div class="acts"><button class="btn pri" onclick="go(\\'approvals\\')">Open the request</button>'
         +'<button class="btn">Cancel it</button></div></div>';
         document.getElementById(id).outerHTML=h;
       }} else {{
         h=b.ans+(b.sug?'<div class="asw" style="margin:10px 0 0">'+b.sug+'</div>':'');
         if(b.src&&b.src.length){{h+='<div class="srcs">'+b.src.map(s=>
           '<span class="chip src" onclick="'+(EXPL[s[2]]?'explain':'openDrawer')+'(\\''+s[2]+'\\')">'
           +s[0]+' · <b>'+s[1]+'</b></span>').join('')+'</div>';}}
         document.getElementById(id).innerHTML=h;
       }}
     }},260);
   }}
 }})();}}
function filterTrail(){{
  const q=(document.getElementById('afq').value||'').toLowerCase();
  const k=document.getElementById('afk').value, u=document.getElementById('afu').value;
  let n=0, rows=document.querySelectorAll('#atrail tbody tr');
  rows.forEach(r=>{{
    const ok=(!q||r.dataset.s.includes(q))&&(!k||r.dataset.k===k)&&(!u||r.dataset.u===u);
    r.style.display=ok?'':'none'; if(ok)n++;
  }});
  document.getElementById('afc').textContent=n+' of '+rows.length+' events';
}}
const ACC_NAMES={json.dumps({k:lab for k,lab,g,li,dk,n in ACCENTS})};
function toggleAppear(e){{
  document.getElementById('am').classList.toggle('on');
  if(e) e.stopPropagation();
}}
function syncAppear(){{
  const d=document.documentElement;
  const t=d.getAttribute('data-theme')||'dark', a=d.getAttribute('data-accent')||'petrol',
        g=d.getAttribute('data-signal')||'muted';
  document.querySelectorAll('#segtheme button').forEach(b=>b.classList.toggle('on',b.dataset.v===t));
  document.querySelectorAll('#segsig button').forEach(b=>b.classList.toggle('on',b.dataset.v===g));
  document.querySelectorAll('.sw').forEach(b=>b.classList.toggle('on',b.dataset.a===a));
  const n=document.getElementById('swn'); if(n) n.textContent=ACC_NAMES[a]||'';
}}
function setSignal(v){{
  document.documentElement.setAttribute('data-signal',v);
  try{{ localStorage.setItem('icc-signal',v); }}catch(e){{}}
  syncAppear();
}}
function setAccent(a){{
  document.documentElement.setAttribute('data-accent',a);
  try{{ localStorage.setItem('icc-accent',a); }}catch(e){{}}
  syncAppear();
}}
function applyTheme(t){{
  document.documentElement.setAttribute('data-theme',t);
  const b=document.getElementById('tb');
  if(b) b.innerHTML = t==='light' ? '&#9680;' : '&#9681;';
  try{{ localStorage.setItem('icc-theme',t); }}catch(e){{}}
  syncAppear();
}}

(function(){{
  let a='petrol';
  try{{ a=localStorage.getItem('icc-accent')||'petrol'; }}catch(e){{}}
  document.documentElement.setAttribute('data-accent',a);

  let g='muted';
  try{{ g=localStorage.getItem('icc-signal')||'muted'; }}catch(e){{}}
  document.documentElement.setAttribute('data-signal',g);

  let t='dark';
  try{{ t=localStorage.getItem('icc-theme') ||
    (window.matchMedia&&matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'); }}catch(e){{}}
  applyTheme(t);
}})();
function tab(btn,g,i){{
  document.querySelectorAll('.tabbar[data-g="'+g+'"] .tab').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  document.querySelectorAll('.tabpane[data-g="'+g+'"]').forEach(p=>
    p.classList.toggle('on', p.dataset.i==String(i)));
}}
function moreMenu(btn){{
  const m=btn.nextElementSibling;
  document.querySelectorAll('.moremenu.on').forEach(x=>{{if(x!==m)x.classList.remove('on');}});
  m.classList.toggle('on');
  event.stopPropagation();
}}
document.addEventListener('click',()=>{{
  document.querySelectorAll('.moremenu.on').forEach(x=>x.classList.remove('on'));
  const am=document.getElementById('am'); if(am) am.classList.remove('on');
}});
setRole(); go('command'); greet(); filterTrail(); syncAppear(); setInterval(greet,30000);
</script></body></html>"""
# The caller decides where these go. scripts/build_interface.py splits them into
# the app's stylesheet, script and www template; nothing is written from here.


BOOT_CSS = """
/* ============ LIVE vs DEMO ============ */
.dnote{display:flex;align-items:flex-start;gap:9px;background:var(--med-bg);
 border:1px solid var(--med-line);border-left:3px solid var(--med);border-radius:var(--r);
 padding:10px 13px;margin-bottom:14px;font-size:11.5px;color:var(--mut);line-height:1.45}
.dnote b{color:var(--stale);font-weight:650}
.dnote .dn-i{flex:none;font-size:12px;color:var(--stale);line-height:1.3}
.livechip{display:inline-flex;align-items:center;gap:6px;font-size:10.5px;font-weight:650;
 padding:3px 9px;border-radius:999px;white-space:nowrap;
 background:var(--ok-bg);color:var(--ok);border:1px solid var(--ok-line)}
.livechip.stale{background:var(--med-bg);color:var(--stale);border-color:var(--med-line)}
.whosel:disabled{opacity:1;cursor:default}
/* The caret was drawn for a persona dropdown. With a real session there is
   nothing to choose, so the arrow would promise a menu that never opens. */
.who.nopick::after{content:none}
.who.nopick{cursor:default}

/* ============ THE DRILL AFFORDANCE ============ */
/* It sat at bottom:7px, below the footnote rather than beside it. The footnote
   box is 26px tall and ends 15px above the card's bottom edge, so its text
   centres at about 22.5px -- a 13px glyph therefore starts at 16px. */
.kpi.clickable::after,
.bk.clickable::before{
  /* The literal character, not the escape \\203a: the minifier resolved that
     as U+0203 followed by a stray "a", which rendered as a missing-glyph box
     and the letter a on every card. */
  content:"›";position:absolute;bottom:16px;right:12px;
  color:var(--dim);font-size:13px;line-height:1;pointer-events:none}
/* .bk already uses ::after for the hairline on tiles with no footnote, so the
   chevron goes on ::before there. */
.bk.clickable{position:relative}
.kpi.clickable .delta,
.bk.clickable .v{padding-right:18px}
.kpi.clickable:hover::after,
.bk.clickable:hover::before{color:var(--accent)}
.bk.clickable{cursor:pointer}

/* ============ THE GREETING ============ */
/* #greet is an <h3>, so the icon is a flex child of a heading: a long name
   pushed it onto its own line. Pinned so it cannot wrap and centred so it spans
   both lines of text rather than sitting against one of them. */
.hello{display:flex;align-items:center;gap:12px;flex-wrap:nowrap;margin-bottom:4px}
.hello > .greet-text{flex:1 1 auto;min-width:0}
.hello > .greet-text > .greet-line{white-space:nowrap;overflow:hidden;
 text-overflow:ellipsis}
.hello .tod{flex:0 0 38px;width:38px;height:38px;align-self:center}
@media(max-width:700px){.hello .tod{flex-basis:32px;width:32px;height:32px}}

/* ============ SPACING ============ */
/* The illustrative banner sat directly on the greeting. */
.view > .topbar:first-child,
.view > .hello:first-child{margin-top:4px}
#ccdnote{margin-bottom:18px !important}

/* ============ SIDEBAR BADGES ============ */
/* The markup emitted <span class="bdg">5</span> from the start and nothing ever
   styled it, so it rendered as bare text against the label: "Daily brief5". */
.navi{display:flex;align-items:center;gap:8px}
.navi > span:first-of-type{flex:1;min-width:0;overflow:hidden;
 text-overflow:ellipsis;white-space:nowrap}
.navi.sub::before{flex:none}
.bdg{flex:none;min-width:19px;height:18px;padding:0 6px;border-radius:999px;
 background:var(--accent-bg);color:var(--accent);border:1px solid var(--accent-dim);
 font-size:10px;font-weight:700;line-height:1;display:inline-flex;
 align-items:center;justify-content:center;font-variant-numeric:tabular-nums}
.navi.on .bdg{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
"""

BOOT_JS = """

/* =====================================================================
   Adopt the signed-in session.

   Runs after the interface has initialised, so it patches rather than
   competes with it. Without a payload -- the file opened on its own, outside
   Frappe -- everything below is skipped and the demo extract stands, which is
   what makes the same build serve as both the product and the walkthrough.
   ===================================================================== */
(function(){
  var B = window.CC_BOOT;
  if(!B) return;

  /* -- the person, not a demo persona ------------------------------------ */
  if(B.user){
    try{
      PEOPLE[who] = {name:B.user.name, init:B.user.initials, role:'ceo',
                     dept:(B.user.roles||[]).join(' \u00b7 ') || 'Management'};
    }catch(e){}
    var sel=document.getElementById('role');
    if(sel){
      /* A persona switcher is a demonstration device. With a real session the
         only person this can be is the one signed in. */
      sel.innerHTML='<option>'+B.user.name+'</option>';
      sel.disabled=true;
    }
  }

  /* -- businesses, from the registry ------------------------------------- */
  var ent=document.getElementById('entity');
  if(ent && B.scopes && B.scopes.length){
    var real=B.scopes.filter(function(s){ return s.code!=='__all__'; });
    var list=(real.length>1)? B.scopes : real;
    var byCode={};
    (B.businesses||[]).forEach(function(b){ byCode[b.business_code]=b; });
    ent.innerHTML=list.map(function(s){
      var b=byCode[s.code], bits=[s.label];
      if(b && b.currency) bits.push(b.currency);
      if(b && !b.can_read) bits.push('unreachable');
      else if(b && !b.can_act) bits.push('read only here');
      return '<option value="'+s.code+'"'+((b&&!b.can_read)?' disabled':'')+'>'
             + bits.join(' \u00b7 ') + '</option>';
    }).join('');
    if(real.length<2){
      /* "All businesses" is a scope only once there is more than one. */
      ent.title='Connect a second business to compare them';
    }
  }

  /* -- what the figures describe, and when they were read ---------------- */
  var asof=document.querySelector('.asof');
  if(asof){
    if(B.as_of && B.as_of.date){
      var d=new Date(B.as_of.date+'T00:00:00');
      asof.textContent='\u25cf Figures as at '+d.toLocaleDateString('en-GB',
        {day:'numeric',month:'short',year:'numeric'});
      asof.title='The latest date the data covers. Ageing is measured against '
        +'this, not today'+(B.as_of.last_run? ' \u00b7 last read '+B.as_of.last_run : '');
    } else {
      asof.textContent='\u25cf No figures loaded yet';
      asof.title='Run the load before relying on anything here';
    }
  }
  var live=document.querySelector('.live');
  if(live && B.site){
    var ok=B.as_of && B.as_of.status==='OK';
    live.className='live'+(ok?'':' ');
    live.innerHTML='<span class="dot"></span>ERPNext connected <small>'+B.site+'</small>';
  }

  /* -- say which screens are real ---------------------------------------- */
  var liveViews=(B.live||[]);
  var NOTE='<span class="dn-i">●</span><span><b>Illustrative figures.</b> '
    +'The design and the workings are real; the numbers on this screen are still '
    +'the demonstration extract. Each area is wired to the loaded facts in turn, '
    +'and a screen drops this line the moment it reads them.</span>';

  if(!liveViews.length){
    /* Nothing wired yet, so one line above the views rather than the same
       warning repeated on twenty screens. A notice that appears everywhere
       stops being read. */
    var main=document.getElementById('main');
    if(main && !document.getElementById('ccdnote')){
      var g=document.createElement('div');
      g.id='ccdnote'; g.className='dnote';
      g.style.margin='14px 26px 0';
      g.innerHTML=NOTE;
      main.parentNode.insertBefore(g, main);
    }
  } else {
    document.querySelectorAll('.view').forEach(function(v){
      var k=(v.id||'').replace(/^v-/,'');
      if(k==='denied' || liveViews.indexOf(k)!==-1) return;
      if(v.querySelector('.dnote')) return;
      var n=document.createElement('div');
      n.className='dnote';
      n.innerHTML=NOTE;
      var tb=v.querySelector('.topbar');
      if(tb && tb.nextSibling) v.insertBefore(n, tb.nextSibling);
      else v.insertBefore(n, v.firstChild);
    });
  }

  /* -- badges claim counts, so they wait for something to count ---------- */
  /* "Daily brief 5", "Approvals 3" read as live tallies. They were fixed
     numbers from the walkthrough, and unlike every figure on a screen they
     carry no caveat next to them -- a small number in a sidebar looks like
     fact. They come back per view as that view starts reading the facts. */
  document.querySelectorAll('.navi').forEach(function(n){
    var k=n.dataset.nav, b=n.querySelector('.bdg');
    if(b && liveViews.indexOf(k)===-1) b.remove();
  });

  /* the interface already initialised; re-run what the payload changed */
  try{ setRole(); greet(); }catch(e){}
})();
"""


def normalise_cards(html: str) -> str:
    """Give every tile the same affordance, whichever view built it.

    .kpi cards come from one function now. .bk tiles do not come from a function
    at all -- there are twenty-five hand-written sites -- which is why five
    screens kept their old appearance while the rest changed. Rewriting all of
    them by hand would be a large, error-prone edit of markup that components
    will replace anyway, so the contract is applied here instead, once, to
    whatever the generators produced.

    This is a bridge. It disappears with the last legacy view.
    """
    import re as _re

    def fix(m):
        classes, attrs = m.group(1), m.group(2)
        if "clickable" in classes:
            return m.group(0)
        # A tile with no drill target still opens: every figure in this platform
        # answers "which records?", and a tile that did not would look like a
        # different component as well as breaking the promise.
        if "onclick" not in attrs:
            attrs += ' onclick="explain(&#39;unwired&#39;)"'
        return f'<div class="{classes} clickable"{attrs}>'

    # Variants matter: Control Health's six questions are class="bk q", and a
    # pattern that only matched the bare class left that whole screen behind --
    # which is how it was reported as unchanged.
    return _re.sub(r'<div class="(bk(?:\s+[\w-]+)*)"((?:(?!>).)*)>', fix, html)


VIEWS = {k: normalise_cards(v) for k, v in VIEWS.items()}

_i = BODY.index("<script>")
_j = BODY.rindex("</script>")
PARTS = {
    "css": CSS + EXTRA_CSS + BOOT_CSS,
    "body": BODY[:_i],
    "js": BODY[_i + len("<script>"):_j] + BOOT_JS,
}
print("  generated: css %d · body %d · js %d bytes"
      % (len(PARTS["css"]), len(PARTS["body"]), len(PARTS["js"])))
