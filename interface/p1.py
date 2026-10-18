# -*- coding: utf-8 -*-
CSS = """
/* ============ TOKENS ============ */
:root{
 /* Dark. Neutral near-black, not blue-navy: the navy-and-periwinkle pairing was the
    single strongest "generated" tell of the first design. Restyle, 17 Oct 2026. */
 --bg:#0c0d0f; --chrome:#0c0d0f; --surface:#141518; --raised:#1a1b1f; --panel:#141518;
 --line:#222428; --line2:#2c2f35; --hover:rgba(255,255,255,.04); --zebra:rgba(255,255,255,.02);
 --ink:#f2f3f5; --ink2:#c8cbd1; --mut:#8d929b; --dim:#6b707a;
 --accent:#6a7fef; --accent-ink:#9aa8f4; --accent-dim:#262c4d;
 --accent-bg:rgba(106,127,239,.10); --accent-bg2:rgba(106,127,239,.17); --on-accent:#111317;
 --crit:#f0695e; --crit-bg:rgba(240,105,94,.12); --crit-line:rgba(240,105,94,.32);
 --high:#e8994a; --high-bg:rgba(232,153,74,.11); --high-line:rgba(232,153,74,.30);
 --med:#e3c063; --med-bg:rgba(227,192,99,.11); --med-line:rgba(227,192,99,.30);
 --ok:#3fc48e; --ok-bg:rgba(63,196,142,.11); --ok-line:rgba(63,196,142,.30);
 --ok-glow:rgba(63,196,142,.45);
 --info:#6a7fef; --stale:#e3c063; --dim-bg:rgba(141,146,155,.13); --thin-bg:rgba(141,146,155,.05);
 --star:#c9d2ff; --scrim:rgba(6,7,8,.66);
 --sun:#e3c063; --dawn:#e8994a; --moon:#9aa8f4;
 --shadow:0 1px 2px rgba(0,0,0,.35); --shadow2:0 24px 60px -20px rgba(0,0,0,.72),0 0 0 1px #26282d;
 --shadow-hover:0 4px 10px rgba(0,0,0,.25),0 14px 32px -14px rgba(0,0,0,.55);
 --grad:linear-gradient(#6a7fef,#6a7fef);
 --solid:#6a7fef;

 /* Corners. Large on surfaces, small on controls; pills only where a thing is a pill. */
 --r-xs:8px; --r-sm:12px; --r:20px; --r2:24px; --r-pill:999px;
 /* Type scale. Every font size in the stylesheet is one of these. */
 --fs-3xs:10px; --fs-2xs:11px; --fs-xs:12px; --fs-sm:13px; --fs-md:14px; --fs-lg:16px;
 --fs-xl:20px; --fs-2xl:24px; --fs-3xl:28px; --fs-4xl:32px; --fs-5xl:36px;
 /* Four weights. The first design used fifteen, 520 to 680; on a variable font every
    one renders exactly, so the hierarchy blurred into near-identical greys of bold. */
 --fw-regular:400; --fw-medium:500; --fw-semibold:600; --fw-bold:700;
 /* Spacing, on a 4px grid. */
 --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:20px; --sp-6:24px; --sp-8:32px; --sp-10:40px;
 --mono:ui-monospace,'SF Mono',Menlo,Consolas,monospace;
 --sans:'Manrope Variable',Manrope,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
}
[data-theme="light"]{
 --bg:#f3f4f6; --chrome:#f3f4f6; --surface:#ffffff; --raised:#f5f6f8; --panel:#ffffff;
 --line:#ecedf0; --line2:#dfe1e6; --hover:rgba(17,19,23,.04); --zebra:rgba(17,19,23,.02);
 --ink:#111317; --ink2:#3b3f47; --mut:#646973; --dim:#7c818b; --solid:#2443e8;
 --accent:#2443e8; --accent-ink:#1c34b5; --accent-dim:#c9d1fa;
 --accent-bg:rgba(36,67,232,.08); --accent-bg2:rgba(36,67,232,.14); --on-accent:#ffffff;
 --crit:#c2392f; --crit-bg:rgba(194,57,47,.09); --crit-line:rgba(194,57,47,.26);
 --high:#a85a0a; --high-bg:rgba(168,90,10,.10); --high-line:rgba(168,90,10,.26);
 --med:#856307; --med-bg:rgba(133,99,7,.11); --med-line:rgba(133,99,7,.26);
 --ok:#127a55; --ok-bg:rgba(18,122,85,.09); --ok-line:rgba(18,122,85,.26);
 --ok-glow:rgba(18,122,85,.28);
 --info:#2443e8; --stale:#a85a0a; --dim-bg:rgba(100,105,115,.10); --thin-bg:rgba(100,105,115,.045);
 --star:#2443e8; --scrim:rgba(17,19,23,.32); --sun:#a85e09; --dawn:#a85a0a; --moon:#2443e8;
 --shadow:0 1px 2px rgba(17,19,23,.04),0 8px 24px -12px rgba(17,19,23,.10);
 --shadow2:0 24px 60px -20px rgba(17,19,23,.28),0 2px 6px rgba(17,19,23,.06);
 --shadow-hover:0 2px 6px rgba(17,19,23,.06),0 14px 32px -14px rgba(17,19,23,.18);
 --grad:linear-gradient(#2443e8,#2443e8);
}

/* ---- light-only refinements ---- */
[data-theme="light"] table.dt th{color:var(--mut);border-bottom-color:var(--line2)}
[data-theme="light"] .btn{background:var(--surface)}
[data-theme="light"] .btn:hover{background:var(--raised)}
[data-theme="light"] .chartwrap,[data-theme="light"] .ans,[data-theme="light"] .askbox,
[data-theme="light"] .note{box-shadow:var(--shadow)}

/* ============ BASE ============ */
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--bg);color:var(--ink);font:var(--fs-md)/1.55 var(--sans);
 -webkit-font-smoothing:antialiased;overflow:hidden;
 transition:background .18s,color .18s}
button{font-family:inherit}
/* Tabular figures only where numbers line up: figures and table columns. On running
   text Manrope's tabular digits leave a gap after every 1 -- "9.1 8M", "1 9 Aug". */
.val,.n,.num,.barval,.afig,.dsum-n,table.dt td,.dt td{font-variant-numeric:tabular-nums}
/* The shell -- sidebar, bar, content panel -- is styled in shell.py, and only there. */
.view{display:none}.view.on{display:block}
.topbar{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px;gap:16px}
.eyebrow{font-size:var(--fs-3xs);letter-spacing:.16em;text-transform:uppercase;color:var(--accent);
 font-weight:var(--fw-bold);display:block;margin-bottom:7px}
.topbar h3{font-size:var(--fs-3xl);font-weight:var(--fw-bold);letter-spacing:-.028em;line-height:1.18}
.topbar .when{color:var(--mut);font-size:var(--fs-md);margin-top:7px;line-height:1.5;
 letter-spacing:0} /* the headline's tight tracking is inherited as px, twice as tight at 14px */
/* ============ CARDS ============ */
.kpis{display:grid;gap:12px;margin-bottom:24px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:17px 16px 15px;
 position:relative;box-shadow:var(--shadow);transition:border-color .15s,transform .15s,box-shadow .15s;
 display:flex;flex-direction:column;align-items:center;text-align:center;min-height:126px}
.khead{display:flex;align-items:center;justify-content:center;gap:7px;min-height:14px;max-width:100%}
.kpi .lab{font-size:var(--fs-3xs);color:var(--dim);line-height:1.3;letter-spacing:.06em;text-transform:uppercase;
 font-weight:var(--fw-bold);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.kpi .val{font-size:var(--fs-4xl);font-weight:var(--fw-bold);letter-spacing:-.038em;white-space:nowrap;color:var(--ink);
 overflow:hidden;text-overflow:ellipsis;margin:11px 0 0;line-height:1.05;flex:1;max-width:100%;
 display:flex;align-items:center;justify-content:center}
.kpi .cur{font-size:var(--fs-sm);color:var(--dim);font-weight:var(--fw-medium);letter-spacing:0;margin-left:5px}
.cx{font-size:var(--fs-md);color:var(--dim);font-weight:var(--fw-bold);letter-spacing:.01em;margin-right:5px}
.mag{font-size:var(--fs-xl);color:var(--mut);font-weight:var(--fw-bold);letter-spacing:-.02em;margin-left:1px}
.afig .cx{font-size:var(--fs-xs);margin-right:3px}
.kpi .delta{font-size:var(--fs-2xs);margin-top:11px;padding-top:10px;border-top:1px solid var(--line);
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.3;width:100%;min-height:15px}
.up{color:var(--ok)}.dn{color:var(--crit)}.flat{color:var(--dim)}
.flag{flex:none;font-size:var(--fs-3xs);padding:3px 7px;border-radius:var(--r-pill);white-space:nowrap;
 font-weight:var(--fw-bold);background:var(--med-bg);color:var(--stale);border:1px solid var(--med-line);
 letter-spacing:0}
.flag.f-ok{background:var(--ok-bg);color:var(--ok);border-color:var(--ok-line)}
.flag.f-med{background:var(--med-bg);color:var(--stale);border-color:var(--med-line)}
.flag.f-high{background:var(--high-bg);color:var(--high);border-color:var(--high-line)}
.flag.f-crit{background:var(--crit-bg);color:var(--crit);border-color:var(--crit-line)}
.flag.f-dim{background:var(--dim-bg);color:var(--dim);border-color:var(--line2,var(--line))}
.sect{font-size:var(--fs-3xs);letter-spacing:.15em;text-transform:uppercase;color:var(--dim);font-weight:var(--fw-bold);
 margin:28px 0 12px;display:flex;justify-content:space-between;align-items:center}
/* ============ ALERTS ============ */
.alert{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;
 margin-bottom:11px;border-left:3px solid var(--line2);box-shadow:var(--shadow)}
.alert.crit{border-left-color:var(--crit)}.alert.high{border-left-color:var(--high)}
.alert.med{border-left-color:var(--med)}.alert.info{border-left-color:var(--info)}
.arow{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}
.awhat{font-size:var(--fs-md);font-weight:var(--fw-semibold);line-height:1.45;letter-spacing:-.012em}
.awhy{font-size:var(--fs-xs);color:var(--mut);margin-top:4px;line-height:1.5}
.asw{font-size:var(--fs-xs);color:var(--ok);margin-top:6px;font-weight:var(--fw-medium)}
.afig{font:var(--fw-bold) var(--fs-xl) var(--sans);white-space:nowrap;letter-spacing:-.028em}
.afig small{font-size:var(--fs-2xs);color:var(--dim);font-weight:var(--fw-medium);letter-spacing:0}
.ameta{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px;align-items:center}
.chip{background:var(--raised);border:1px solid var(--line2);border-radius:var(--r-pill);padding:4px 11px;
 font-size:var(--fs-2xs);color:var(--mut);white-space:nowrap}
.chip b{color:var(--ink);font-weight:var(--fw-semibold)}
.chip.src{border-color:var(--accent-dim);color:var(--accent-ink);cursor:pointer;transition:.15s}
.chip.src:hover{background:var(--accent-bg2);border-color:var(--accent)}
.chip.own{border-color:var(--line2)}
.acts{display:flex;gap:6px;margin-top:11px;flex-wrap:wrap;align-items:center}
.btn{background:var(--raised);border:1px solid var(--line2);color:var(--mut);border-radius:var(--r-pill);
 padding:7px 14px;font-size:var(--fs-xs);cursor:pointer;font-weight:var(--fw-medium);transition:.15s;
 white-space:nowrap;flex:none}
.btn:hover{color:var(--ink);border-color:var(--dim)}
.btn.pri{background:var(--solid);border-color:var(--solid);color:var(--on-accent)}
.btn.pri:hover{filter:brightness(1.08)}
.btn.dgr{color:var(--crit);border-color:var(--crit-line)}
/* ============ TABLES ============ */
table.dt{width:100%;border-collapse:collapse;font-size:var(--fs-sm)}
table.dt th{text-align:left;color:var(--dim);font-size:var(--fs-3xs);letter-spacing:.12em;text-transform:uppercase;
 padding:10px 11px;border-bottom:1px solid var(--line2);font-weight:var(--fw-bold)}
table.dt td{padding:11px 11px;border-bottom:1px solid var(--line);vertical-align:middle}
table.dt tr:hover td{background:var(--hover)}
.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:var(--fw-semibold)}
.lnk{color:var(--accent);text-decoration:none;font-family:var(--mono);font-size:var(--fs-xs);cursor:pointer}
.lnk:hover{text-decoration:underline}
.tag{font-size:var(--fs-2xs);padding:4px 11px;border-radius:var(--r-pill);font-weight:var(--fw-semibold);display:inline-block;
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
.bk .flag{flex:none;font-size:var(--fs-3xs);padding:3px 7px;border-radius:var(--r-pill);white-space:nowrap;
 letter-spacing:0;font-weight:var(--fw-bold);border:1px solid transparent}
.bk .n small{font-size:var(--fs-xs);color:var(--dim);font-weight:var(--fw-medium);margin-left:5px;letter-spacing:0}
.bk .n .cx{font-size:var(--fs-md)}
.bk.q .l{font-size:var(--fs-2xs);text-transform:none;letter-spacing:.005em;font-weight:var(--fw-semibold);color:var(--ink)}
.bk .bar{height:4px;background:var(--line);border-radius:3px;width:100%;margin-top:11px;overflow:hidden}
.bk .bar>i{display:block;height:100%;border-radius:3px}
.kpi:hover,.bk:hover{border-color:var(--accent);transform:translateY(-2px);
 box-shadow:var(--shadow-hover)}
.bk .n{font-size:var(--fs-4xl);font-weight:var(--fw-bold);letter-spacing:-.038em;line-height:1.05;margin-top:11px;
 flex:1;display:flex;align-items:center;justify-content:center}
.bk .l{font-size:var(--fs-3xs);color:var(--dim);line-height:1.3;min-width:0;letter-spacing:.06em;order:-1;
 text-transform:uppercase;font-weight:var(--fw-bold);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bk .v{font-size:var(--fs-2xs);color:var(--mut);margin-top:11px;padding-top:10px;border-top:1px solid var(--line);
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%;min-height:15px}
.note{background:var(--surface);border:1px solid var(--line);border-radius:var(--r2);padding:18px 20px;
 margin-top:18px;box-shadow:var(--shadow)}
.note h4{font-size:var(--fs-2xs);letter-spacing:.09em;text-transform:uppercase;color:var(--accent);
 margin-bottom:9px;font-weight:var(--fw-bold)}
.note ul{margin-left:17px;color:var(--mut);font-size:var(--fs-sm)}
.note li{margin:6px 0}.note b{color:var(--ink)}
/* ============ ASK ============ */
.askbox{background:var(--surface);border:1px solid var(--line2);border-radius:var(--r-pill);padding:15px 22px;
 margin-bottom:13px;display:flex;gap:11px;align-items:center;box-shadow:var(--shadow)}
.askbox input{flex:1;background:none;border:none;color:var(--ink);font:var(--fs-md) var(--sans);outline:none}
.askbox input::placeholder{color:var(--dim)}
.ans{background:var(--surface);border:1px solid var(--line);border-radius:var(--r2);padding:16px 18px;
 margin-bottom:13px;box-shadow:var(--shadow)}
.ans p{font-size:var(--fs-md);line-height:1.65;margin-bottom:11px}
.srcs{display:flex;gap:7px;flex-wrap:wrap;padding-top:12px;border-top:1px solid var(--line)}
.gate{background:var(--crit-bg);border:1px solid var(--crit-line);border-radius:var(--r);
 padding:14px 16px;margin-bottom:13px}
.gate .gt{font-size:var(--fs-xs);font-weight:var(--fw-bold);color:var(--crit);margin-bottom:6px}
.gate p{font-size:var(--fs-sm);color:var(--mut);line-height:1.6}
.tstate{display:flex;margin:15px 0}
.ts{flex:1;text-align:center;font-size:var(--fs-2xs);padding:8px 5px;background:var(--surface);
 border:1px solid var(--line);color:var(--dim)}
.ts:first-child{border-radius:var(--r-xs) 0 0 var(--r-xs)}.ts:last-child{border-radius:0 var(--r-xs) var(--r-xs) 0}
.ts.done{background:var(--ok-bg);color:var(--ok);border-color:var(--ok-line)}
.ts.now{background:var(--high-bg);color:var(--high);border-color:var(--high-line);font-weight:var(--fw-bold)}
.kv{display:grid;grid-template-columns:140px 1fr;gap:7px 13px;font-size:var(--fs-sm)}
.kv dt{color:var(--dim)}.kv dd{font-weight:var(--fw-medium)}
/* ============ DRAWER ============ */
.scrim{position:fixed;inset:0;background:var(--scrim);opacity:0;pointer-events:none;
 transition:opacity .18s;z-index:40;backdrop-filter:blur(2px)}
.scrim.on{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;width:640px;max-width:94vw;height:100vh;background:var(--panel);
 border-left:1px solid var(--line2);z-index:50;transform:translateX(100%);
 transition:transform .22s cubic-bezier(.32,.72,0,1);overflow-y:auto;padding:20px 22px;
 box-shadow:var(--shadow2)}
.drawer.on{transform:none}
/* The answer, before the rows. A drawer that opens onto a hundred records and no
   sentence makes the reader do the summarising, which is the work they opened it to
   avoid. */
.dsum{padding:14px 16px;margin:0 0 14px;border:1px solid var(--line);border-radius:var(--r-sm);
background:var(--raised)}
.dsum-n{font-size:var(--fs-2xl);font-weight:var(--fw-bold);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.dsum-t{font-size:var(--fs-xs);color:var(--mut);margin-top:5px;line-height:1.55}
.dsum-t b{color:var(--txt);font-weight:var(--fw-bold)}
/* Through to the document itself. Provenance stops being a column of codes. */
.dlink{color:var(--accent);text-decoration:none;font-weight:var(--fw-semibold);white-space:nowrap}
.dlink:hover{text-decoration:underline}
.dhead{display:flex;justify-content:space-between;align-items:flex-start;padding-bottom:13px;
 border-bottom:1px solid var(--line);margin-bottom:14px}
.dhead .dt{font-size:var(--fs-2xs);color:var(--accent);letter-spacing:.05em;text-transform:uppercase;font-weight:var(--fw-bold)}
.dhead h4{font-size:var(--fs-lg);font-weight:var(--fw-bold);margin-top:4px;letter-spacing:-.01em}
.chain{margin:7px 0 15px}
.cstep{display:flex;gap:11px;align-items:flex-start;padding:8px 0;position:relative}
.cdot{width:9px;height:9px;border-radius:50%;flex:none;margin-top:5px;background:var(--ok)}
.cdot.pend{background:var(--line2);border:1.5px solid var(--dim)}
.cline{position:absolute;left:4px;top:19px;bottom:-4px;width:1px;background:var(--line2)}
.cstep .ct{font-size:var(--fs-sm);font-weight:var(--fw-semibold)}
.cstep .cs{font-size:var(--fs-2xs);color:var(--dim)}
.banner{background:var(--accent-bg);border:1px solid var(--accent-dim);border-radius:var(--r);
 padding:12px 15px;margin-bottom:15px;font-size:var(--fs-sm);color:var(--mut);line-height:1.6}
.banner b{color:var(--ink)}
.warn{background:var(--high-bg);border:1px solid var(--high-line);border-radius:var(--r);
 padding:13px 15px;margin-top:13px;font-size:var(--fs-sm);color:var(--mut);line-height:1.6}
.warn b{color:var(--high)}
.denied{text-align:center;padding:80px 20px;color:var(--dim)}
.denied .big{font-size:var(--fs-5xl);margin-bottom:12px}
.denied h4{font-size:var(--fs-lg);color:var(--ink);margin-bottom:8px}
.denied p{font-size:var(--fs-sm);max-width:440px;margin:0 auto;line-height:1.65}
.hide{display:none!important}
@media(max-width:900px){.drawer{width:100%}}

"""
