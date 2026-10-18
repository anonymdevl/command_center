# -*- coding: utf-8 -*-
"""The skin of the blocks every screen is made of. Restyle, phase 5 (18 Oct 2026).

Cards, tiles, panels, tables, tags, flags, tabs, alerts, buttons, notes and the drawer,
restyled to the approved mockup. What changes is appearance -- surface, edge, corner,
type, colour, hover. What does not: layout, the class names hydrate.js finds cards by,
the labels, and the two things Michael asked for by name in the first build -- a
hairline above every card's footnote and the chevron that says a card opens.

This is a layer, appended after the generators' own rules and before shell.py, so it
wins where the two disagree. The generators still own layout; this file owns the look.
Moving every rule here would have meant rewriting nineteen screens' worth of layout
for no visible gain, which is the opposite of what the restyle promised.
"""

BLOCKS_CSS = """
/* ============ BLOCKS SKIN (blocks.py) ============ */

/* ---- screen headings ---- */
.topbar h3{font-size:var(--fs-4xl);font-weight:var(--fw-semibold);letter-spacing:-.03em;line-height:1.12}
.topbar .when{color:var(--mut)}
/* The heading's column may shrink, so a long greeting ellipsises (greeting.js) instead of
   pushing the screen wider than a phone. */
.topbar>div:first-child{min-width:0;flex:1 1 auto}
.topbar h3.hello{max-width:100%}
@container panel (max-width:520px){.topbar h3{font-size:clamp(26px,8.5cqi,var(--fs-4xl))}}

/* ---- section labels and banners ---- */
.sect{font-size:var(--fs-lg);letter-spacing:-.015em;text-transform:none;color:var(--ink);
 font-weight:var(--fw-semibold);align-items:baseline}
.sect .lnk{font-size:var(--fs-sm);text-transform:none;letter-spacing:0;font-family:var(--sans)}
.banner{background:var(--raised);border:0;border-radius:var(--r-sm);color:var(--mut);font-size:var(--fs-sm)}

/* ---- figure cards and tiles ---- */
.kpi,.bk{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);box-shadow:none;
 padding:20px 20px 16px;container-type:inline-size;transition:border-color .18s,box-shadow .18s,transform .18s}
.kpi:hover,.bk:hover,
[data-theme="light"] .kpi:hover,[data-theme="light"] .bk:hover,
.kpi.clickable:hover{border-color:var(--line2);box-shadow:var(--shadow-hover);transform:translateY(-1px)}
/* Labels in plain words, not tracked capitals: the small-caps label over every number
   was one of the strongest "generated" tells. */
.kpi .lab,.bk .l{font-size:var(--fs-xs);font-weight:var(--fw-medium);color:var(--mut);letter-spacing:0;
 text-transform:none}
.kpi .val,.bk .n{font-size:clamp(26px,13cqi,40px);font-weight:var(--fw-semibold);letter-spacing:-.035em;
 color:var(--ink);font-variant-numeric:normal}
/* Proportional digits on a standalone figure: Manrope's tabular 1 leaves a gap
   ("1 .55M"). Tables keep tabular digits, where columns have to line up. */
.cx{font-size:.42em;color:var(--mut);font-weight:var(--fw-semibold);letter-spacing:0;margin-right:.3em;
 vertical-align:.12em}
.mag{font-size:.6em;color:var(--mut);font-weight:var(--fw-semibold);letter-spacing:-.01em}
.kpi .delta,.bk .v{font-size:var(--fs-xs);color:var(--mut)}
.bk .n small{font-size:var(--fs-sm);color:var(--mut);font-weight:var(--fw-medium)}

/* ---- flags on cards: provenance, said quietly ---- */
.flag,.bk .flag{border-color:transparent;font-weight:var(--fw-semibold);padding:3px 8px}

/* ---- status tags in tables and lists: a tinted pill with a dot ---- */
.tag{display:inline-flex;align-items:center;gap:6px;border:0;font-weight:var(--fw-semibold);
 font-size:var(--fs-xs);padding:4px 10px 4px 9px;letter-spacing:0}
.tag::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;flex:none;opacity:.9}

/* ---- panels become cards ---- */
.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:18px 20px;
 margin-bottom:16px}
.panel .panel{border:0;padding:0;background:none;margin-bottom:10px}
.ph{align-items:baseline;margin-bottom:12px;gap:10px}
.ph b{font-size:var(--fs-lg);font-weight:var(--fw-semibold);letter-spacing:-.015em}
/* The subtitle sits under the title, as in the mockup, instead of wrapping beside it. */
.ph > div > span,.ph > div > b + span{display:block;margin:3px 0 0;font-size:var(--fs-xs);color:var(--mut)}
.ph span{font-size:var(--fs-xs);color:var(--mut)}
.ph .lnk,.ph a{font-family:var(--sans);font-weight:var(--fw-semibold)}

/* ---- tables ---- */
table.dt{font-size:var(--fs-sm)}
table.dt th,[data-theme="light"] table.dt th{font-size:var(--fs-xs);font-weight:var(--fw-medium);color:var(--mut);
 letter-spacing:0;text-transform:none;padding:10px 12px;border-bottom:1px solid var(--line)}
table.dt td{padding:12px 12px;border-bottom:1px solid var(--line)}
table.dt tr:last-child td{border-bottom:0}
table.dt tbody tr{transition:background .12s}
table.dt tr:hover td{background:var(--hover)}

/* ---- tabs: a segmented control ---- */
.tabbar{display:inline-flex;gap:2px;border:1px solid var(--line2);border-radius:var(--r-pill);padding:3px;
 margin:20px 0 18px;border-bottom:1px solid var(--line2);max-width:100%}
.tab{border:0;border-radius:var(--r-pill);padding:7px 16px;font-size:var(--fs-sm);
 font-weight:var(--fw-semibold);color:var(--mut);white-space:nowrap;margin:0}
.tab:hover{color:var(--ink)}
.tab.on{background:var(--raised);color:var(--ink);border:0;box-shadow:inset 0 0 0 1px var(--line2)}

/* ---- alerts: a severity label instead of a coloured edge; figure in its own box;
   owner and source on a quiet footer line with the actions at its right ---- */
.alert{background:var(--surface);border:1px solid var(--line);border-left:1px solid var(--line);
 border-radius:var(--r);padding:20px 22px 0;margin-bottom:12px;box-shadow:none;
 display:flex;flex-wrap:wrap;align-items:center;transition:border-color .15s}
/* The generators' severity edge (.alert.crit and the quiet-signal variant) goes. */
.alert:is(.crit,.high,.med,.info),[data-signal] .alert{border-left:1px solid var(--line)}
.alert:hover,.alert:is(.crit,.high,.med,.info):hover{border-color:var(--line2)}
.alert>*{flex:1 1 100%;min-width:0}
.alert>.arow{gap:20px;align-items:flex-start;padding-bottom:16px}
.alert>.arow>div:first-child{min-width:0}
.asev{display:inline-flex;align-items:center;gap:6px;font-size:var(--fs-2xs);font-weight:var(--fw-semibold);
 padding:3px 10px 3px 8px;border-radius:var(--r-pill);margin-bottom:10px;border:1px solid var(--line2);
 color:var(--mut);background:var(--raised)}
.asev::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.alert.crit .asev{color:var(--crit);background:var(--crit-bg);border-color:var(--crit-line)}
.alert.high .asev{color:var(--high);background:var(--high-bg);border-color:var(--high-line)}
.alert.med .asev{color:var(--stale);background:var(--med-bg);border-color:var(--med-line)}
.alert.info .asev{color:var(--info);background:var(--accent-bg2);border-color:var(--accent-dim)}
.awhat{font-size:var(--fs-lg);font-weight:var(--fw-semibold);letter-spacing:-.015em;line-height:1.35}
.awhy{font-size:var(--fs-sm);color:var(--mut);margin-top:6px;line-height:1.55}
.asw{font-size:var(--fs-sm);color:var(--ink2);font-weight:var(--fw-medium);margin-top:10px;line-height:1.5}
.afig{flex:none;font-weight:var(--fw-semibold);font-size:var(--fs-2xl);letter-spacing:-.03em;
 background:var(--raised);border-radius:var(--r-sm);padding:12px 16px;text-align:right;line-height:1.15}
.afig .cx{color:var(--mut);font-weight:var(--fw-medium)}
.afig small{display:block;margin-top:2px}
.alert>.ameta,.alert>.acts{border-top:1px solid var(--line);padding:12px 0 14px;margin:0}
.alert>.ameta{flex:1 1 auto;gap:6px}
.alert>.acts{flex:0 0 auto;margin-left:auto;padding-left:12px;gap:8px}
.alert>.ameta+.acts{margin-left:0}
.alert .chip{font-size:var(--fs-xs);padding:4px 10px;background:transparent;border-color:transparent;color:var(--mut)}
.alert .chip b{font-weight:var(--fw-semibold)}
.alert .chip.src{background:var(--accent-bg2);border-color:transparent;color:var(--accent-ink)}
.alert .chip.src:hover{border-color:var(--accent)}
.alert .chip.src::after{content:" \\2197";font-size:.9em}
.alert>div:not([class]),.alert>.tstate{margin-bottom:14px}
.chip{font-size:var(--fs-xs);padding:5px 12px;background:var(--surface)}
@container panel (max-width:620px){
 .alert>.arow{flex-direction:column}
 .afig{text-align:left}
 .alert>.acts{flex-basis:100%;border-top:0;padding:0 0 14px;margin-top:-4px}
}

/* ---- the alert's "more" menu (legacy/actions.js) ---- */
.amenu{position:relative;display:inline-flex}
.amenu-b{width:34px;height:34px;border-radius:var(--r-pill);border:1px solid var(--line2);background:var(--surface);
 color:var(--mut);font-size:var(--fs-md);line-height:1;cursor:pointer;display:inline-flex;align-items:center;
 justify-content:center}
.amenu-b:hover,.amenu.on .amenu-b{color:var(--ink);border-color:var(--ink2)}
.amenu-b:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.amenu-l{position:absolute;top:calc(100% + 6px);right:0;min-width:200px;background:var(--surface);
 border:1px solid var(--line2);border-radius:var(--r-sm);padding:6px;box-shadow:var(--shadow2);z-index:50;display:none}
.amenu.flip .amenu-l{top:auto;bottom:calc(100% + 6px)}
.amenu.on .amenu-l{display:block}
.amenu-l button{display:block;width:100%;text-align:left;background:none;border:0;border-radius:var(--r-xs);
 padding:9px 12px;font:inherit;font-size:var(--fs-sm);font-weight:var(--fw-medium);color:var(--ink);cursor:pointer;
 white-space:nowrap}
.amenu-l button:hover,.amenu-l button:focus-visible{background:var(--hover);outline:0}
.amenu-l button.dgr{color:var(--crit)}
.act-notice{flex:1 1 100%;font-size:var(--fs-sm);color:var(--mut);background:var(--raised);border-radius:var(--r-sm);
 padding:10px 14px;margin:0 0 14px;line-height:1.5}
.panel>.act-notice{margin:12px 0 0}

/* ---- the live queue on Today, Approvals and Outstanding Tasks (legacy/work.js) ---- */
.work-list{display:block}
.work-list>.sect:first-child{margin-top:8px}
.work-empty{display:flex;flex-direction:column;gap:4px;background:var(--surface);border:1px dashed var(--line2);
 border-radius:var(--r);padding:22px 22px;margin-bottom:12px;color:var(--mut);font-size:var(--fs-sm)}
.work-empty b{color:var(--ink);font-size:var(--fs-md);font-weight:var(--fw-semibold)}
.work-detail{flex:1 1 100%;font-size:var(--fs-sm);color:var(--mut);background:var(--raised);
 border-radius:var(--r-sm);padding:10px 14px;margin:0 0 14px;white-space:pre-line;line-height:1.5}
.work-more{display:inline-block;margin:2px 0 14px;background:none;border:0;padding:0;cursor:pointer;
 color:var(--accent-ink);font-size:var(--fs-sm)}
a.chip.src{text-decoration:none}
a.btn{text-decoration:none;display:inline-flex;align-items:center}
.work-banner{margin:0 0 14px}
div.work-table{overflow-x:auto;margin-bottom:12px}
div.work-table table.dt{min-width:560px}
.alert .chip.src{white-space:normal;max-width:100%}

/* ---- Home in the approved mockup's layout (legacy/home.js) ---- */
.hero-row{grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-bottom:16px}
.bk.hero.sig{min-height:220px;padding:22px 22px 20px}
.bk.hero .l{font-size:var(--fs-lg);color:var(--ink);font-weight:var(--fw-semibold);letter-spacing:-.01em}
.bk.hero .hd{font-size:var(--fs-sm);color:var(--ink2);margin-top:4px;max-width:28ch;line-height:1.45}
.bk.hero .v{order:0;margin-top:10px;font-size:var(--fs-sm);font-weight:var(--fw-medium);color:var(--ink)}
.bk.hero .n{font-size:clamp(34px,16cqi,52px)}
@container panel (max-width:760px){.hero-row{grid-template-columns:1fr}.bk.hero.sig{min-height:170px}}

.mbrief{position:relative;overflow:hidden;background:#141518;color:#f4f5f7;border-radius:var(--r);
 padding:22px 24px;margin-bottom:16px}
.mbrief::after{content:"";position:absolute;right:-60px;top:-80px;width:340px;height:340px;border-radius:50%;
 background:radial-gradient(circle,var(--accent) 0%,transparent 65%);opacity:.32;pointer-events:none}
:root[data-theme="dark"] .mbrief{background:var(--raised);border:1px solid var(--line2)}
.mb-tag{display:inline-flex;align-items:center;gap:6px;font-size:var(--fs-xs);font-weight:var(--fw-semibold);
 border:1px solid rgba(255,255,255,.18);border-radius:var(--r-pill);padding:4px 12px;color:#dfe2e8}
.mbrief h4{position:relative;z-index:1;font-size:var(--fs-2xl);font-weight:var(--fw-semibold);letter-spacing:-.02em;
 margin:12px 0 14px;color:#fff;line-height:1.25}
.mb-chips{position:relative;z-index:1;display:flex;flex-wrap:wrap;gap:8px}
.mb-chip{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);color:#e6e8ec;border-radius:var(--r-pill);
 padding:7px 14px;font:inherit;font-size:var(--fs-sm);cursor:pointer;text-align:left}
.mb-chip:hover{background:rgba(255,255,255,.14)}
.mb-chip b{color:#fff;font-weight:var(--fw-semibold)}
.mb-chip.crit b{color:#ffb4ab}.mb-chip.high b{color:#ffd29a}

.panel.debt{padding:0;overflow:hidden}
.debt-h{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:20px 22px 14px;flex-wrap:wrap}
.debt-h h4,.gp-h h4{font-size:var(--fs-lg);font-weight:var(--fw-semibold);margin:0;letter-spacing:-.01em;
 display:flex;align-items:center;gap:8px}
.debt-h p,.gp-h p{margin:4px 0 0;font-size:var(--fs-sm);color:var(--mut)}
.debt-n{font-size:var(--fs-xs);font-weight:var(--fw-medium);color:var(--mut);border:1px solid var(--line2);
 border-radius:var(--r-pill);padding:2px 10px}
.debt-n:empty{display:none}
.segc{display:inline-flex;gap:2px;border:1px solid var(--line2);border-radius:var(--r-pill);padding:3px;
 max-width:100%;overflow-x:auto}
.segc button{border:0;background:none;border-radius:var(--r-pill);padding:6px 14px;font:inherit;font-size:var(--fs-sm);
 font-weight:var(--fw-semibold);color:var(--mut);cursor:pointer;white-space:nowrap}
.segc button.on{background:var(--raised);color:var(--ink);box-shadow:inset 0 0 0 1px var(--line2)}
.debt-cols{display:grid;grid-template-columns:minmax(0,1fr) 120px minmax(0,260px);gap:12px;padding:10px 22px;
 border-top:1px solid var(--line);border-bottom:1px solid var(--line);font-size:var(--fs-xs);color:var(--mut)}
.debt-cols span:last-child{text-align:right}
.debt-row{display:grid;grid-template-columns:minmax(0,1fr) 120px minmax(0,260px);gap:12px;align-items:center;width:100%;
 padding:14px 22px;border:0;border-bottom:1px solid var(--line);background:none;font:inherit;color:var(--ink);
 cursor:pointer;text-align:left}
.debt-row:last-child{border-bottom:0}
.debt-row:hover{background:var(--hover)}
.debt-who{display:flex;align-items:center;gap:12px;min-width:0}
.av2{flex:none;width:38px;height:38px;border-radius:12px;background:var(--t2);color:var(--ink2);display:grid;
 place-items:center;font-size:var(--fs-xs);font-weight:var(--fw-bold)}
.debt-name{display:flex;flex-direction:column;min-width:0}
.debt-name b{font-weight:var(--fw-semibold);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.debt-name span{font-size:var(--fs-xs);color:var(--mut)}
.dpill{justify-self:start;font-size:var(--fs-xs);font-weight:var(--fw-semibold);border-radius:var(--r-pill);padding:3px 10px;
 border:1px solid var(--line2);color:var(--mut)}
.dpill::before{content:"● ";font-size:.8em}
.dpill.crit{color:var(--crit);background:var(--crit-bg);border-color:var(--crit-line)}
.dpill.high{color:var(--high);background:var(--high-bg);border-color:var(--high-line)}
.dpill.ok{color:var(--ok);background:var(--ok-bg);border-color:var(--ok-line)}
.debt-amt{display:flex;align-items:center;justify-content:flex-end;gap:12px}
.debt-a{display:flex;flex-direction:column;align-items:flex-end}
.debt-a b{font-size:var(--fs-lg);font-weight:var(--fw-semibold);letter-spacing:-.01em;font-variant-numeric:tabular-nums}
.debt-a small{font-size:var(--fs-2xs);color:var(--mut)}
.debt-arrow{color:var(--dim)}
.debt-more{padding:12px 22px;font-size:var(--fs-xs);color:var(--mut);border-top:1px solid var(--line)}
@container panel (max-width:720px){
 .debt-cols{display:none}
 .debt-row{grid-template-columns:minmax(0,1fr) auto;row-gap:8px}
 .debt-amt{grid-column:1 / -1;justify-content:flex-start}
 .debt-a{align-items:flex-start}
}

.counts{display:flex;flex-direction:column;gap:8px;margin:0 0 16px}
.count{display:flex;align-items:center;gap:14px;padding:14px 20px;border-radius:var(--r);background:var(--raised);
 cursor:pointer;border:1px solid var(--line)}
.count b{font-size:var(--fs-3xl);font-weight:var(--fw-semibold);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.count span:last-child{color:var(--mut);font-size:var(--fs-sm)}
.count-i{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:var(--surface);
 color:var(--mut);font-size:var(--fs-3xs)}
.count.dark{background:#141518;color:#fff;border-color:transparent}
.count.dark span:last-child{color:#c9ccd3}
.count.dark .count-i{background:var(--accent);color:var(--on-accent)}
:root[data-theme="dark"] .count.dark{background:var(--surface);border-color:var(--line2)}

.home-pair{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-bottom:16px}
@container panel (max-width:760px){.home-pair{grid-template-columns:1fr}}
.home-pair>.panel{margin:0}
.gp-h{display:flex;justify-content:space-between;margin-bottom:8px}
.gauge{position:relative;display:flex;flex-direction:column;align-items:center;min-height:180px;justify-content:center}
.dial{width:min(100%,300px);height:auto}
.gauge-mid{position:absolute;top:47%;left:50%;transform:translate(-50%,-50%);display:flex;align-items:baseline;gap:2px}
.gauge-mid b{font-size:var(--fs-5xl);font-weight:var(--fw-semibold);letter-spacing:-.04em}
.gauge-mid small{color:var(--mut);font-size:var(--fs-md)}
.gauge-say{font-size:var(--fs-sm);font-weight:var(--fw-semibold);margin-top:-6px;text-align:center}
.gauge-how{display:block;margin:12px auto 0;background:none;border:0;padding:0;cursor:pointer;font-size:var(--fs-sm);
 color:var(--accent-ink)}
.gauge-parts{list-style:none;margin:12px 0 0;padding:12px 0 0;border-top:1px solid var(--line);display:flex;
 flex-direction:column;gap:8px;font-size:var(--fs-sm)}
.gauge-parts li{display:flex;gap:10px;align-items:baseline}
.gauge-parts li b{min-width:2.4em;font-variant-numeric:tabular-nums}
.gauge-parts .gauge-note{color:var(--mut);font-size:var(--fs-xs)}
.topc-bar{display:flex;gap:4px;height:8px;margin:6px 0 14px}
.topc-bar i{display:block;border-radius:var(--r-pill);background:var(--line2)}
.topc-bar i.c0,.topc-dot.c0{background:var(--accent)}.topc-bar i.c1,.topc-dot.c1{background:var(--ok)}
.topc-bar i.c2,.topc-dot.c2{background:var(--ink)}.topc-bar i.c3,.topc-dot.c3{background:var(--high)}
.topc-bar i.c4,.topc-dot.c4{background:var(--dim)}
.topc-l{list-style:none;margin:0;padding:0}
.topc-row{display:flex;align-items:center;gap:12px;width:100%;padding:9px 0;border:0;background:none;font:inherit;
 color:var(--ink);cursor:pointer;text-align:left;border-bottom:1px solid var(--line)}
.topc-l li:last-child .topc-row{border-bottom:0}
.topc-row:hover .topc-name{text-decoration:underline}
.topc-dot{width:8px;height:8px;border-radius:50%;flex:none}
.topc-name{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:var(--fw-medium)}
.topc-pct{font-size:var(--fs-xs);font-weight:var(--fw-semibold);border:1px solid var(--line2);border-radius:var(--r-pill);
 padding:2px 10px;font-variant-numeric:tabular-nums}
.home-wait{padding:18px 22px;color:var(--mut);font-size:var(--fs-sm)}
.topc .home-wait,.gauge .home-wait{padding:18px 0}

/* ---- live alerts (legacy/alerts.js) ---- */
.asev.astate{margin-left:6px;color:var(--ok);background:var(--ok-bg);border-color:var(--ok-line)}
.alert-flash{box-shadow:0 0 0 3px var(--accent-bg2);border-color:var(--accent)!important;transition:box-shadow .3s}
.alert-live-list{display:block}

/* ---- the action dialog: assign, request evidence, escalate, raise a finding ---- */
.dlg-scrim{position:fixed;inset:0;background:var(--scrim);z-index:120;display:flex;align-items:center;
 justify-content:center;padding:16px}
.dlg{width:min(480px,100%);max-height:calc(100vh - 32px);overflow:auto;background:var(--surface);
 border:1px solid var(--line2);border-radius:20px;box-shadow:var(--shadow2);padding:24px;color:var(--ink);
 font-family:var(--sans)}
.dlg h3{font-size:var(--fs-xl);font-weight:var(--fw-semibold);letter-spacing:-.02em;margin:0}
.dlg-sub{font-size:var(--fs-sm);color:var(--mut);margin:6px 0 0;line-height:1.5}
.dlg-hint{font-size:var(--fs-xs);color:var(--dim);margin:8px 0 0}
.dlg label{display:block;font-size:var(--fs-xs);font-weight:var(--fw-semibold);color:var(--mut);margin:16px 0 6px}
.dlg select,.dlg input,.dlg textarea{width:100%;box-sizing:border-box;font:inherit;font-size:var(--fs-sm);
 color:var(--ink);background:var(--bg);border:1px solid var(--line2);border-radius:var(--r-sm);padding:10px 12px}
.dlg textarea{resize:vertical;line-height:1.5}
.dlg select:focus,.dlg input:focus,.dlg textarea:focus{outline:0;border-color:var(--accent);
 box-shadow:0 0 0 3px var(--accent-bg2)}
.dlg-err{margin-top:14px;font-size:var(--fs-sm);color:var(--crit);background:var(--crit-bg);
 border-radius:var(--r-sm);padding:10px 12px}
.dlg-acts{display:flex;justify-content:flex-end;gap:8px;margin-top:20px;flex-wrap:wrap}
.dlg-acts a{text-decoration:none}
.dlg-foot{font-size:var(--fs-xs);color:var(--dim);margin:14px 0 0;text-align:right}
.dlg-ok{width:44px;height:44px;border-radius:50%;background:var(--ok-bg);color:var(--ok);display:flex;
 align-items:center;justify-content:center;font-size:var(--fs-xl);font-weight:var(--fw-bold);margin-bottom:14px}

/* ---- buttons ---- */
.btn,[data-theme="light"] .btn{background:var(--surface);border:1px solid var(--line2);color:var(--ink);
 font-size:var(--fs-sm);font-weight:var(--fw-semibold);padding:8px 16px;border-radius:var(--r-pill)}
.btn:hover,[data-theme="light"] .btn:hover{background:var(--surface);border-color:var(--ink2);color:var(--ink)}
.btn.pri{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.btn.pri:hover{background:var(--accent);filter:brightness(1.07)}
.lnk{font-family:var(--sans);font-weight:var(--fw-semibold)}

/* ---- notes, warnings, "not yet measured" ---- */
.note,[data-theme="light"] .note{background:var(--raised);border:0;border-radius:var(--r);box-shadow:none;
 padding:18px 22px}
.note h4{font-size:var(--fs-md);letter-spacing:-.01em;text-transform:none;color:var(--ink);
 font-weight:var(--fw-semibold)}
.warn{border-radius:var(--r-sm);border-color:transparent}
.thin{border-radius:var(--r-sm);font-size:var(--fs-sm)}

/* ---- charts and bars ---- */
.chartwrap,[data-theme="light"] .chartwrap{border-radius:var(--r-sm);box-shadow:none;border-color:var(--line)}
.bartrack{border-radius:var(--r-pill);height:10px;background:var(--raised)}
.barfill{border-radius:var(--r-pill)}
.barlab,.barval{font-size:var(--fs-sm)}

/* ---- the Ask screen's own box ---- */
.askbox,[data-theme="light"] .askbox{border:1px solid var(--line2);box-shadow:none;padding:14px 22px}
.askbox{align-items:center}
.askbox .askbox-i{color:var(--accent);flex:none}
/* Whole questions as suggestions are longer than a phone is wide: they wrap there
   rather than run off the screen or lose their ending. */
#asksugg .btn{max-width:100%;text-align:left}
@container panel (max-width:560px){#asksugg .btn{white-space:normal}}
.askbox:focus-within{border-color:var(--accent-dim);box-shadow:0 0 0 5px var(--accent-bg)}

/* ---- the signature card, on every screen (build.py signature_tiles) ---- */
/* Tinted, left-aligned, a cut corner with a round arrow -- the approved mockup, on every
   .kpi card and .bk tile. The tints (--t1..--t3) are tokens in both themes and cycle
   along each row. */
/* :is(.kpi,.bk).sig rather than .sig: the generators' .bk:has(.n) centres a tile and is
   as specific as two classes, so a one-class rule lost and left question tiles centred. */
:is(.kpi,.bk).sig{--cut:76px;--r-cut:20px;background:var(--t1);border:0;text-align:left;align-items:flex-start;
 min-height:176px;padding:20px 20px 18px;position:relative;overflow:visible;display:flex;
 flex-direction:column}
.sig:nth-child(3n+2){background:var(--t2)}
.sig:nth-child(3n+3){background:var(--t3)}
.sig:hover,[data-theme="light"] .sig:hover,.kpi.sig.clickable:hover{border:0;
 box-shadow:var(--shadow-hover);transform:translateY(-2px)}
.sig > .khead{justify-content:flex-start;width:100%}
.sig .l,.sig .lab{color:var(--ink2);font-weight:var(--fw-semibold);font-size:var(--fs-sm)}
:is(.kpi,.bk).sig .n,:is(.kpi,.bk).sig .val{justify-content:flex-start;font-size:clamp(28px,14cqi,44px);margin-top:auto;padding-top:16px;
 text-align:left;width:100%}
/* The footnote may take a second line beside the arrow: cutting it off with an
   ellipsis hid what the figure means. */
:is(.kpi,.bk).sig .v,:is(.kpi,.bk).sig .delta{border-top:0;padding-top:0;margin-top:6px;max-width:calc(100% - var(--cut));
 color:var(--ink2);white-space:normal;overflow:visible;text-overflow:clip;line-height:1.4;text-align:left}
.sig > .flag[data-prov]{align-self:flex-start;margin-top:8px}
.sig:has(.n):not(:has(.v))::after{display:none}
.sig.clickable::before,.sig.clickable::after,.kpi.sig.clickable:hover::after{display:none}
:is(.kpi,.bk).sig .bar{max-width:calc(100% - var(--cut));margin-left:0}
.sig-cut{position:absolute;right:0;bottom:0;width:var(--cut);height:var(--cut);background:var(--surface);
 border-top-left-radius:var(--r-cut);pointer-events:none}
.sig-cut::before,.sig-cut::after{content:"";position:absolute;width:var(--r-cut);height:var(--r-cut);
 background:radial-gradient(circle at 0 0,transparent calc(var(--r-cut) - .5px),var(--surface) var(--r-cut))}
.sig-cut::before{right:0;top:calc(var(--r-cut) * -1)}
.sig-cut::after{left:calc(var(--r-cut) * -1);bottom:0}
.sig-go{position:absolute;right:6px;bottom:6px;width:58px;height:58px;border-radius:50%;background:var(--ink);
 color:var(--surface);display:grid;place-items:center;transition:transform .2s;pointer-events:none}
.sig:hover .sig-go{transform:rotate(45deg)}
/* A card inside a panel sits on the panel's surface, which the cut must match. */
.panel .sig-cut,.panel .sig-cut::before,.panel .sig-cut::after{--surface:var(--surface)}

/* ---- a written report, under the Reports table (legacy/reports.js) ---- */
.rp{margin-top:18px}
.rp-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.rp-head b{font-size:var(--fs-xl);font-weight:var(--fw-semibold);letter-spacing:-.02em}
.rp-sub{font-size:var(--fs-xs);color:var(--mut)}
.rp-acts{margin-left:auto;display:flex;gap:8px}
.rp-body{font-size:var(--fs-md);line-height:1.62;color:var(--ink2)}
.rp-body b{color:var(--ink)}

/* ---- the analyst's answers (markdown.js, charts.js) ---- */
/* The same sizes as the screens: body text at --fs-sm, the headline one step up. */
.md{font-size:var(--fs-sm);line-height:1.62;color:var(--ink2)}
.md > *{margin:0 0 12px}
.md b{color:var(--ink);font-weight:var(--fw-semibold)}
.md .md-lead{font-size:var(--fs-md);line-height:1.55;color:var(--ink);font-weight:var(--fw-medium);
 letter-spacing:-.01em}
.md h4{font-size:var(--fs-md);font-weight:var(--fw-semibold);letter-spacing:-.015em;color:var(--ink);
 margin:22px 0 8px}
.md h5{font-size:var(--fs-sm);font-weight:var(--fw-semibold);color:var(--ink);margin:18px 0 6px}
.md ul,.md ol{padding-left:20px}
.md li{margin:5px 0;padding-left:2px}
.md li::marker{color:var(--dim)}
.md pre{background:var(--raised);border-radius:var(--r-sm);padding:12px 14px;overflow-x:auto;
 font:var(--fs-xs)/1.5 var(--mono)}
.md .md-rec,.md .md-proj{list-style:none;border-left:0;border-radius:var(--r-sm);padding:11px 14px 11px 40px;
 position:relative;color:var(--ink)}
.md .md-rec{background:var(--accent-bg)}
.md .md-rec::before{content:"";position:absolute;left:14px;top:14px;width:14px;height:14px;border-radius:50%;
 background:var(--accent);box-shadow:inset 0 0 0 4px var(--accent-bg)}
.md .md-proj{background:var(--raised)}
.md .md-proj::before{content:"";position:absolute;left:15px;top:15px;width:12px;height:12px;
 border:2px dashed var(--dim);border-radius:50%}
.md li.md-rec,.md li.md-proj{margin-left:-20px;margin-bottom:8px}
.md-table{border:1px solid var(--line);border-radius:var(--r-sm);overflow-x:auto;margin:6px 0 14px}
.md-table table.dt{margin:0}
.md-table table.dt th{background:var(--raised);padding:9px 12px}
.md-table table.dt td{padding:10px 12px}
.md-table table.dt tbody tr:nth-child(even) td{background:var(--zebra)}
.md-table td.r,.md-table th.r{text-align:right;font-variant-numeric:tabular-nums}
/* Key figures: the same tints as the cards, so an answer and a screen are one product. */
/* Cards size to what they hold and move to the next row when there is no room, rather
   than squeezing a figure onto two lines. */
.md-figs{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 8px}
.md-fig{background:var(--t1);border-radius:var(--r-sm);padding:12px 14px;display:flex;flex-direction:column;gap:2px;
 flex:1 1 auto;min-width:130px;max-width:100%}
.md-fig:nth-child(3n+2){background:var(--t2)}
.md-fig:nth-child(3n+3){background:var(--t3)}
.md-fig-l{font-size:var(--fs-xs);color:var(--ink2);font-weight:var(--fw-semibold)}
.md-fig-v{font-size:var(--fs-xl);white-space:nowrap;font-weight:var(--fw-semibold);letter-spacing:-.025em;color:var(--ink);
 line-height:1.15;margin-top:4px;overflow-wrap:anywhere}
.md-fig-n{font-size:var(--fs-xs);color:var(--mut)}
.md-fig.t-bad .md-fig-v{color:var(--crit)}
.md-fig.t-warn .md-fig-v{color:var(--high)}
.md-fig.t-good .md-fig-v{color:var(--ok)}
.md-chart{margin:14px 0;padding:16px 18px 14px;border:1px solid var(--line);border-radius:var(--r-sm);
 background:var(--surface)}
.md-chart figcaption{font-size:var(--fs-sm);font-weight:var(--fw-semibold);color:var(--ink);margin-bottom:12px}
.md-bars{display:flex;flex-direction:column;gap:9px}
.md-bar{display:grid;grid-template-columns:minmax(90px,34%) minmax(0,1fr) auto;gap:12px;align-items:center;
 font-size:var(--fs-sm)}
.md-bar-l{color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.md-bar-t{height:10px;background:var(--raised);border-radius:var(--r-pill);overflow:hidden}
.md-bar-t i{display:block;height:100%;background:var(--accent);border-radius:var(--r-pill)}
.md-bar:first-child .md-bar-t i{filter:saturate(1.15)}
.md-bar-v{font-variant-numeric:tabular-nums;font-weight:var(--fw-semibold);color:var(--ink);white-space:nowrap}
.md-line{width:100%;height:auto;display:block;overflow:visible}
.md-grid{stroke:var(--line);stroke-width:1}
.md-axis{fill:var(--mut);font-size:var(--fs-3xs);font-family:var(--sans)}
.md-area{fill:var(--accent-bg)}
.md-ln{fill:none;stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}
.md-ln.s0,.md-legend i.s0{stroke:var(--accent);background:var(--accent)}
.md-ln.s1,.md-legend i.s1{stroke:var(--ok);background:var(--ok)}
.md-ln.s2,.md-legend i.s2{stroke:var(--dim);background:var(--dim)}
.md-pt.s0{fill:var(--accent)}.md-pt.s1{fill:var(--ok)}.md-pt.s2{fill:var(--dim)}
.md-donut{display:flex;align-items:center;gap:24px;flex-wrap:wrap}
.md-donut svg{width:150px;height:150px;flex:none}
.md-sl.c0,.md-legend i.c0{fill:var(--accent);background:var(--accent)}
.md-sl.c1,.md-legend i.c1{fill:var(--ok);background:var(--ok)}
.md-sl.c2,.md-legend i.c2{fill:var(--high);background:var(--high)}
.md-sl.c3,.md-legend i.c3{fill:var(--dim);background:var(--dim)}
.md-sl.c4,.md-legend i.c4{fill:var(--crit);background:var(--crit)}
.md-sl.c5,.md-legend i.c5{fill:var(--med);background:var(--med)}
.md-dt{fill:var(--ink);font-size:var(--fs-xs);font-weight:var(--fw-semibold);font-family:var(--sans)}
.md-legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:var(--fs-xs);color:var(--mut);margin-top:10px}
.md-legend span{display:inline-flex;align-items:center;gap:7px}
.md-legend i{width:9px;height:9px;border-radius:3px;flex:none}
.md-legend.stack{flex-direction:column;gap:9px;margin:0;flex:1;min-width:180px}
.md-legend.stack b{margin-left:auto;color:var(--ink);font-variant-numeric:tabular-nums}

/* ---- follow-up questions under an answer ---- */
.md-follow{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:16px 0 4px;padding-top:14px;
 border-top:1px solid var(--line)}
.md-follow-t{font-size:var(--fs-xs);font-weight:var(--fw-semibold);color:var(--mut);margin-right:4px}
.md-follow-q{border:1px solid var(--line2);background:var(--surface);color:var(--ink);border-radius:var(--r-pill);
 padding:7px 14px;font:var(--fw-medium) var(--fs-sm) var(--sans);cursor:pointer;text-align:left;
 transition:border-color .15s,background .15s}
.md-follow-q:hover{border-color:var(--accent);background:var(--accent-bg)}
.md-follow-q:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* ---- the Ask AI screen as a conversation ---- */
.thread-tools{display:flex;justify-content:flex-end;margin:6px 0 4px}
#sout2{display:flex;flex-direction:column;gap:22px;margin-top:10px}
.turn{display:flex;flex-direction:column;gap:10px;scroll-margin-top:20px}
.turn-q{align-self:flex-end;max-width:min(78%,640px);background:var(--accent-bg);color:var(--ink);
 border-radius:20px 20px 6px 20px;padding:11px 16px;font-size:var(--fs-md);font-weight:var(--fw-medium);
 line-height:1.5}
.turn-a > .panel{margin:0;border:0;padding:0;background:none}
.turn-a .askans{padding:0}
.turn-a .ap-think{padding:6px 0}

/* ---- the last small-capital labels, in plain words like the rest ---- */
.eyebrow,.dhead .dt,.askchecked-t{text-transform:none;letter-spacing:0;font-size:var(--fs-xs);
 font-weight:var(--fw-semibold);color:var(--mut)}

/* ---- an answer on the Ask AI screen ---- */
.ans-q{font-size:var(--fs-lg);font-weight:var(--fw-semibold);letter-spacing:-.02em;line-height:1.3;
 padding:4px 16px 0}

/* ---- the records drawer ---- */
.drawer{border-left:0;border-radius:24px 0 0 24px;box-shadow:var(--shadow2)}
"""
