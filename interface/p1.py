# -*- coding: utf-8 -*-
CSS = """
/* ============ TOKENS ============ */
:root{
 /* refined dark: deeper, cooler, softer edges */
 --bg:#0a0c11; --chrome:#0e1118; --surface:#12151d; --raised:#191d27; --panel:#141821;
 --line:#1e2330; --line2:#2b3242; --hover:rgba(255,255,255,.045); --zebra:rgba(255,255,255,.022);
 --ink:#eef0f6; --mut:#98a1b5; --dim:#616a7e;
 --accent:#7c8cff; --accent-ink:#b3bdff; --accent-dim:#2e3566;
 --accent-bg:rgba(124,140,255,.09); --accent-bg2:rgba(124,140,255,.16);
 --crit:#f4726e; --crit-bg:rgba(244,114,110,.12); --crit-line:rgba(244,114,110,.32);
 --high:#f5a15c; --high-bg:rgba(245,161,92,.11); --high-line:rgba(245,161,92,.30);
 --med:#f2cc6b; --med-bg:rgba(242,204,107,.11); --med-line:rgba(242,204,107,.30);
 --ok:#5ed6a4; --ok-bg:rgba(94,214,164,.11); --ok-line:rgba(94,214,164,.30);
 --ok-glow:rgba(94,214,164,.5);
 --info:#7c8cff; --stale:#f2cc6b; --dim-bg:rgba(150,160,180,.13); --thin-bg:rgba(150,160,180,.05);
 --star:#cfe0ff; --scrim:rgba(4,6,10,.64);
 --sun:#f2cc6b; --dawn:#f5a15c; --moon:#8fb0ee;
 --shadow:0 1px 2px rgba(0,0,0,.30); --shadow2:0 18px 44px rgba(0,0,0,.50);
 --grad:linear-gradient(135deg,#7c8cff,#a78bfa);
 --solid:#7c8cff;
 --r:14px; --r2:18px;
 --mono:ui-monospace,'SF Mono',Menlo,Consolas,monospace;
 --sans:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
}
[data-theme="light"]{
 --bg:#f6f4ef; --chrome:#fffefb; --surface:#ffffff; --raised:#f3f1ea; --panel:#ffffff;
 --line:#e9e5db; --line2:#d8d3c6; --hover:rgba(30,25,15,.045); --zebra:rgba(30,25,15,.022);
 --ink:#17161a; --mut:#545360; --dim:#6e6d79; --solid:#1a1a20;
 --crit:#b8382f; --crit-bg:rgba(184,56,47,.09); --crit-line:rgba(184,56,47,.26);
 --high:#a45a0e; --high-bg:rgba(164,90,14,.10); --high-line:rgba(164,90,14,.26);
 --med:#87630a; --med-bg:rgba(135,99,10,.11); --med-line:rgba(135,99,10,.26);
 --ok:#0c6a4d; --ok-bg:rgba(12,106,77,.09); --ok-line:rgba(12,106,77,.26);
 --ok-glow:rgba(12,106,77,.30);
 --stale:#a45a0e; --dim-bg:rgba(88,84,74,.11); --thin-bg:rgba(88,84,74,.045);
 --scrim:rgba(23,22,26,.34); --sun:#b8830c; --dawn:#a45a0e;
 --shadow:0 1px 2px rgba(30,25,15,.05), 0 2px 6px rgba(30,25,15,.045);
 --shadow2:0 26px 64px rgba(30,25,15,.17), 0 3px 10px rgba(30,25,15,.06);
}

/* ---- light-only refinements ---- */
[data-theme="light"] .topnav{box-shadow:0 1px 0 var(--line)}
[data-theme="light"] .side{box-shadow:1px 0 0 var(--line)}
[data-theme="light"] table.dt th{color:#6b7280;border-bottom-color:var(--line2)}
[data-theme="light"] .btn{background:#fff}
[data-theme="light"] .btn:hover{background:var(--raised)}
[data-theme="light"] .logo{box-shadow:0 2px 8px rgba(30,25,15,.18)}
[data-theme="light"] .chartwrap,[data-theme="light"] .ans,[data-theme="light"] .askbox,
[data-theme="light"] .note{box-shadow:0 1px 2px rgba(28,24,16,.05), 0 2px 7px rgba(28,24,16,.04)}
[data-theme="light"] .navi.on{background:linear-gradient(90deg,var(--accent-bg2),transparent);
 box-shadow:inset 2px 0 0 var(--accent)}
[data-theme="light"] .side{background:#fbfbfa}

/* ============ BASE ============ */
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--bg);color:var(--ink);font:14px/1.55 var(--sans);
 font-feature-settings:"tnum" 1,"cv05" 1;-webkit-font-smoothing:antialiased;overflow:hidden;
 transition:background .18s,color .18s}
button{font-family:inherit}
.shell{display:grid;grid-template-rows:auto 1fr;height:100vh}
.topnav{display:flex;align-items:center;gap:13px;padding:10px 18px;background:var(--chrome);
 border-bottom:1px solid var(--line);flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:10px;padding-right:15px;border-right:1px solid var(--line)}
.logo{width:28px;height:28px;border-radius:9px;background:var(--grad);display:grid;place-items:center;
 font:700 11px var(--sans);color:#fff;letter-spacing:.02em;box-shadow:var(--shadow)}
.brand b{font-size:13px;display:block;line-height:1.2;letter-spacing:-.01em}
.brand span{font-size:10px;color:var(--dim)}
.sel{background:var(--raised);border:1px solid var(--line2);color:var(--ink);border-radius:999px;
 padding:8px 14px;font-size:12px;cursor:pointer;transition:border-color .15s}
.sel:hover{border-color:var(--dim)}
.sel:focus{outline:2px solid var(--accent-bg2);border-color:var(--accent)}
.lbl{font-size:10px;color:var(--dim);letter-spacing:.07em;text-transform:uppercase;margin-right:-7px}
.spacer{flex:1}
.themebtn{background:var(--raised);border:1px solid var(--line2);color:var(--mut);border-radius:999px;
 width:32px;height:32px;display:grid;place-items:center;cursor:pointer;font-size:13px;transition:.15s}
.themebtn:hover{color:var(--ink);border-color:var(--dim)}
.asof{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;background:var(--med-bg);border:1px solid var(--med-line);
 color:var(--stale);border-radius:999px;padding:6px 12px;font-size:11px;font-weight:550}
.body{display:grid;grid-template-columns:212px 1fr;min-height:0}
.side{background:var(--chrome);border-right:1px solid var(--line);padding:14px 10px;overflow-y:auto}
.main{padding:30px 34px 80px;overflow-y:auto;min-width:0}
.view{display:none}.view.on{display:block}
.topbar{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px;gap:16px}
.eyebrow{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);
 font-weight:700;display:block;margin-bottom:7px}
.topbar h3{font-size:27px;font-weight:680;letter-spacing:-.028em;line-height:1.18}
.topbar .when{color:var(--mut);font-size:13.5px;margin-top:7px;line-height:1.5}
/* ============ CARDS ============ */
.kpis{display:grid;gap:12px;margin-bottom:24px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:17px 16px 15px;
 position:relative;box-shadow:var(--shadow);transition:border-color .15s,transform .15s,box-shadow .15s;
 display:flex;flex-direction:column;align-items:center;text-align:center;min-height:126px}
.khead{display:flex;align-items:center;justify-content:center;gap:7px;min-height:14px;max-width:100%}
.kpi .lab{font-size:9px;color:var(--dim);line-height:1.3;letter-spacing:.11em;text-transform:uppercase;
 font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.kpi .val{font-size:31px;font-weight:680;letter-spacing:-.038em;white-space:nowrap;color:var(--ink);
 overflow:hidden;text-overflow:ellipsis;margin:11px 0 0;line-height:1.05;flex:1;max-width:100%;
 display:flex;align-items:center;justify-content:center}
.kpi .cur{font-size:13px;color:var(--dim);font-weight:520;letter-spacing:0;margin-left:5px}
.cx{font-size:14px;color:var(--dim);font-weight:660;letter-spacing:.01em;margin-right:5px}
.mag{font-size:20px;color:var(--mut);font-weight:660;letter-spacing:-.02em;margin-left:1px}
.afig .cx{font-size:11.5px;margin-right:3px}
.kpi .delta{font-size:10.5px;margin-top:11px;padding-top:10px;border-top:1px solid var(--line);
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.3;width:100%;min-height:15px}
.up{color:var(--ok)}.dn{color:var(--crit)}.flat{color:var(--dim)}
.flag{flex:none;font-size:8px;padding:3px 8px;border-radius:999px;white-space:nowrap;
 font-weight:650;background:var(--med-bg);color:var(--stale);border:1px solid var(--med-line);
 letter-spacing:.02em}
.flag.f-ok{background:var(--ok-bg);color:var(--ok);border-color:var(--ok-line)}
.flag.f-med{background:var(--med-bg);color:var(--stale);border-color:var(--med-line)}
.flag.f-high{background:var(--high-bg);color:var(--high);border-color:var(--high-line)}
.flag.f-crit{background:var(--crit-bg);color:var(--crit);border-color:var(--crit-line)}
.flag.f-dim{background:var(--dim-bg);color:var(--dim);border-color:var(--line2,var(--line))}
.sect{font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--dim);font-weight:700;
 margin:28px 0 12px;display:flex;justify-content:space-between;align-items:center}
/* ============ ALERTS ============ */
.alert{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;
 margin-bottom:11px;border-left:3px solid var(--line2);box-shadow:var(--shadow)}
.alert.crit{border-left-color:var(--crit)}.alert.high{border-left-color:var(--high)}
.alert.med{border-left-color:var(--med)}.alert.info{border-left-color:var(--info)}
.arow{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}
.awhat{font-size:14.5px;font-weight:580;line-height:1.45;letter-spacing:-.012em}
.awhy{font-size:12px;color:var(--mut);margin-top:4px;line-height:1.5}
.asw{font-size:12px;color:var(--ok);margin-top:6px;font-weight:530}
.afig{font:660 19px var(--sans);white-space:nowrap;letter-spacing:-.028em}
.afig small{font-size:10.5px;color:var(--dim);font-weight:500;letter-spacing:0}
.ameta{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px;align-items:center}
.chip{background:var(--raised);border:1px solid var(--line2);border-radius:999px;padding:4px 11px;
 font-size:10.5px;color:var(--mut);white-space:nowrap}
.chip b{color:var(--ink);font-weight:550}
.chip.src{border-color:var(--accent-dim);color:var(--accent-ink);cursor:pointer;transition:.15s}
.chip.src:hover{background:var(--accent-bg2);border-color:var(--accent)}
.chip.own{border-color:var(--line2)}
.acts{display:flex;gap:6px;margin-top:11px;flex-wrap:wrap;align-items:center}
.btn{background:var(--raised);border:1px solid var(--line2);color:var(--mut);border-radius:999px;
 padding:7px 14px;font-size:11.5px;cursor:pointer;font-weight:530;transition:.15s;
 white-space:nowrap;flex:none}
.btn:hover{color:var(--ink);border-color:var(--dim)}
.btn.pri{background:var(--solid);border-color:var(--solid);color:#fff}
.btn.pri:hover{filter:brightness(1.08)}
.btn.dgr{color:var(--crit);border-color:var(--crit-line)}
/* ============ TABLES ============ */
table.dt{width:100%;border-collapse:collapse;font-size:12.5px}
table.dt th{text-align:left;color:var(--dim);font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;
 padding:10px 11px;border-bottom:1px solid var(--line2);font-weight:700}
table.dt td{padding:11px 11px;border-bottom:1px solid var(--line);vertical-align:middle}
table.dt tr:hover td{background:var(--hover)}
.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:550}
.lnk{color:var(--accent);text-decoration:none;font-family:var(--mono);font-size:11.5px;cursor:pointer}
.lnk:hover{text-decoration:underline}
.tag{font-size:10.5px;padding:4px 11px;border-radius:999px;font-weight:620;display:inline-block;
 letter-spacing:.01em;white-space:nowrap}
.t-od{background:var(--crit-bg);color:var(--crit)}
.t-ok{background:var(--ok-bg);color:var(--ok)}
.t-wt{background:var(--high-bg);color:var(--high)}
.t-dr{background:var(--dim-bg);color:var(--dim)}
.grid{display:grid;gap:10px}
.bk{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:17px 16px 15px;
 cursor:pointer;box-shadow:var(--shadow);transition:border-color .15s,transform .15s,box-shadow .15s;
 display:flex;flex-direction:column;min-height:126px}
.bk:has(.n){text-align:center;align-items:center;min-height:126px;justify-content:flex-start;padding-top:17px}
.bk:has(.n):not(:has(.v))::after{content:"";display:block;width:100%;margin-top:11px;padding-top:10px;
 border-top:1px solid var(--line);min-height:15px}
.bk:has(.n) .l{max-width:100%}
.bk>.khead{order:-1;width:100%}
.bk .flag{flex:none;font-size:8px;padding:3px 8px;border-radius:999px;white-space:nowrap;
 letter-spacing:.02em;font-weight:650;border:1px solid transparent}
.bk .n small{font-size:12px;color:var(--dim);font-weight:520;margin-left:5px;letter-spacing:0}
.bk .n .cx{font-size:14px}
.bk.q .l{font-size:11px;text-transform:none;letter-spacing:.005em;font-weight:580;color:var(--ink)}
.bk .bar{height:4px;background:var(--line);border-radius:3px;width:100%;margin-top:11px;overflow:hidden}
.bk .bar>i{display:block;height:100%;border-radius:3px}
.kpi:hover,.bk:hover{border-color:var(--accent);transform:translateY(-2px);
 box-shadow:0 4px 10px rgba(0,0,0,.18),0 12px 28px rgba(0,0,0,.22)}
.bk .n{font-size:31px;font-weight:680;letter-spacing:-.038em;line-height:1.05;margin-top:11px;
 flex:1;display:flex;align-items:center;justify-content:center}
.bk .l{font-size:9px;color:var(--dim);line-height:1.3;min-width:0;letter-spacing:.11em;order:-1;
 text-transform:uppercase;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bk .v{font-size:10.5px;color:var(--mut);margin-top:11px;padding-top:10px;border-top:1px solid var(--line);
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%;min-height:15px}
.note{background:var(--surface);border:1px solid var(--line);border-radius:var(--r2);padding:18px 20px;
 margin-top:18px;box-shadow:var(--shadow)}
.note h4{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--accent);
 margin-bottom:9px;font-weight:700}
.note ul{margin-left:17px;color:var(--mut);font-size:12.5px}
.note li{margin:6px 0}.note b{color:var(--ink)}
/* ============ ASK ============ */
.askbox{background:var(--surface);border:1px solid var(--line2);border-radius:999px;padding:15px 22px;
 margin-bottom:13px;display:flex;gap:11px;align-items:center;box-shadow:var(--shadow)}
.askbox input{flex:1;background:none;border:none;color:var(--ink);font:14.5px var(--sans);outline:none}
.askbox input::placeholder{color:var(--dim)}
.ans{background:var(--surface);border:1px solid var(--line);border-radius:var(--r2);padding:16px 18px;
 margin-bottom:13px;box-shadow:var(--shadow)}
.ans p{font-size:13.5px;line-height:1.65;margin-bottom:11px}
.srcs{display:flex;gap:7px;flex-wrap:wrap;padding-top:12px;border-top:1px solid var(--line)}
.gate{background:var(--crit-bg);border:1px solid var(--crit-line);border-radius:var(--r);
 padding:14px 16px;margin-bottom:13px}
.gate .gt{font-size:12px;font-weight:640;color:var(--crit);margin-bottom:6px}
.gate p{font-size:12.5px;color:var(--mut);line-height:1.6}
.tstate{display:flex;margin:15px 0}
.ts{flex:1;text-align:center;font-size:10.5px;padding:8px 5px;background:var(--surface);
 border:1px solid var(--line);color:var(--dim)}
.ts:first-child{border-radius:7px 0 0 7px}.ts:last-child{border-radius:0 7px 7px 0}
.ts.done{background:var(--ok-bg);color:var(--ok);border-color:var(--ok-line)}
.ts.now{background:var(--high-bg);color:var(--high);border-color:var(--high-line);font-weight:650}
.kv{display:grid;grid-template-columns:140px 1fr;gap:7px 13px;font-size:12.5px}
.kv dt{color:var(--dim)}.kv dd{font-weight:520}
/* ============ DRAWER ============ */
.scrim{position:fixed;inset:0;background:var(--scrim);opacity:0;pointer-events:none;
 transition:opacity .18s;z-index:40;backdrop-filter:blur(2px)}
.scrim.on{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;width:640px;max-width:94vw;height:100vh;background:var(--panel);
 border-left:1px solid var(--line2);z-index:50;transform:translateX(100%);
 transition:transform .22s cubic-bezier(.32,.72,0,1);overflow-y:auto;padding:20px 22px;
 box-shadow:var(--shadow2)}
.drawer.on{transform:none}
.dhead{display:flex;justify-content:space-between;align-items:flex-start;padding-bottom:13px;
 border-bottom:1px solid var(--line);margin-bottom:14px}
.dhead .dt{font-size:11px;color:var(--accent);letter-spacing:.05em;text-transform:uppercase;font-weight:650}
.dhead h4{font-size:15.5px;font-weight:640;margin-top:4px;letter-spacing:-.01em}
.chain{margin:7px 0 15px}
.cstep{display:flex;gap:11px;align-items:flex-start;padding:8px 0;position:relative}
.cdot{width:9px;height:9px;border-radius:50%;flex:none;margin-top:5px;background:var(--ok)}
.cdot.pend{background:var(--line2);border:1.5px solid var(--dim)}
.cline{position:absolute;left:4px;top:19px;bottom:-4px;width:1px;background:var(--line2)}
.cstep .ct{font-size:12.5px;font-weight:540}
.cstep .cs{font-size:11px;color:var(--dim)}
.banner{background:var(--accent-bg);border:1px solid var(--accent-dim);border-radius:var(--r);
 padding:12px 15px;margin-bottom:15px;font-size:12.5px;color:var(--mut);line-height:1.6}
.banner b{color:var(--ink)}
.warn{background:var(--high-bg);border:1px solid var(--high-line);border-radius:var(--r);
 padding:13px 15px;margin-top:13px;font-size:12.5px;color:var(--mut);line-height:1.6}
.warn b{color:var(--high)}
.denied{text-align:center;padding:80px 20px;color:var(--dim)}
.denied .big{font-size:36px;margin-bottom:12px}
.denied h4{font-size:16px;color:var(--ink);margin-bottom:8px}
.denied p{font-size:13px;max-width:440px;margin:0 auto;line-height:1.65}
.hide{display:none!important}
@media(max-width:900px){
 .body{grid-template-columns:1fr}.side{display:none}
 .main{padding:16px 15px 70px}.drawer{width:100%}
 .topnav{gap:9px}.lbl{display:none}
}

"""
