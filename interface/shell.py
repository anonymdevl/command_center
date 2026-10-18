# -*- coding: utf-8 -*-
"""The shell: sidebar, bar, and the panel the screens sit in. The one owner of their CSS.

Restyle, phase 3 (17-18 Oct 2026), from the approved mockup. These rules used to be
spread over p1.py, build.py, tidy.py and signals.py, each overriding the last; they
were removed from all four and live here only, appended last so nothing downstream
can quietly win.

Only shell classes are styled here. None of them appears in views.json -- checked
before the move -- so this file cannot change anything inside a screen.
"""

SHELL_CSS = """
/* ============ SHELL (shell.py is the only owner) ============ */
.shell{display:grid;grid-template-columns:252px minmax(0,1fr);gap:14px;height:100vh;
 padding:14px;background:var(--bg)}

/* ---- sidebar ---- */
.side{display:flex;flex-direction:column;min-height:0;padding:6px 4px 4px}
.brand{display:flex;align-items:center;gap:9px;padding:6px 6px 18px;margin:0 6px;
 border-bottom:1px solid var(--line2)}
.logo{width:34px;height:34px;border-radius:11px;background:var(--ink);display:grid;place-items:center;flex:none}
.logo i{width:14px;height:14px;border-radius:50%;border:3px solid var(--accent);display:block;
 box-shadow:6px 0 0 -1px var(--bg)}
.brand-t{min-width:0}
/* "AI Business Intelligence" is longer than the old name: a step smaller so it fits. */
.brand-t b{display:block;font-size:var(--fs-md);font-weight:var(--fw-semibold);letter-spacing:-.03em;
 white-space:nowrap;line-height:1.25}
.brand-t span{display:block;font-size:var(--fs-2xs);color:var(--mut);letter-spacing:-.005em;line-height:1.35}
.brand{padding-right:2px}
.nav{flex:1;min-height:0;overflow-y:auto;padding:12px 6px 18px;
 scrollbar-width:thin;scrollbar-color:var(--line2) transparent;
 /* The last screens sit below the fold on a laptop; a soft edge says there is more. */
 -webkit-mask-image:linear-gradient(to bottom,#000 calc(100% - 26px),transparent);
 mask-image:linear-gradient(to bottom,#000 calc(100% - 26px),transparent)}
.navsec{font-size:var(--fs-2xs);font-weight:var(--fw-semibold);letter-spacing:.06em;text-transform:uppercase;
 color:var(--dim);padding:14px 12px 5px}
.navgrp:first-child .navsec{padding-top:4px}
.navi{display:flex;align-items:center;gap:11px;height:34px;padding:0 12px;border-radius:11px;
 color:var(--ink2);font-size:var(--fs-md);font-weight:var(--fw-medium);cursor:pointer;white-space:nowrap;
 transition:background .15s,color .15s,box-shadow .15s}
.navi .ic{color:var(--mut);flex:none;transition:color .15s}
.navi span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis}
.navi:hover{background:var(--hover);color:var(--ink)}
.navi.on{background:var(--surface);color:var(--ink);font-weight:var(--fw-semibold);box-shadow:var(--shadow)}
.navi.on .ic{color:var(--accent)}
.navi:focus-visible{outline:2px solid var(--accent);outline-offset:1px}

/* ---- the business being looked at ---- */
.biz{position:relative;margin:4px 6px 0;padding:12px 6px 6px;border-top:1px solid var(--line2)}
.biz-row{display:flex;align-items:center;gap:10px}
.biz-av{width:36px;height:36px;border-radius:11px;background:var(--accent-bg2);color:var(--accent-ink);
 display:grid;place-items:center;font-size:var(--fs-xs);font-weight:var(--fw-bold);flex:none}
.biz-av.sm{width:30px;height:30px;border-radius:var(--r-xs)}
.biz-t{min-width:0}
.biz-t b{display:block;font-size:var(--fs-sm);font-weight:var(--fw-semibold);line-height:1.3}
.asof{display:flex;align-items:center;gap:7px;font-size:var(--fs-xs);color:var(--mut);margin-top:3px;
 white-space:nowrap}
.asof .dot{width:7px;height:7px;border-radius:50%;background:var(--ok);flex:none;
 animation:ccpulse 2.2s ease-out infinite}
/* Behind today: the figures are a snapshot, so the dot says so rather than pulsing
   "live" over data that is not. */
.asof.stale .dot{background:var(--med);animation:none}
.asof.none .dot{background:var(--high);animation:none}
@keyframes ccpulse{0%{box-shadow:0 0 0 0 var(--ok-glow)}100%{box-shadow:0 0 0 7px transparent}}
.biz-sw{margin-left:auto;width:34px;height:34px;flex:none;border:1px solid var(--line2);border-radius:50%;
 background:var(--surface);color:var(--ink2);display:grid;place-items:center;cursor:pointer;
 transition:border-color .15s,color .15s}
.biz-sw:hover:not(:disabled){border-color:var(--ink2)}
.biz-sw:disabled{color:var(--dim);background:transparent;cursor:default}
.biz-sw:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.biz-note{font-size:var(--fs-xs);color:var(--mut);line-height:1.5;padding:10px 12px 6px;border-top:1px solid var(--line);
 margin-top:6px}
.biz-note a{display:block;margin-top:6px;color:var(--accent-ink);font-weight:var(--fw-semibold);text-decoration:none}
.biz-menu{position:absolute;left:0;right:0;bottom:calc(100% + 8px);background:var(--surface);
 border-radius:18px;box-shadow:var(--shadow2);padding:6px;z-index:70}
.biz-opt{display:flex;align-items:center;gap:10px;width:100%;padding:8px;border-radius:var(--r-sm);border:0;
 background:none;text-align:left;cursor:pointer;color:var(--ink);font:inherit}
.biz-opt:hover:not(:disabled),.biz-opt.on{background:var(--raised)}
.biz-opt:disabled{opacity:.5;cursor:not-allowed}
.biz-opt-t{min-width:0}
.biz-opt-t b{display:block;font-size:var(--fs-sm);font-weight:var(--fw-semibold)}
.biz-opt-t small{display:block;font-size:var(--fs-xs);color:var(--mut)}

/* ---- the bar ---- */
.col{display:flex;flex-direction:column;gap:14px;min-width:0;min-height:0}
.topnav{display:flex;align-items:center;gap:12px;flex:none;position:relative;z-index:30}
.askwrap{flex:1;min-width:0;position:relative}
.ask{width:100%;height:56px;display:flex;align-items:center;gap:12px;padding:0 8px 0 20px;
 background:var(--surface);border-radius:var(--r-pill);border:1px solid transparent;box-shadow:var(--shadow);
 transition:border-color .2s,box-shadow .2s}
.ask:focus-within{border-color:var(--accent-dim);box-shadow:0 0 0 5px var(--accent-bg)}
.ask-i{color:var(--accent);flex:none}
.ask input{flex:1;min-width:0;border:0;outline:0;background:none;color:var(--ink);
 font:var(--fw-regular) var(--fs-md) var(--sans)}
.ask input::placeholder{color:var(--mut)}
.ask-k{font:var(--fw-semibold) var(--fs-xs) var(--sans);color:var(--mut);border:1px solid var(--line2);
 border-radius:var(--r-xs);padding:2px 7px;white-space:nowrap}
.ask-go{height:40px;padding:0 18px 0 15px;border-radius:var(--r-pill);border:0;background:var(--accent);
 color:var(--on-accent);font:var(--fw-semibold) var(--fs-sm) var(--sans);display:flex;align-items:center;
 gap:7px;cursor:pointer;white-space:nowrap;transition:filter .15s}
.ask-go:hover{filter:brightness(1.07)}
.ask-go:disabled{opacity:.55;cursor:default;filter:none}
.askwrap.open .ask{border-color:var(--accent-dim);box-shadow:0 0 0 5px var(--accent-bg)}

/* ---- answers under the bar (AskBar.jsx) ---- */
.askpop{position:absolute;left:0;right:0;top:calc(100% + 10px);z-index:40;background:var(--surface);
 border:1px solid var(--line2);border-radius:22px;box-shadow:var(--shadow2);padding:8px;max-height:calc(100vh - 120px);overflow-y:auto;
 scrollbar-width:thin;scrollbar-color:var(--line2) transparent}
.ap-h{font-size:var(--fs-2xs);font-weight:var(--fw-semibold);letter-spacing:.06em;text-transform:uppercase;
 color:var(--dim);padding:10px 14px 6px}
.ap-s{display:flex;align-items:center;gap:12px;width:100%;text-align:left;padding:10px 14px;border:0;
 border-radius:14px;background:none;color:var(--ink2);font:var(--fw-medium) var(--fs-md) var(--sans);cursor:pointer}
.ap-s .ic{color:var(--dim);flex:none}
.ap-s span{flex:1;min-width:0}
.ap-s em{font-style:normal;font-size:var(--fs-xs);color:var(--mut);white-space:nowrap}
.ap-s:hover,.ap-s.hl{background:var(--raised);color:var(--ink)}
.ap-s.hl .ic,.ap-s:hover .ic{color:var(--accent)}
.ap-think{display:flex;align-items:center;gap:14px;padding:16px 14px}
.ap-think div{flex:1;min-width:0}
.ap-think b{display:block;font-weight:var(--fw-semibold);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ap-think span{display:block;font-size:var(--fs-sm);color:var(--mut);margin-top:2px}
.ap-deep{display:flex;align-items:flex-start;gap:14px;background:var(--accent-bg);border-radius:var(--r-sm);
 padding:12px 14px;margin:0 0 14px}
.ap-deep > div{flex:1;min-width:0}
.ap-deep b{display:block;font-weight:var(--fw-semibold);color:var(--ink);font-size:var(--fs-sm)}
.ap-deep > div > span{display:block;font-size:var(--fs-xs);color:var(--ink2);margin-top:2px}
.ap-steps{list-style:none;margin:10px 0 0;padding:0;display:flex;flex-direction:column;gap:6px}
.ap-steps li{position:relative;padding-left:24px;font-size:var(--fs-sm);color:var(--ink2);line-height:1.4}
.ap-steps li::before{content:"";position:absolute;left:3px;top:4px;width:11px;height:11px;border-radius:50%}
.ap-steps li.done{color:var(--mut)}
.ap-steps li.done::before{background:var(--ok);box-shadow:inset 0 0 0 3px var(--ok-bg)}
.ap-steps li.now::before{border:2px solid var(--accent-bg2);border-top-color:var(--accent);
 animation:apspin .8s linear infinite;width:9px;height:9px}
.ap-think{align-items:flex-start}
.ap-spin{width:22px;height:22px;border-radius:50%;border:2.5px solid var(--accent-bg2);
 border-top-color:var(--accent);animation:apspin .8s linear infinite;flex:none}
@keyframes apspin{to{transform:rotate(360deg)}}
.ap-err{padding:16px 14px;color:var(--ink2)}
.ap-err b{color:var(--crit)}
.ap-ans{padding:14px 16px 10px}
.ap-src{display:flex;align-items:center;gap:7px;font-size:var(--fs-xs);color:var(--mut);font-weight:var(--fw-medium)}
.ap-src .ic{color:var(--accent)}
.ap-q{font-size:var(--fs-lg);font-weight:var(--fw-semibold);letter-spacing:-.015em;line-height:1.35;margin:8px 0 10px}
.ap-body{font-size:var(--fs-sm);line-height:1.6;color:var(--ink2)}
/* An answer with a table, chart or figures gets room: the panel grows past the bar,
   up to a reading width, instead of squeezing what is in it. */
.askpop.wide{right:auto;width:max(100%,min(980px,calc(100vw - 320px)))}
.ap-note{background:var(--high-bg);color:var(--ink2);border-radius:var(--r-sm);padding:10px 12px;
 font-size:var(--fs-sm);margin:0 0 12px}
.ap-note.info{background:var(--accent-bg);color:var(--ink)}
.ap-note span{display:block;color:var(--mut);font-size:var(--fs-xs);margin-top:3px;word-break:break-word}
.ap-body b{color:var(--ink)}
.ap-body .panel{margin:0!important;border:0;background:none}
.ap-checked{margin:14px 0 4px;border-top:1px solid var(--line);padding-top:10px;font-size:var(--fs-xs);color:var(--mut)}
.ap-checked summary{cursor:pointer;font-weight:var(--fw-semibold);color:var(--ink2)}
.ap-checked ul{margin:8px 0 0 18px}
.ap-checked li{margin:3px 0;font-family:var(--mono);font-size:var(--fs-3xs);word-break:break-all}
.ap-acts{display:flex;align-items:center;gap:8px;flex-wrap:wrap;border-top:1px solid var(--line);
 margin-top:12px;padding-top:12px}
.ap-gap{flex:1}
.ap-act{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 14px;border-radius:var(--r-pill);
 border:1px solid var(--line2);background:var(--surface);color:var(--ink);cursor:pointer;
 font:var(--fw-semibold) var(--fs-sm) var(--sans);white-space:nowrap;transition:border-color .15s}
.ap-act:hover{border-color:var(--ink2)}
.ap-act.pri{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.ap-act.pri:hover{filter:brightness(1.07)}
.ap-s:focus-visible,.ap-act:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.pill{display:flex;align-items:center;gap:4px;padding:5px;background:var(--surface);border-radius:var(--r-pill);
 box-shadow:var(--shadow);flex:none}
.ib{width:46px;height:46px;border-radius:50%;border:0;background:none;color:var(--mut);display:grid;
 place-items:center;cursor:pointer;transition:background .15s,color .15s}
.ib:hover{background:var(--raised);color:var(--ink)}
.ib.on{background:var(--raised);color:var(--ink);box-shadow:inset 0 0 0 1px var(--line2)}
.ib:focus-visible,.ask-go:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* ---- the alerts bell (components/Bell.jsx) ---- */
.bellw{position:relative}
.ib.bell{position:relative}
.bell-n{position:absolute;top:5px;right:4px;min-width:18px;height:18px;padding:0 5px;border-radius:var(--r-pill);
 background:var(--raised);color:var(--ink);font-size:var(--fs-3xs);font-weight:var(--fw-bold);line-height:18px;
 text-align:center;box-shadow:0 0 0 2px var(--surface)}
.bell-n.fresh{background:var(--crit);color:#fff}
.bellpop{position:absolute;right:0;top:calc(100% + 12px);width:min(380px,calc(100vw - 32px));z-index:60;
 background:var(--surface);border:1px solid var(--line2);border-radius:20px;box-shadow:var(--shadow2);padding:8px}
.bellpop-h{display:flex;align-items:baseline;justify-content:space-between;padding:10px 12px 8px}
.bellpop-h b{font-size:var(--fs-md);font-weight:var(--fw-semibold)}
.bellpop-h span{font-size:var(--fs-xs);color:var(--mut)}
.bellpop-l{list-style:none;margin:0;padding:0;max-height:min(60vh,440px);overflow:auto}
.bellpop-l button{display:flex;gap:10px;align-items:flex-start;width:100%;text-align:left;background:none;border:0;
 border-radius:var(--r-sm);padding:10px 12px;cursor:pointer;color:var(--ink);font:inherit}
.bellpop-l button:hover,.bellpop-l button:focus-visible{background:var(--hover);outline:0}
.bell-dot{flex:none;width:8px;height:8px;border-radius:50%;margin-top:6px;background:var(--dim)}
.bell-dot.crit{background:var(--crit)}.bell-dot.high{background:var(--high)}
.bell-dot.med{background:var(--med)}.bell-dot.info{background:var(--info)}
.bell-t{display:flex;flex-direction:column;gap:2px;min-width:0}
.bell-t b{font-size:var(--fs-sm);font-weight:var(--fw-semibold);line-height:1.35}
.bell-t span{font-size:var(--fs-xs);color:var(--mut)}
.bellpop-e{font-size:var(--fs-sm);color:var(--mut);padding:4px 12px 12px;margin:0}
.bellpop-f{display:flex;justify-content:space-between;gap:12px;border-top:1px solid var(--line);
 padding:10px 12px 6px;margin-top:4px;font-size:var(--fs-sm)}
.bellpop-f .lnk{background:none;border:0;padding:0;cursor:pointer;color:var(--accent-ink);text-decoration:none}
.menu-b{display:none}
.who{display:flex;align-items:center;gap:10px;padding:0 14px 0 4px;min-width:0}
.av{width:44px;height:44px;border-radius:50%;background:var(--accent-bg2);color:var(--accent-ink);
 display:grid;place-items:center;font:var(--fw-bold) var(--fs-sm) var(--sans);flex:none}
.whotxt{min-width:0}
.whotxt b{display:block;font-size:var(--fs-sm);font-weight:var(--fw-semibold);white-space:nowrap;
 max-width:170px;overflow:hidden;text-overflow:ellipsis;line-height:1.3}
.whotxt span{display:block;font-size:var(--fs-xs);color:var(--mut);white-space:nowrap}

/* ---- appearance menu ---- */
.appear{position:relative}
.appearmenu{position:absolute;top:calc(100% + 14px);right:-4px;width:280px;background:var(--surface);
 border-radius:20px;box-shadow:var(--shadow2);padding:16px;z-index:60;display:none}
.appearmenu.on{display:block}
.amsec{font-size:var(--fs-2xs);font-weight:var(--fw-semibold);letter-spacing:.06em;text-transform:uppercase;
 color:var(--dim);margin:0 0 10px}
.amsec:not(:first-child){margin-top:18px}
.seg{display:flex;background:var(--raised);border:1px solid var(--line);border-radius:var(--r-pill);padding:3px}
.seg button{flex:1;background:none;border:none;color:var(--mut);font:var(--fw-semibold) var(--fs-xs) var(--sans);
 padding:7px 4px;border-radius:var(--r-pill);cursor:pointer;white-space:nowrap;transition:.14s}
.seg button:hover{color:var(--ink)}
.seg button.on{background:var(--surface);color:var(--ink);box-shadow:var(--shadow)}
.swatches{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.sw{width:100%;aspect-ratio:1;border-radius:50%;border:1px solid var(--line2);cursor:pointer;padding:0;
 transition:transform .12s}
.sw:hover{transform:scale(1.08)}
.sw.on{box-shadow:0 0 0 2px var(--surface),0 0 0 4px var(--ink)}
.swname{display:flex;justify-content:space-between;gap:8px;font-size:var(--fs-xs);color:var(--mut);margin-top:10px}
.swname b{color:var(--ink);font-weight:var(--fw-semibold)}

/* ---- the panel every screen sits in ---- */
.main{flex:1;min-height:0;overflow-y:auto;background:var(--surface);border-radius:28px;
 padding:32px 36px 64px;box-shadow:var(--shadow);
 /* The screens' card rows size themselves against this panel (see build.py). */
 container:panel/inline-size}
.dnote{display:flex;align-items:flex-start;gap:10px;padding:10px 14px;margin:0 0 22px;
 border-radius:var(--r-sm);background:var(--raised);color:var(--mut);font-size:var(--fs-xs);line-height:1.5}
.dnote b{color:var(--ink);font-weight:var(--fw-semibold)}
/* Said only while something on the screen is still illustrative (hydrate.js marks it). */
.main:not(:has([data-illustrative])) .dnote{display:none}
.dnote .dn-i{flex:none;color:var(--med);font-size:var(--fs-2xs);line-height:1.65}

@media(prefers-reduced-motion:reduce){.asof .dot,.ap-spin{animation:none}}

/* ---- export controls on every screen (ViewTools.jsx) ---- */
.vtools{display:flex;justify-content:flex-end;gap:8px;margin:-10px 0 12px}
.ap-act.failed{border-color:var(--crit-line);color:var(--crit)}
.ap-act:disabled{opacity:.7;cursor:default}
.dhead{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.print-head{display:none}

/* ---- paper: a screen printed or saved as PDF ---- */
@media print{
 @page{size:A4 landscape;margin:12mm}
 html,body{height:auto;overflow:visible;background:#fff}
 .shell{display:block;height:auto;padding:0;background:#fff}
 .side,.topnav,.vtools,.askpop,.drawer,.scrim-nav,.cc-preview-tag,.dnote{display:none!important}
 .col{display:block}
 .main{overflow:visible;box-shadow:none;border-radius:0;padding:0;background:#fff}
 .print-head{display:block;font-size:var(--fs-xs);color:var(--mut);border-bottom:1px solid var(--line2);
  padding-bottom:6px;margin-bottom:14px}
 .kpi,.bk,.panel,.alert,.note,.chartwrap,table.dt tr{break-inside:avoid}
 .kpi:hover,.bk:hover{transform:none;box-shadow:none}
 .tabpane:not(.on){display:none!important}
 a{color:inherit;text-decoration:none}
}

/* ---- narrower screens ---- */
@media(max-width:1180px){
 .shell{grid-template-columns:228px minmax(0,1fr)}
 .whotxt,.ask-k{display:none}
 .who{padding:0 4px}
}
/* A phone: the sidebar becomes a drawer behind a menu button, rather than vanishing
   and leaving no way to reach eighteen of the nineteen screens. */
@media(max-width:900px){
 .shell{grid-template-columns:minmax(0,1fr);padding:10px;gap:10px}
 .side{position:fixed;inset:0 auto 0 0;width:280px;z-index:90;background:var(--bg);padding:14px 6px 10px;
  transform:translateX(-102%);transition:transform .22s ease;box-shadow:var(--shadow2)}
 .shell.navopen .side{transform:none}
 .scrim-nav{position:fixed;inset:0;background:var(--scrim);z-index:80}
 .menu-b{display:grid;background:var(--surface);box-shadow:var(--shadow);flex:none}
 .topnav{gap:8px}
 .ask{height:50px;padding-left:16px}
 .ask-go{width:40px;padding:0;justify-content:center}
 .ask-go span{display:none}
 .seg2{display:none}
 .askpop,.askpop.wide{position:fixed;left:10px;right:10px;top:72px;width:auto;max-height:calc(100vh - 86px)}
 .ap-q{font-size:var(--fs-md)}
 .ib{width:40px;height:40px}
 .av{width:38px;height:38px}
 .main{padding:20px 16px 56px;border-radius:var(--r)}
}
"""
