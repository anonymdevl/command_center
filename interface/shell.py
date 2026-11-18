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
.brand-t{min-width:0}
/* The product's own logo (Settings -> Branding) in place of the mark, one for each
   background. The name is set by the administrator, so a long one is cut, not wrapped. */
.brand-logo{height:34px;max-width:72px;flex:none;display:flex;align-items:center}
.brand-logo img{max-height:34px;max-width:72px;width:auto;object-fit:contain;display:block}
.brand-logo img.dk{display:none}
[data-theme="dark"] .brand-logo img.lt{display:none}
[data-theme="dark"] .brand-logo img.dk{display:block}
.brand-t b{display:block;font-size:var(--fs-md);font-weight:var(--fw-semibold);letter-spacing:-.03em;
 white-space:nowrap;line-height:1.25;overflow:hidden;text-overflow:ellipsis}
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
/* A report finished while its writer is on another screen (Bell.jsx): a word, not a dialog. */
.cc-toast{position:fixed;right:24px;bottom:24px;z-index:85;display:flex;align-items:center;gap:12px;
 width:min(420px,calc(100vw - 32px));background:var(--surface);border:1px solid var(--line2);
 border-radius:var(--r-sm);box-shadow:var(--shadow2);padding:12px 12px 12px 16px}
.cc-toast .bell-dot{margin-top:0}
.cc-toast .bell-t{flex:1}
.cc-toast-x{flex:none;width:28px;height:28px;border:0;background:none;border-radius:50%;color:var(--dim);
 cursor:pointer;font-size:var(--fs-md);line-height:1}
.cc-toast-x:hover{background:var(--hover);color:var(--ink)}
@media (max-width:640px){.cc-toast{right:16px;left:16px;bottom:16px;width:auto}}
@media print{.cc-toast{display:none}}
.menu-b{display:none}
.who{display:flex;align-items:center;gap:10px;padding:0 14px 0 4px;min-width:0}
.av{width:44px;height:44px;border-radius:50%;background:var(--accent-bg2);color:var(--accent-ink);
 display:grid;place-items:center;font:var(--fw-bold) var(--fs-sm) var(--sans);flex:none}
.whotxt{min-width:0}
.whotxt b{display:block;font-size:var(--fs-sm);font-weight:var(--fw-semibold);white-space:nowrap;
 max-width:170px;overflow:hidden;text-overflow:ellipsis;line-height:1.3}
.whotxt span{display:block;font-size:var(--fs-xs);color:var(--mut);white-space:nowrap}
.whow{position:relative}
button.who{background:none;border:0;border-radius:var(--r-pill);cursor:pointer;color:inherit;font:inherit;text-align:left}
button.who:hover,button.who.on,button.who:focus-visible{background:var(--hover);outline:0}
.whomenu{position:absolute;right:0;top:calc(100% + 12px);width:260px;z-index:60;background:var(--surface);
 border:1px solid var(--line2);border-radius:20px;box-shadow:var(--shadow2);padding:8px}
.whomenu-h{display:flex;flex-direction:column;gap:2px;padding:10px 12px;border-bottom:1px solid var(--line);margin-bottom:6px}
.whomenu-h b{font-size:var(--fs-sm);font-weight:var(--fw-semibold)}
.whomenu-h span{font-size:var(--fs-xs);color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.whomenu-out{display:flex;align-items:center;gap:10px;width:100%;background:none;border:0;border-radius:var(--r-sm);
 padding:10px 12px;cursor:pointer;color:var(--ink);font:inherit;font-size:var(--fs-sm);font-weight:var(--fw-semibold)}
.whomenu-out:hover,.whomenu-out:focus-visible{background:var(--hover);outline:0}
.whomenu-out:disabled{opacity:.6;cursor:default}
.whomenu-out svg{width:18px;height:18px}

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
.print-head,.print-foot{display:none}

/* ---- paper: a screen printed or saved as PDF ---- */
@media print{
 @page{size:A4 landscape;margin:12mm}
 html,body{height:auto;overflow:visible;background:#fff}
 .shell{display:block;height:auto;padding:0;background:#fff}
 .side,.topnav,.vtools,.askpop,.drawer,.scrim-nav,.cc-preview-tag,.dnote{display:none!important}
 .col{display:block}
 .main{overflow:visible;box-shadow:none;border-radius:0;padding:0;background:#fff}
 .print-head{display:flex;align-items:center;gap:14px;font-size:var(--fs-xs);color:var(--mut);
  border-bottom:1px solid var(--line2);padding-bottom:8px;margin-bottom:14px}
 .print-head img{max-height:28px;max-width:160px;object-fit:contain}
 .print-head b{color:var(--ink);font-size:var(--fs-sm);font-weight:var(--fw-semibold)}
 .print-head .ph-meta{margin-left:auto;text-align:right;line-height:1.45}
 .print-foot{display:block;font-size:var(--fs-2xs);color:var(--mut);border-top:1px solid var(--line2);
  padding-top:6px;margin-top:18px}
 @page{@bottom-right{content:"Page " counter(page) " of " counter(pages)}}
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
 /* The bell's, the account's and the appearance panels sit under the top bar across the
    screen's width: anchored to their buttons they ran off the left edge (iPhone 11). */
 .bellpop,.whomenu,.appearmenu{position:fixed;left:10px;right:10px;top:72px;width:auto;
  max-height:calc(100vh - 86px);overflow:auto}
 .ap-q{font-size:var(--fs-md)}
 .ib{width:40px;height:40px}
 .av{width:38px;height:38px}
 .main{padding:20px 16px 56px;border-radius:var(--r)}
}

/* ======================================================================
   Answer charts and tables, second set (legacy/charts.js, legacy/markdown.js):
   column, ranked, combo and scatter charts; hover figures; the Download control;
   sortable, paged answer tables. New rules only -- nothing above is changed.
   ====================================================================== */
.md-chart{position:relative}
.md-cols,.md-scatter{width:100%;height:auto;display:block;overflow:visible}
.md-rect.c0,.md-dot.c0{fill:var(--accent)}
.md-rect.c1{fill:var(--ok)}
.md-rect.c2{fill:var(--high)}
.md-rect.c3{fill:var(--dim)}
.md-base{stroke:var(--ink2);stroke-width:1;opacity:.55}
.md-unit{font-weight:var(--fw-semibold)}
.md-val{fill:var(--ink2);font-size:var(--fs-3xs);font-weight:var(--fw-semibold);font-family:var(--sans)}
.md-plab{fill:var(--ink2);font-size:var(--fs-3xs);font-family:var(--sans)}
.md-dot{stroke:var(--surface);stroke-width:1.5}
.md-hit{fill:transparent;stroke:none}
.md-cols .md-hit:hover,.md-line .md-hit:hover{fill:var(--hover)}
.md-legend i.ln{height:3px;width:14px;border-radius:2px}
.md-hbars{display:flex;flex-direction:column;gap:10px}
.md-hbar{display:flex;flex-direction:column;gap:5px;font-size:var(--fs-sm)}
.md-hbar-h{display:flex;align-items:baseline;gap:8px;min-width:0}
.md-hbar-r{flex:none;min-width:18px;color:var(--dim);font-size:var(--fs-xs);font-variant-numeric:tabular-nums}
.md-hbar-l{flex:1;min-width:0;color:var(--ink2);overflow-wrap:anywhere}
.md-hbar-v{flex:none;font-variant-numeric:tabular-nums;font-weight:var(--fw-semibold);color:var(--ink);white-space:nowrap}
.md-hbar-t{position:relative;display:block;height:8px;margin-left:26px;background:var(--raised);
 border-radius:var(--r-pill);overflow:hidden}
.md-hbar-t i{position:absolute;top:0;bottom:0;background:var(--accent);border-radius:var(--r-pill)}
.md-hbar-t i.neg{background:var(--crit)}
.md-chart-note{font-size:var(--fs-xs);color:var(--mut);margin-top:8px}
.md-tip{position:absolute;z-index:5;pointer-events:none;max-width:280px;white-space:pre-line;
 background:var(--surface);color:var(--ink);border:1px solid var(--line2);border-radius:var(--r-sm);
 box-shadow:var(--shadow);padding:7px 10px;font-size:var(--fs-xs);line-height:1.45;font-variant-numeric:tabular-nums}
.md-tip[hidden]{display:none}
.md-chart-f,.md-pager{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:6px;margin-top:10px}
.md-dl-t,.md-pager-i{font-size:var(--fs-xs);color:var(--mut);margin-right:2px}
.md-dl{background:var(--surface);border:1px solid var(--line2);color:var(--ink);border-radius:var(--r-pill);
 padding:4px 11px;font-size:var(--fs-xs);font-weight:var(--fw-semibold);font-family:inherit;cursor:pointer;
 white-space:nowrap;transition:border-color .15s}
.md-dl:hover:not(:disabled){border-color:var(--ink2)}
.md-dl:disabled{opacity:.45;cursor:default}
.md-dl[hidden]{display:none}
.md-dl:focus-visible,.md-sort:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.md-pager{padding:8px 12px;margin:0;border-top:1px solid var(--line)}
table.dt th[aria-sort]{cursor:pointer;user-select:none}
.md-sort{all:unset;cursor:pointer;border-radius:3px}
table.dt th[aria-sort]::after{content:"";display:inline-block;width:0;height:0;margin-left:6px;vertical-align:middle;
 border-left:4px solid transparent;border-right:4px solid transparent;opacity:0}
table.dt th[aria-sort="none"]:hover::after{border-top:5px solid currentColor;opacity:.35}
table.dt th[aria-sort="descending"]::after{border-top:5px solid currentColor;opacity:.8}
table.dt th[aria-sort="ascending"]::after{border-bottom:5px solid currentColor;opacity:.8}
@media print{
 .md-chart-f,.md-pager,.md-tip{display:none!important}
 table.dt tbody tr[hidden]{display:table-row!important}
}
/* ======================================================================
   Charts, third set (legacy/viz.js on Apache ECharts): every chart on the
   platform -- answers and the designed screens' panels. The switcher, Download
   and Table toolbar; the chart's box; its table view; the tooltip ECharts writes
   (its frame is set in vizoptions.js from these same tokens).
   ====================================================================== */
.vz{position:relative;min-width:0}
.vz-bar{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px 10px;margin:0 0 8px}
.vz-seg{display:inline-flex;flex-wrap:wrap;gap:2px;padding:2px;border:1px solid var(--line2);
 border-radius:var(--r-pill);background:var(--raised)}
.vz-seg[hidden]{display:none}
.vz-opt{all:unset;cursor:pointer;padding:3px 10px;border-radius:var(--r-pill);font-size:var(--fs-xs);
 font-weight:var(--fw-medium);color:var(--mut);line-height:1.5;white-space:nowrap;transition:background .15s,color .15s}
.vz-opt:hover{color:var(--ink)}
.vz-opt.on{background:var(--surface);color:var(--ink);box-shadow:var(--shadow)}
.vz-opt:focus-visible,.vz-dl:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.vz-tools{display:inline-flex;align-items:center;gap:4px;margin-left:auto}
.vz-dl-t{font-size:var(--fs-2xs);color:var(--dim);margin-right:2px}
.vz-dl{background:var(--surface);border:1px solid var(--line2);color:var(--ink2);border-radius:var(--r-pill);
 padding:2px 9px;font:var(--fw-semibold) var(--fs-2xs) var(--sans);cursor:pointer;white-space:nowrap;
 transition:border-color .15s,color .15s}
.vz-dl:hover{border-color:var(--ink2);color:var(--ink)}
.vz-stage{width:100%;min-width:0}
.vz-stage[hidden],.vz-table[hidden]{display:none}
.vz-table{overflow:auto;max-height:420px}
.vz-tbl th.num,.vz-tbl td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.vz-tbl tr.clickable{cursor:pointer}
.vz-tbl tr.clickable:hover td{background:var(--hover)}
.vz-tbl tr.clickable:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.vz-tt-h{font-weight:var(--fw-semibold);color:var(--ink);margin-bottom:4px;max-width:260px;white-space:normal;
 overflow-wrap:anywhere}
.vz-tt-r{display:flex;align-items:center;gap:8px;min-width:150px;line-height:1.6}
.vz-tt-k{width:8px;height:8px;border-radius:2px;flex:none}
.vz-tt-n{color:var(--mut);flex:1;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.vz-tt-v{color:var(--ink);font-weight:var(--fw-semibold);font-variant-numeric:tabular-nums;white-space:nowrap}
.vz-tt-x{color:var(--mut);font-size:var(--fs-2xs);margin-top:2px;max-width:260px;white-space:normal}
.vz-compact .vz-bar{margin:2px 0 6px}
.vz-compact .vz-dl-t{display:none}
@media (hover:hover){
 .panel .vz-compact .vz-bar{opacity:.55;transition:opacity .15s}
 .panel:hover .vz-compact .vz-bar,.panel .vz-compact .vz-bar:focus-within{opacity:1}
}
@media (max-width:520px){
 .vz-dl-t{display:none}
 .vz-opt{padding:3px 8px}
 .vz-seg{flex-wrap:nowrap;overflow-x:auto;max-width:100%;scrollbar-width:none}
 .vz-seg::-webkit-scrollbar{display:none}
}
@media print{.vz-bar{display:none!important}}
/* ---- Ask: grouped live steps, Stop, one question at a time (15 Nov 2026) ---- */
.ap-stepwrap{margin-top:10px}
.ap-stepwrap .ap-steps{margin-top:0}
.ap-think .ap-steps .ap-stepn,.ap-deep .ap-steps .ap-stepn,.ap-steps .ap-stepn{display:inline-block;
 margin:0 0 0 6px;padding:0 7px;border-radius:var(--r-pill);background:var(--accent-bg);
 color:var(--accent-ink);font-size:var(--fs-xs);font-weight:var(--fw-semibold);line-height:1.6}
.ap-steps .ap-stepd{list-style:none;margin:4px 0 0;padding:0;display:flex;flex-direction:column;gap:2px}
.ap-steps .ap-stepd li{padding-left:0;font-size:var(--fs-xs);color:var(--mut)}
.ap-steps .ap-stepd li::before{content:none}
.ap-stepall{margin:8px 0 0 24px;padding:0;border:0;background:none;color:var(--accent-ink);font:inherit;
 font-size:var(--fs-xs);font-weight:var(--fw-semibold);cursor:pointer}
.ap-stepall:hover{text-decoration:underline}
.ap-busy{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 12px}
.ap-act:disabled{opacity:.6;cursor:default}
/* The starter questions are sentences with figures in them: they wrap inside the panel
   rather than running past its edge. */
#asksugg .btn{white-space:normal;flex:0 1 auto;max-width:100%;text-align:left;line-height:1.4}
/* ---- "Not recorded yet": the how-to-set-it-up guide (legacy/guide.js) ---- */
.guide{padding:14px 16px;border:1px dashed var(--line);border-radius:var(--r);background:var(--surface)}
.guide-compact{padding:10px 12px}
.guide-t{margin:0 0 8px;color:var(--ink2);font-size:var(--fs-sm);line-height:1.5}
.guide-s{margin:0 0 10px 18px;padding:0;color:var(--mut);font-size:var(--fs-sm);line-height:1.55}
.guide-s li{margin:2px 0}
.guide-a{display:inline-flex;text-decoration:none}
.guide-drawer{padding:20px}
.guide-drawer h3{margin:0 0 12px;font-size:var(--fs-lg)}
/* ---- The sign-in page's vendor footer (command-center-login.html) ---- */
/* Under the card, quiet: the product and "Built by", then the contact items. Each item
   is one unit (nowrap) and the items wrap only as whole units, centred. The dots sit in
   the gap and take no room, and an item that starts a line has none (the page's script
   marks it .ls), so no line begins or ends with a stray separator. */
/* Content-sized rows, centred while they fit and from the top when they do not (a phone):
   centring an overflowing page pushes its top out of reach. */
body.cc-auth{height:auto;grid-template-rows:auto auto;align-content:safe center;gap:18px}
.auth-by{width:min(960px,100%);text-align:center;font-size:var(--fs-2xs);color:var(--dim);line-height:1.6}
.auth-by-l{display:flex;flex-wrap:wrap;justify-content:center;column-gap:18px;row-gap:2px;margin:0}
.auth-by-l > span{position:relative;white-space:nowrap}
.auth-by-l > span::before{content:"·";position:absolute;left:-12px;width:6px;text-align:center}
.auth-by-l > span:first-child::before,.auth-by-l > span.ls::before{content:none}
@media (max-width:480px){
 .auth-by-c{flex-direction:column;align-items:center}
 .auth-by-c > span::before{content:none}
}
/* ---- The signature card's arrow only where the card opens something (build.py) ---- */
/* A tile with no action (Business Health's six questions, a figure not read) keeps the
   tinted card but has no cut corner, no arrow and no lift: only .clickable opens. */
:is(.kpi,.bk).sig:not(.clickable) > :is(.sig-cut,.sig-go){display:none}
:is(.kpi,.bk).sig:not(.clickable){cursor:default}
:is(.kpi,.bk).sig:not(.clickable):hover{box-shadow:none;transform:none}
:is(.kpi,.bk).sig:not(.clickable) :is(.v,.delta,.bar){max-width:none}
/* ======================================================================
   The record drawer (Drawer.jsx, Records.jsx, Understanding.jsx), 16 Nov 2026, from
   the approved mockup: wider, a solid header that stays put, a hero with the figure
   and one sentence, then Insight / Records / Trend. The drawer itself has no padding
   now; each band pads itself, so the header can run edge to edge and nothing shows
   through above it. Tokens only.
   ====================================================================== */
.drawer{width:min(880px,calc(100vw - 48px));max-width:none;padding:0;background:var(--panel)}
@media(max-width:900px){.drawer{width:100%;border-radius:0}}
.dw-body{padding:var(--sp-5) 22px}

/* ---- the header: Back, breadcrumb, title, actions, close ---- */
.dw-head{position:sticky;top:0;z-index:6;display:flex;align-items:center;gap:var(--sp-3);
 padding:14px 22px;background:var(--panel);border-bottom:1px solid var(--line);
 transition:box-shadow .15s}
.drawer.dw-scrolled .dw-head{box-shadow:var(--shadow)}
.drawer:focus{outline:none}
/* Markup that opens on Enter (legacy/keys.js) shows where the keyboard is. */
[data-keys]:focus{outline:none}
[data-keys]:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:var(--r-xs)}
.dw-titles{flex:1;min-width:0}
.dw-crumb{font-size:var(--fs-2xs);color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
 margin-bottom:2px}
.dw-title{margin:0;font-size:var(--fs-lg);font-weight:var(--fw-semibold);color:var(--ink);letter-spacing:-.01em;
 line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dw-acts{display:flex;align-items:center;gap:6px;flex:none}
.dw-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;height:32px;padding:0 12px;
 border:1px solid var(--line2);border-radius:var(--r-pill);background:var(--surface);color:var(--ink);
 font:var(--fw-semibold) var(--fs-xs)/1 var(--sans);white-space:nowrap;cursor:pointer;text-decoration:none;
 transition:border-color .15s,background .15s}
.dw-btn:hover:not(:disabled){border-color:var(--ink2);background:var(--raised)}
.dw-btn:disabled{opacity:.6;cursor:default}
.dw-btn:focus-visible,.dw-tab:focus-visible,.dw-search:focus-visible,.dw-bar-link:focus-visible{
 outline:2px solid var(--accent);outline-offset:2px}
.dw-btn.failed{border-color:var(--crit-line);color:var(--crit)}
.dw-x{width:32px;padding:0;font-size:var(--fs-lg);font-weight:var(--fw-regular)}
.dw-back{flex:none}

/* ---- the hero: the figure, its chips, and the one sentence ---- */
.dw-hero{display:flex;flex-wrap:wrap;align-items:flex-end;gap:var(--sp-4) var(--sp-8);padding:22px 22px 20px}
.dw-hero-fig{min-width:0;max-width:100%}
.dw-big{font-size:var(--fs-3xl);font-weight:var(--fw-semibold);letter-spacing:-.025em;line-height:1.15;color:var(--ink);
 font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dw-say{flex:1 1 300px;margin:0;max-width:62ch;font-size:var(--fs-md);line-height:1.6;color:var(--ink2)}
.dw-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.dw-chip,.dw-pill{display:inline-flex;align-items:center;font-size:var(--fs-2xs);font-weight:var(--fw-semibold);
 line-height:1.5;padding:2px 9px;border-radius:var(--r-pill);white-space:nowrap;color:var(--ink2);
 background:var(--raised);border:1px solid var(--line)}
.dw-c-crit{color:var(--crit);background:var(--crit-bg);border-color:var(--crit-line)}
.dw-c-high{color:var(--high);background:var(--high-bg);border-color:var(--high-line)}
.dw-c-ok{color:var(--ok);background:var(--ok-bg);border-color:var(--ok-line)}

/* ---- tabs ---- */
.dw-tabs{display:flex;gap:4px;padding:8px 18px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);
 overflow-x:auto;scrollbar-width:none}
.dw-tabs::-webkit-scrollbar{display:none}
.dw-tab{appearance:none;border:0;background:none;cursor:pointer;padding:6px 14px;border-radius:var(--r-pill);
 font:var(--fw-medium) var(--fs-sm)/1.4 var(--sans);color:var(--mut);white-space:nowrap;transition:background .15s,color .15s}
.dw-tab:hover{color:var(--ink)}
.dw-tab.on{background:var(--raised);color:var(--ink);font-weight:var(--fw-semibold);box-shadow:inset 0 0 0 1px var(--line)}

/* ---- the bands of a tab ---- */
.dw-sec{padding:18px 22px;border-bottom:1px solid var(--line)}
.dw-pane > .dw-sec:last-child,.dw-pane > :last-child .dw-sec:last-child{border-bottom:0}
.dw-lab{margin:0 0 10px;font-size:var(--fs-xs);font-weight:var(--fw-semibold);color:var(--mut);letter-spacing:0}
.dw-p{margin:0 0 8px;max-width:72ch;font-size:var(--fs-sm);line-height:1.6;color:var(--ink2)}
.dw-note{margin:8px 0 0;font-size:var(--fs-xs);line-height:1.5;color:var(--mut)}
.dw-pad{padding:14px 22px 18px;margin:0}
.dw-note.dw-note-top{margin:-4px 0 10px}
.dw-note.dw-ok{color:var(--ok)}
.dw-note.dw-bad{color:var(--crit)}
.dw-ai{background:var(--accent-bg)}
.dw-ai-err{background:var(--crit-bg)}

/* key numbers */
.dw-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.dw-tile{min-width:0;padding:12px 14px;border-radius:var(--r-sm);background:var(--raised)}
.dw-tile-l{display:block;font-size:var(--fs-2xs);color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dw-tile b{display:block;margin-top:4px;font-size:var(--fs-lg);font-weight:var(--fw-semibold);color:var(--ink);
 font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dw-tile-n{display:block;margin-top:2px;font-size:var(--fs-2xs);color:var(--dim);white-space:nowrap;overflow:hidden;
 text-overflow:ellipsis}
.dw-t-crit b{color:var(--crit)}
.dw-t-high b{color:var(--high)}
.dw-t-ok b{color:var(--ok)}

/* horizontal bars: the bridge, the concentration, what covers it */
/* One grid for every row (subgrid), so the tracks start and end together whatever the
   width of each figure. */
.dw-bars{display:grid;grid-template-columns:minmax(0,260px) minmax(60px,1fr) auto;column-gap:12px;row-gap:2px}
.dw-bar{grid-column:1/-1;display:grid;grid-template-columns:subgrid;align-items:center;
 padding:5px 0;font-size:var(--fs-sm);color:var(--ink2)}
.dw-bar-tot{color:var(--ink);font-weight:var(--fw-semibold)}
.dw-bar-l{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dw-bar-t{position:relative;display:block;height:10px;border-radius:3px;background:var(--raised);overflow:hidden}
.dw-bar-t i{position:absolute;left:0;top:0;bottom:0;border-radius:3px;background:var(--accent)}
.dw-bar-t i.dw-b-start{background:var(--accent)}
.dw-bar-t i.dw-b-end,.dw-bar-t i.dw-b-position{background:var(--ok)}
.dw-bar-t i.dw-b-process{background:var(--high)}
.dw-bar-t i.dw-b-timing{background:var(--accent-ink)}
.dw-bar-t i.dw-b-unexplained{background:var(--dim)}
.dw-bar-v{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.dw-bar-v small{margin-left:8px;font-size:var(--fs-2xs);color:var(--mut)}
.dw-bar-link{appearance:none;width:calc(100% + 16px);margin:0 -8px;padding:6px 8px;border:0;border-radius:var(--r-xs);
 background:none;font:inherit;text-align:left;cursor:pointer}
.dw-bar-link:hover:not(:disabled){background:var(--hover);color:var(--ink)}
a.dw-bar-link{color:inherit;text-decoration:none}
.dw-bar-link:disabled{cursor:default}
.dw-more{margin-top:10px}
.dw-more summary{cursor:pointer;font-size:var(--fs-xs);font-weight:var(--fw-semibold);color:var(--accent-ink)}
.dw-more[open] summary{margin-bottom:8px}

/* what to do, prevent it */
.dw-two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--sp-6)}
.dw-steps{margin:0;padding-left:18px;font-size:var(--fs-sm);line-height:1.55;color:var(--ink2)}
.dw-steps li{margin:0 0 6px;padding-left:2px}
.dw-plain{list-style:disc}
.dw-cta{margin-top:12px}
.dw-prev{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.dw-prev li{display:flex;gap:10px;align-items:flex-start;font-size:var(--fs-sm);line-height:1.5;color:var(--ink2)}
.dw-tick{flex:none;display:inline-grid;place-items:center;width:16px;height:16px;margin-top:2px;
 border-radius:var(--r-pill);border:1.5px solid var(--line2);font-size:var(--fs-3xs);font-weight:var(--fw-bold);line-height:1}
.dw-prev li.on .dw-tick{color:var(--ok);background:var(--ok-bg);border-color:var(--ok-line)}
.dw-prev li.off .dw-tick{border-color:var(--high-line)}

/* the explanation's own tables: one line per row as well */
.dw-sec .ins-t td,.dw-sec .ins-t th{white-space:nowrap}
.dw-sec .ins-block:first-child{margin-top:0}
.dw-clip{display:inline-block;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
 vertical-align:bottom}
.dw-date{white-space:nowrap}

/* ---- the records: search, a scroll box of their own, header and totals that stay ---- */
.dw-tbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:0 0 12px}
.dw-tbar .dw-note{margin:0}
.dw-search{height:34px;width:min(300px,100%);padding:0 14px;border:1px solid var(--line2);border-radius:var(--r-pill);
 background:var(--surface);color:var(--ink);font:var(--fw-regular) var(--fs-sm)/1 var(--sans)}
.dw-search::placeholder{color:var(--dim)}
.dw-tbox{max-width:100%;max-height:min(64vh,680px);overflow:auto;border:1px solid var(--line);
 border-radius:var(--r-sm);background:var(--surface);overscroll-behavior:contain}
table.dt.dw-t{width:100%;border-collapse:separate;border-spacing:0;font-size:var(--fs-sm)}
table.dt.dw-t th,table.dt.dw-t td{white-space:nowrap;font-variant-numeric:tabular-nums}
table.dt.dw-t thead th{position:sticky;top:0;z-index:2;padding:10px 12px;background:var(--raised);
 border-bottom:1px solid var(--line2);text-align:left}
table.dt.dw-t th.num,table.dt.dw-t td.num{text-align:right}
table.dt.dw-t td{padding:9px 12px;border-bottom:1px solid var(--line)}
table.dt.dw-t tbody tr:nth-child(even) td{background:var(--zebra)}
table.dt.dw-t tbody tr:hover td{background:var(--hover)}
table.dt.dw-t tfoot td{position:sticky;bottom:0;z-index:1;padding:10px 12px;background:var(--raised);
 border-top:1px solid var(--line2);border-bottom:0;font-weight:var(--fw-semibold);color:var(--ink)}
.dw-tbox .thin{padding:14px}

/* ---- narrower ---- */
@media(max-width:640px){
 .dw-head{flex-wrap:wrap;padding:12px 16px;gap:8px 10px}
 .dw-titles{flex:1 1 calc(100% - 110px)}
 .dw-acts{order:3;width:100%}
 .dw-acts .dw-x{margin-left:auto}
 /* Close alone keeps its place beside the title: a row of its own was empty but for it. */
 .dw-acts:has(> .dw-x:only-child){order:0;width:auto}
 .dw-hero{padding:18px 16px 16px}
 .dw-big{font-size:var(--fs-2xl)}
 .dw-tabs{padding:8px 12px}
 .dw-sec{padding:16px}
 .dw-pad{padding:12px 16px 16px}
 .dw-body{padding:16px}
 .dw-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
 .dw-two{grid-template-columns:minmax(0,1fr)}
 .dw-bars{grid-template-columns:minmax(0,1fr) minmax(40px,.6fr) auto;column-gap:8px}
 .dw-bar-v small{display:block;margin-left:0}
 .dw-clip{max-width:180px}
 .dw-search{width:100%}
}
/* ======================================================================
   The sign-in page: "It notices you" (L3, command-center-login.html), 16 Nov 2026,
   from the approved mockup-signin-L3.html. A warm grey ground (light) or a deep ink
   one (dark); about two dozen fine threads in the accent hue flow across the whole
   screen on a canvas behind everything, with ring nodes on every fifth thread. They
   lean gently towards the pointer (or the finger) and the nodes near it brighten and
   grow. One screen, never a scroll: the page is exactly the screen's height and the
   card, the brand and the footer fit inside it. Scoped to body.cc-signin, so the
   access pages (.auth.single) keep their own look. Tokens only: the page's few colours
   are mixed from the palette, in both themes; the threads read the accent from CSS.
   ====================================================================== */
body.cc-signin{
 --sg-ground:color-mix(in srgb,var(--t3) 38%,var(--bg));
 --sg-thread:var(--accent);
 --sg-card:var(--raised);
 --sg-card-line:var(--line2);
 --sg-field:var(--surface);
}
[data-theme="light"] body.cc-signin{
 --sg-ground:color-mix(in srgb,var(--t2) 45%,var(--line2));
 --sg-thread:var(--accent);
 --sg-card:var(--surface);
 --sg-card-line:color-mix(in srgb,var(--t2) 30%,var(--line2));
 --sg-field:var(--surface);
}
body.cc-auth.cc-signin{position:relative;display:grid;grid-template-columns:minmax(0,1fr);
 grid-template-rows:auto minmax(0,1fr) auto;place-items:stretch;align-content:stretch;gap:0;padding:0;
 height:100vh;height:100dvh;min-height:0;overflow:hidden;background:var(--sg-ground)}
/* Only a screen too short to hold the form at all (a phone on its side) may scroll:
   cutting the Sign In button off would be worse than a scroll. */
@media (max-height:519px){
 body.cc-auth.cc-signin{height:auto;min-height:100vh;min-height:100dvh;overflow-x:hidden;overflow-y:auto}
}
/* The threads: decoration only, never in the way of the form. */
.sg-threads{position:fixed;inset:0;width:100%;height:100%;z-index:0;pointer-events:none;
 color:var(--sg-thread)}
/* ---- top left: the logo, the product's name and tagline; the dateline right ---- */
.sg-top{position:relative;z-index:1;display:flex;align-items:center;justify-content:space-between;
 gap:var(--sp-4);padding:var(--sp-8) var(--sp-10) 0}
.sg-brand{display:flex;align-items:center;gap:14px;min-width:0}
.sg-brand .auth-mark{flex:none}
.sg-brand .auth-logo{height:40px;max-width:200px}
.sg-name{min-width:0}
.sg-name b{display:block;font-size:var(--fs-lg);font-weight:var(--fw-semibold);letter-spacing:-.015em;
 line-height:1.25;color:var(--ink)}
.sg-name .auth-tag{font-size:var(--fs-xs);line-height:1.4;margin-top:2px;color:var(--ink2)}
.sg-date{margin:0;font-size:var(--fs-xs);color:var(--ink2);white-space:nowrap;font-variant-numeric:tabular-nums}
/* ---- the stage: the card, with the threads running behind it ---- */
.sg-stage{position:relative;z-index:1;display:grid;place-items:center;padding:var(--sp-6) var(--sp-4);min-height:0}
.sg-card{position:relative;z-index:1;width:min(392px,100%);padding:36px 34px 26px;background:var(--sg-card);
 border:1px solid var(--sg-card-line);border-radius:var(--r-sm);box-shadow:var(--shadow2)}
/* A short accent rule at the card's head, the way a page marks its section. */
.sg-card::before{content:"";position:absolute;left:34px;top:-1px;width:28px;height:2px;background:var(--accent)}
.sg-card h1{margin:0;font-size:var(--fs-2xl);font-weight:var(--fw-semibold);letter-spacing:-.025em;line-height:1.2;
 color:var(--ink)}
.sg-card .auth-sub{margin-top:6px;font-size:var(--fs-sm)}
.sg-card form{display:flex;flex-direction:column;margin-top:var(--sp-6)}
.sg-card label{margin:0 0 6px;font-size:var(--fs-xs);font-weight:var(--fw-semibold);color:var(--ink2)}
.sg-card label:not(:first-child){margin-top:var(--sp-4)}
.sg-card input{width:100%;height:44px;padding:0 14px;border:1px solid var(--line2);border-radius:var(--r-xs);
 background:var(--sg-field);color:var(--ink);font:var(--fw-regular) var(--fs-md) var(--sans);
 transition:border-color .15s,box-shadow .15s}
.sg-card input:hover{border-color:color-mix(in srgb,var(--line2) 55%,var(--mut))}
.sg-card input:focus{outline:0;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-bg2)}
/* The browser's own autofill tint would paint the field another colour. */
.sg-card input:-webkit-autofill{-webkit-text-fill-color:var(--ink);caret-color:var(--ink);
 box-shadow:0 0 0 40px var(--sg-field) inset}
.sg-card input:-webkit-autofill:focus{box-shadow:0 0 0 40px var(--sg-field) inset,0 0 0 3px var(--accent-bg2)}
.sg-card .auth-pw input{padding-right:66px}
.sg-card .auth-pw button{top:5px;right:5px;height:34px;padding:0 10px;background:transparent;color:var(--mut);
 border-radius:var(--r-xs);transition:color .15s,background .15s}
.sg-card .auth-pw button:hover{color:var(--ink);background:var(--hover)}
.sg-card .auth-msg{margin-top:var(--sp-4);border:1px solid var(--crit-line);line-height:1.5}
.sg-card .auth-go{width:100%;height:46px;margin-top:22px;padding:0 var(--sp-6);border-radius:var(--r-xs);
 background:var(--ink);color:var(--surface);transition:background .15s,transform .1s}
.sg-card .auth-go:hover{filter:none;background:color-mix(in srgb,var(--ink) 84%,var(--accent))}
.sg-card .auth-go:active{transform:translateY(1px)}
.sg-card .auth-go:disabled{background:var(--ink);opacity:.6;transform:none}
.sg-card .auth-foot{gap:4px;margin-top:22px;padding-top:var(--sp-4);border-top:1px solid var(--line);line-height:1.5}
.sg-card .auth-foot a{justify-self:start;align-self:flex-start}
.sg-card .auth-foot a:hover{text-decoration:underline;text-underline-offset:3px}
body.cc-signin .auth-by{position:relative;z-index:1;justify-self:center;width:min(960px,100%);
 padding:var(--sp-4) var(--sp-4) 22px;color:var(--mut)}
/* A wide screen: the card stands to the right, as in the mockup, and the threads have
   the rest of the page to themselves. */
@media(min-width:1100px){
 .sg-stage{justify-items:end;padding-right:clamp(40px,9vw,160px)}
}
/* A short screen (a laptop at 720 or less): everything a little tighter, so the card
   and the footer still fit without a scroll. */
@media(max-height:760px){
 .sg-top{padding-top:var(--sp-6)}
 .sg-stage{padding-top:var(--sp-4);padding-bottom:var(--sp-4)}
 .sg-card{padding:28px 30px 20px}
 .sg-card form{margin-top:var(--sp-5)}
 .sg-card label:not(:first-child){margin-top:var(--sp-3)}
 .sg-card .auth-go{margin-top:18px}
 .sg-card .auth-foot{margin-top:18px;padding-top:var(--sp-3)}
 body.cc-signin .auth-by{padding-top:var(--sp-2);padding-bottom:16px}
}
/* The phone: the card fills the width less the gutter; the threads cross the band above
   it and run on behind it, showing in the gutters. */
@media(max-width:640px){
 .sg-top{padding:18px var(--sp-4) 0;align-items:flex-start}
 .sg-brand{gap:12px}
 .sg-brand .auth-mark{width:40px;height:40px;border-radius:12px}
 .sg-brand .auth-logo{height:32px;max-width:140px}
 .sg-name b{font-size:var(--fs-md)}
 .sg-name .auth-tag{font-size:var(--fs-2xs)}
 .sg-date{display:none}
 .sg-stage{padding:var(--sp-4) var(--sp-4) var(--sp-2)}
 .sg-card{padding:26px 22px 18px}
 .sg-card::before{left:22px}
 .sg-card form{margin-top:var(--sp-4)}
 .sg-card label:not(:first-child){margin-top:var(--sp-3)}
 .sg-card .auth-go{margin-top:18px}
 .sg-card .auth-foot{margin-top:16px;padding-top:var(--sp-3)}
 body.cc-signin .auth-by{padding:var(--sp-2) var(--sp-4) 14px}
}

/* ======================================================================
   Business Health as a check-up report (16 Nov 2026, approved mockup-health.html):
   the verdict, then six ruled findings, worst first, each with what it was counted
   from, its last eight weeks, the score now and a status (legacy/home.js
   renderHealthTiles). One sheet: the verdict block and the findings block are drawn
   as one. Tokens only; the statuses use the platform's pills (.flag f-*), so the
   Quiet signal level holds here too.
   ====================================================================== */
.hh-report,.hh-findings{background:var(--surface);border:1px solid var(--line);margin:0}
.hh-report{border-bottom:0;border-radius:var(--r) var(--r) 0 0;padding:26px 30px 0}
.hh-findings{border-top:0;border-radius:0 0 var(--r) var(--r);padding:6px 30px 20px;margin-bottom:8px}
.hh-verdict{display:grid;grid-template-columns:136px minmax(0,1fr);gap:var(--sp-8);align-items:center;
 padding-bottom:22px}
.hh-verdict>*{min-width:0}
.hh-gauge{display:flex;flex-direction:column;align-items:center;gap:6px;text-align:center}
.hh-ring{position:relative;width:120px;height:120px}
.hh-ring svg{display:block;width:100%;height:100%}
.hh-ring .hh-track{stroke:var(--line2)}
.hh-ring .hh-arc{stroke:var(--ink);transition:stroke-dasharray .5s ease-out}
.hh-ring-n{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
 font-size:var(--fs-3xl);font-weight:var(--fw-semibold);letter-spacing:-.03em;color:var(--ink);
 font-variant-numeric:tabular-nums;line-height:1}
.hh-ring-n small{font-size:var(--fs-md);font-weight:var(--fw-medium);color:var(--mut);margin-left:1px;
 position:relative;top:-.5em;letter-spacing:0}
.hh-cap{font-size:var(--fs-3xs);font-weight:var(--fw-bold);letter-spacing:.14em;text-transform:uppercase;color:var(--mut)}
.hh-delta{font-size:var(--fs-2xs);font-weight:var(--fw-semibold);font-variant-numeric:tabular-nums;
 padding:2px 9px;border-radius:var(--r-pill);background:var(--raised);color:var(--ink2);white-space:nowrap}
.hh-delta.up{color:var(--ok)}
.hh-delta.dn{color:var(--crit)}
.hh-delta[hidden]{display:none}
.hh-say{margin:0;font-size:var(--fs-xl);line-height:1.42;font-weight:var(--fw-medium);letter-spacing:-.018em;
 color:var(--ink);text-wrap:pretty}
.hh-say b{font-weight:var(--fw-bold)}
.hh-say .hh-since{color:var(--mut);font-weight:var(--fw-regular)}
.hh-note{margin:12px 0 0;font-size:var(--fs-sm);line-height:1.55;color:var(--mut);max-width:68ch}
.hh-tally{display:flex;flex-wrap:wrap;gap:6px 0;margin-top:14px;font-size:var(--fs-xs);color:var(--mut)}
.hh-tally:empty{display:none}
.hh-tally span{padding:0 14px;border-left:1px solid var(--line2);white-space:nowrap}
.hh-tally span:first-child{padding-left:0;border-left:0}
.hh-tally b{font-size:var(--fs-md);font-weight:var(--fw-semibold);color:var(--ink);font-variant-numeric:tabular-nums}
.hh-trend{margin:8px 0 0;font-size:var(--fs-2xs);line-height:1.5;color:var(--dim)}
.hh-assure{display:flex;align-items:center;gap:10px;margin:0;padding:12px 0;border-top:1px solid var(--line);
 font-size:var(--fs-xs);line-height:1.5;color:var(--ink2);font-weight:var(--fw-medium)}
/* A small seal: a ring with a tick, drawn with borders so it follows the theme. */
.hh-seal{flex:none;position:relative;width:16px;height:16px;border-radius:50%;border:1.5px solid var(--ok)}
.hh-seal::after{content:"";position:absolute;left:4.5px;top:2px;width:4px;height:7px;
 border:solid var(--ok);border-width:0 1.5px 1.5px 0;transform:rotate(45deg)}

/* ---- the findings ---- */
.hh-row{display:grid;grid-template-columns:14px minmax(0,1fr) auto 64px 92px;gap:var(--sp-4);align-items:center;
 padding:15px 0;border-top:1px solid var(--line)}
.hh-row>*{min-width:0}
.hh-cols{padding:10px 0 9px;border-top:1.5px solid var(--ink);font-size:var(--fs-3xs);font-weight:var(--fw-bold);
 letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
.hh-cols span:nth-child(4){text-align:right}
.hh-cols span:nth-child(3){width:148px}
.hh-list .hh-row:first-child{border-top-color:var(--line2)}
.hh-sq{width:12px;height:12px;border-radius:calc(var(--r-xs) / 2);background:var(--line2)}
.hh-sq.b-none{background:transparent;box-shadow:inset 0 0 0 1.5px var(--line2)}
.hh-q .l{font-size:var(--fs-md);font-weight:var(--fw-semibold);color:var(--ink);line-height:1.35}
.hh-n{margin-top:3px;font-size:var(--fs-sm);line-height:1.45;color:var(--ink2)}
.hh-src{margin-top:3px;font-size:var(--fs-2xs);line-height:1.45;color:var(--dim)}
.hh-src:empty{display:none}
.hh-row[data-state="wait"] .hh-q .l,.hh-row[data-state="access"] .hh-q .l{color:var(--ink2)}
.hh-strip{display:flex;gap:4px;width:148px}
.hh-wk{width:14px;height:14px;flex:none;border-radius:calc(var(--r-xs) / 2);background:transparent;
 box-shadow:inset 0 0 0 1px var(--line2);background-image:none}
.hh-wk:not([class*=" b-"]){box-shadow:none;border:1px dashed var(--line2)}
.hh-now{text-align:right;font-size:var(--fs-xl);font-weight:var(--fw-semibold);letter-spacing:-.02em;
 color:var(--ink);font-variant-numeric:tabular-nums;line-height:1}
.hh-now small{font-size:var(--fs-xs);font-weight:var(--fw-medium);color:var(--mut);margin-left:1px}
.hh-row[data-state="wait"] .hh-now,.hh-row[data-state="access"] .hh-now{color:var(--dim);font-size:var(--fs-md)}
.hh-status{justify-self:end;white-space:nowrap}
/* bands: the square now is solid; earlier weeks are the same hue, lighter */
.hh-sq.b-crit,.hh-wk.b-crit.now{background:var(--crit-solid);box-shadow:none}
.hh-sq.b-med,.hh-wk.b-med.now{background:var(--med-solid);box-shadow:none}
.hh-sq.b-ok,.hh-wk.b-ok.now{background:var(--ok-solid);box-shadow:none}
.hh-wk.b-crit{background:var(--crit-solid);box-shadow:none;opacity:.42}
.hh-wk.b-med{background:var(--med-solid);box-shadow:none;opacity:.42}
.hh-wk.b-ok{background:var(--ok-solid);box-shadow:none;opacity:.42}
.hh-wk.now{opacity:1}
/* only a row with a guide to open is drawn as something to press */
.hh-row.clickable{cursor:pointer;border-radius:var(--r-xs);margin:0 -12px;padding-left:12px;padding-right:12px;
 transition:background .15s}
.hh-row.clickable:hover{background:var(--hover)}
.hh-row.clickable:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.hh-row.clickable .hh-src::after{content:" ›";color:var(--accent-ink);font-weight:var(--fw-semibold)}
.hh-legend{margin:0;padding:12px 0 0;border-top:1px solid var(--line);font-size:var(--fs-2xs);line-height:1.5;color:var(--dim)}
/* Overview's sheet and Detail's panels keep their own spacing below the tab bar. */
.tabpane .hh-report{margin-top:2px}

/* ---- narrower: the panel, not the window (container panel, above) ---- */
@container panel (max-width:760px){
 .hh-report{padding:22px 20px 0}
 .hh-findings{padding:4px 20px 16px}
 .hh-row{grid-template-columns:12px minmax(0,1fr) auto;grid-template-areas:"sq q pill" ". strip now";
  row-gap:10px;column-gap:12px}
 .hh-row>.hh-sq{grid-area:sq;align-self:start;margin-top:4px}
 .hh-row>.hh-q{grid-area:q}
 .hh-row>.hh-strip{grid-area:strip;width:auto}
 .hh-row>.hh-now{grid-area:now}
 .hh-row>.hh-status{grid-area:pill;align-self:start}
 .hh-cols{grid-template-columns:minmax(0,1fr);grid-template-areas:none}
 .hh-cols span:not(:nth-child(2)){display:none}
 .hh-row.clickable{margin:0 -10px;padding-left:10px;padding-right:10px}
}
@container panel (max-width:520px){
 .hh-verdict{grid-template-columns:minmax(0,1fr);gap:var(--sp-4);justify-items:center;text-align:center}
 .hh-word{text-align:left}
 .hh-say{font-size:var(--fs-lg)}
 .hh-ring{width:108px;height:108px}
 .hh-report{padding:18px 16px 0}
 .hh-findings{padding:2px 16px 14px}
 .hh-tally span{padding:0 10px}
 .hh-wk{width:13px;height:13px}
 .hh-strip{gap:3px}
}

/* ======================================================================
   TABLES, EVERY SCREEN (16 Nov 2026): headers never wrap ("On Open Invoices / GHS" was
   two lines on Sales and Payments), nor do figures and dates; a table wider than its
   panel scrolls sideways in its own box (legacy/tables.js puts each in a .dt-x), never
   the page. Text cells keep wrapping at a readable measure (TABLE TEXT, below) -- unless
   the cell carries its full text in a title, when it may end in an ellipsis.
   ====================================================================== */
table.dt th,[data-theme="light"] table.dt th{white-space:nowrap}
table.dt td.num,table.dt td.n,table.dt td.dt-nw{white-space:nowrap}
table.dt td[title]:not(:has(*)){max-width:28ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dt-x{overflow-x:auto;max-width:100%;overscroll-behavior-x:contain}
.dt-x > table.dt{width:100%}
.dt-x + .thin{margin-top:14px}
.dt-x + .warn{margin-top:16px}
@container panel (max-width:560px){
 /* In its box the table keeps its own layout; the phone rule that made a bare table
    scroll itself is for tables outside one (Settings). */
 :is(.dt-x,.dt-scroll,.fs-wrap) > table.dt{display:table}
}

/* ======================================================================
   FINANCES -- "Management Accounts" (option A, approved 16 Nov 2026)
   Appearance only: every figure, statement, tab, chart and panel is the one the screen
   had. The figures sit in a ruled ribbon instead of tinted cards, the statements are set
   like printed management accounts, and the panels lose their weight. Scoped to the
   screen by its statements block (.view:has(> #fs)) and the rows' .ribbon class.
   ====================================================================== */

/* ---- the figure ribbon: one ruled band, hairlines between the figures ---- */
.kpis.ribbon{gap:0;grid-template-columns:repeat(6,minmax(0,1fr));border-top:1px solid var(--ink2);
 border-bottom:1px solid var(--line2);overflow:hidden;margin:0 0 var(--sp-6);background:none}
.kpis.fs-cards.ribbon{grid-template-columns:repeat(5,minmax(0,1fr));margin:0 0 var(--sp-5)}
.kpis.fs-cards.ribbon:empty{display:none}
.kpis.ribbon > .kpi,.kpis.ribbon > .kpi.sig,
.kpis.ribbon > .kpi.sig:nth-child(n){background:none;border:0;border-radius:0;box-shadow:none;transform:none;
 border-left:1px solid var(--line);border-top:1px solid var(--line);margin:-1px 0 0 -1px;min-height:0;
 padding:var(--sp-4) 30px var(--sp-4) var(--sp-4);text-align:left;align-items:stretch;justify-content:flex-start;
 transition:background .15s}
.kpis.ribbon > .kpi.sig.clickable:hover,[data-theme="light"] .kpis.ribbon > .kpi.sig:hover,
.kpis.ribbon > .kpi.sig:hover{background:var(--hover);border:0;border-left:1px solid var(--line);
 border-top:1px solid var(--line);box-shadow:none;transform:none}
.kpis.ribbon > .kpi:focus-visible{outline:2px solid var(--accent);outline-offset:-3px}
.kpis.ribbon .sig-cut{display:none}
.kpis.ribbon .sig-go{top:var(--sp-4);right:var(--sp-3);bottom:auto;width:18px;height:18px;background:none;
 color:var(--dim);transition:color .15s,transform .2s}
.kpis.ribbon .sig-go svg{width:14px;height:14px}
.kpis.ribbon > .kpi.sig:hover .sig-go{color:var(--ink);transform:rotate(45deg)}
/* The label is read whole: it wraps, and the "as at" pill drops under it when there is no room. */
.kpis.ribbon .khead{justify-content:flex-start;flex-wrap:wrap;gap:4px 6px;min-height:18px;width:100%}
.kpis.ribbon .kpi .lab,.kpis.ribbon .kpi.sig .lab{font-size:var(--fs-xs);font-weight:var(--fw-medium);color:var(--mut);
 letter-spacing:0;text-transform:none;white-space:normal;overflow:visible;line-height:1.35}
.kpis.ribbon .flag{font-size:var(--fs-3xs);padding:2px 7px}
.kpis.ribbon > .kpi.sig .val{font-size:var(--fs-2xl);font-weight:var(--fw-semibold);letter-spacing:-.025em;
 line-height:1.15;margin:var(--sp-2) 0 0;padding:0;flex:none;justify-content:flex-start;color:var(--ink);
 font-variant-numeric:tabular-nums}
.kpis.ribbon .val .cx{font-size:var(--fs-xs);font-weight:var(--fw-medium);color:var(--mut);vertical-align:.3em;
 margin-right:5px;letter-spacing:0}
.kpis.ribbon .val .mag,.kpis.ribbon .val .cur{font-size:.62em;color:var(--mut);font-weight:var(--fw-semibold)}
.kpis.ribbon > .kpi.sig .delta{font-size:var(--fs-xs);color:var(--mut);margin:var(--sp-1) 0 0;padding:0;border:0;
 max-width:none;white-space:normal;overflow:visible;line-height:1.4;min-height:0;text-align:left}
.kpis.ribbon > .kpi.sig .delta.up{color:var(--ok)}
.kpis.ribbon > .kpi.sig .delta.down{color:var(--crit)}
/* A figure that is wrong or needs attention says so in its colour: a statement figure
   the statements mark down (a loss, a current ratio under 1), a figure that failed to
   load. One needing setup is quiet: there is no figure to colour. */
.kpis.ribbon > .kpi.sig:has(> .delta.down) .val,
.kpis.ribbon > .kpi.sig:has(.flag.f-crit) .val{color:var(--crit)}
.kpis.ribbon > .kpi.sig[data-setup] .val{color:var(--dim)}
.kpis.ribbon > .kpi[data-loading] .val{opacity:.5}
/* Six across (five for the statements) while each figure has room, then two rows of three
   on a narrower laptop. The rows answer to the panel (container: panel), like every card row. */
@container panel (max-width:1199px){
 .kpis.ribbon{grid-template-columns:repeat(6,minmax(0,1fr))!important}
 .kpis.fs-cards.ribbon{grid-template-columns:repeat(5,minmax(0,1fr))!important}
 .kpis.ribbon > .kpi.sig .val{font-size:var(--fs-xl)}}
@container panel (max-width:979px){
 .kpis.ribbon,.kpis.fs-cards.ribbon{grid-template-columns:repeat(3,minmax(0,1fr))!important}
 .kpis.ribbon > .kpi.sig .val{font-size:var(--fs-2xl)}}
@container panel (max-width:560px){
 /* A phone: one figure to a line, the label on the left and the figure on the right. */
 .kpis.ribbon,.kpis.fs-cards.ribbon{grid-template-columns:minmax(0,1fr)!important}
 .kpis.ribbon > .kpi,.kpis.ribbon > .kpi.sig,.kpis.ribbon > .kpi.sig:nth-child(n){display:grid;
  grid-template-columns:minmax(0,1fr) auto;column-gap:var(--sp-3);align-items:baseline;border-left:0;margin-left:0;
  padding:var(--sp-3) 26px var(--sp-3) 0}
 .kpis.ribbon > .kpi.sig:hover{border-left:0}
 .kpis.ribbon > .kpi.sig > .khead{grid-column:1;grid-row:1;min-width:0}
 .kpis.ribbon > .kpi.sig > .val{grid-column:2;grid-row:1 / span 2;margin:0;font-size:var(--fs-xl);align-self:center}
 .kpis.ribbon > .kpi.sig > .delta{grid-column:1;grid-row:2}
 .kpis.ribbon .sig-go{top:50%;right:0;margin-top:-9px}
 .kpis.ribbon > .kpi.sig:hover .sig-go{transform:none}
}

/* ---- the statements, set like printed management accounts ---- */
.fs{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-sm);padding:var(--sp-6) 28px 28px;
 box-shadow:none}
.fs-head{margin-bottom:var(--sp-5);align-items:flex-end}
.fs-title b{font-size:var(--fs-xl);font-weight:var(--fw-semibold);letter-spacing:-.02em}
.fs-title span{margin-top:4px;font-size:var(--fs-xs);color:var(--mut);line-height:1.5}
.fs-periods{background:none;border:0;border-radius:0;padding:0;gap:2px var(--sp-1)}
.fs-p{border-radius:0;padding:6px 6px 5px;color:var(--mut);font-weight:var(--fw-medium);
 border-bottom:2px solid transparent}
.fs-p:hover{color:var(--ink)}
.fs-p.on{background:none;box-shadow:none;color:var(--ink);font-weight:var(--fw-semibold);border-bottom-color:var(--ink)}
.fs-p:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.fs-exports{padding-left:var(--sp-3);margin-left:var(--sp-1);border-left:1px solid var(--line2)}
.fs-exports .btn{padding:5px 12px;font-size:var(--fs-xs)}
/* The statement tabs and the screen's own Overview / Detail tabs: a ruled line with the
   chosen one underlined, as a printed report's contents would be marked. */
.fs .tabbar,.view:has(> #fs) > .tabbar{display:flex;gap:var(--sp-6);border:0;border-bottom:1px solid var(--line2);
 border-radius:0;padding:0;margin:var(--sp-2) 0 var(--sp-6);overflow-x:auto;scrollbar-width:none;max-width:100%}
.fs .tabbar::-webkit-scrollbar,.view:has(> #fs) > .tabbar::-webkit-scrollbar{display:none}
.fs .tab,.view:has(> #fs) > .tabbar .tab{border:0;border-radius:0;background:none;box-shadow:none;padding:10px 0 11px;
 margin:0 0 -1px;border-bottom:2px solid transparent;color:var(--mut);font-weight:var(--fw-medium)}
.fs .tab:hover,.view:has(> #fs) > .tabbar .tab:hover{color:var(--ink)}
.fs .tab.on,.view:has(> #fs) > .tabbar .tab.on{background:none;box-shadow:none;color:var(--ink);
 font-weight:var(--fw-semibold);border:0;border-bottom:2px solid var(--ink)}
.view:has(> #fs) > .tabbar{margin-top:var(--sp-2)}
.fs-body h4{font-size:var(--fs-md);font-weight:var(--fw-semibold);letter-spacing:-.01em;margin:var(--sp-8) 0 var(--sp-1)}
.fs-body h4:first-child{margin-top:0}
.fs-sub{margin:0 0 var(--sp-3);color:var(--mut)}
.fs-wrap.tall{border-radius:var(--r-xs)}
table.dt.fs-t{border-collapse:collapse;font-size:var(--fs-sm)}
table.dt.fs-t th,[data-theme="light"] table.dt.fs-t th{white-space:nowrap;font-size:var(--fs-2xs);
 font-weight:var(--fw-semibold);color:var(--mut);letter-spacing:.01em;padding:0 12px var(--sp-2);
 border-bottom:1px solid var(--ink2);background:none;vertical-align:bottom}
.fs-wrap.tall table.dt.fs-t th{padding-top:var(--sp-2);background:var(--surface)}
table.dt.fs-t td{padding:7px 12px;border-bottom:1px solid var(--line);background:none}
table.dt.fs-t tbody tr:last-child td{border-bottom:1px solid var(--line)}
table.dt.fs-t tr:hover td{background:var(--hover)}
table.dt.fs-t td.n{color:var(--ink);font-variant-numeric:tabular-nums}
table.dt.fs-t :is(td,th).cmp{color:var(--mut)}
table.dt.fs-t tr.fs-group td,table.dt.fs-t tr.fs-heading td{font-weight:var(--fw-semibold)}
table.dt.fs-t tr.fs-heading td{color:var(--mut);font-size:var(--fs-xs)}
/* A heavier rule above every total, and a double rule under the last line of a statement. */
table.dt.fs-t tr.fs-total td{border-top:1px solid var(--ink2);font-weight:var(--fw-semibold);color:var(--ink)}
table.dt.fs-t tr.fs-total td.cmp{color:var(--ink2)}
table.dt.fs-t tbody tr.fs-total:last-child td{border-bottom:3px double var(--ink2)}
table.dt.fs-t td.neg{color:var(--crit)}
table.dt.fs-t td.pos{color:var(--ok)}
table.dt.fs-t a.fs-acc{border-bottom-color:var(--line2)}
/* The slim bar beside each line of the profit and loss: that line's share of the largest. */
table.dt.fs-t :is(.fs-bar-h,.fs-bar-c){width:20%;min-width:96px;padding-left:var(--sp-5)}
.fs-bar{display:block;height:6px;border-radius:2px;background:var(--ink2);opacity:.7}
.fs-bar.cost{opacity:.3}
.fs-bar.neg{background:var(--crit);opacity:.85}
.fs-says{margin:var(--sp-4) 0 0;max-width:76ch;font-size:var(--fs-md);line-height:1.6;color:var(--ink2)}
.fs-check,.fs-check.ok,.fs-check.bad{background:none;padding:0;border-radius:0;margin-top:var(--sp-3)}
.fs-check::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}
.fs-notes{max-width:96ch}
.fs-mean{margin-top:2px}
@container panel (max-width:760px){
 table.dt.fs-t :is(.fs-bar-h,.fs-bar-c){display:none}}
@container panel (max-width:560px){
 .fs{padding:var(--sp-4) var(--sp-4) var(--sp-5)}
 /* The six periods wrap to a second line rather than run off under the edge. */
 .fs-periods{flex-wrap:wrap;overflow:visible}
 .fs-exports{border-left:0;padding-left:0;margin-left:0}
 .fs .tabbar,.view:has(> #fs) > .tabbar{gap:var(--sp-5)}
 table.dt.fs-t td,table.dt.fs-t th{padding-left:8px;padding-right:8px}
 /* An account's name keeps a readable width; the figures scroll beside it instead. */
 table.dt.fs-t td:first-child{min-width:10em}
 table.dt.fs-t th{padding-bottom:var(--sp-2)}}

/* ---- the panels and charts: quieter frames, no tinted boxes ---- */
.view:has(> #fs) .panel{border-radius:var(--r-sm);box-shadow:none;padding:var(--sp-5) var(--sp-6)}
.view:has(> #fs) .panel .ph{padding-bottom:var(--sp-3);margin-bottom:var(--sp-4);border-bottom:1px solid var(--line)}
.view:has(> #fs) .panel .ph b{font-size:var(--fs-md);letter-spacing:-.01em}
.view:has(> #fs) .pmore{color:var(--mut);font-weight:var(--fw-medium)}
.view:has(> #fs) .ph.clickable:hover .pmore{color:var(--accent-ink)}
.view:has(> #fs) .chartwrap,[data-theme="light"] .view:has(> #fs) .chartwrap{background:none;border:0;box-shadow:none;
 padding:0}
.view:has(> #fs) .thin{background:none;border:0;border-left:2px solid var(--line2);border-radius:0;
 padding:2px 0 2px var(--sp-3);color:var(--mut);font-size:var(--fs-sm);line-height:1.6}
.view:has(> #fs) .thin b{color:var(--ink2);font-weight:var(--fw-semibold)}
.view:has(> #fs) .bartrack{border-radius:2px;height:12px}
.view:has(> #fs) .barfill{border-radius:2px}
.view:has(> #fs) .vz-seg{border-color:var(--line)}
.view:has(> #fs) .vz-dl{background:none}
.view:has(> #fs) .warn{border-radius:var(--r-sm)}
@container panel (max-width:560px){
 .view:has(> #fs) .panel{padding:var(--sp-4)}}
/* ======================================================================
   Business Overview as a front page (16 Nov 2026, the approved mockup: B over A).
   The lead story on the left, three areas beside it, the rest a ruled register.
   The nine tiles are the designed .bk tiles, moved into place by
   legacy/overview.js and restyled here by role (ov-as-lead / ov-as-sec /
   ov-as-row): no card, no tint, no grid of boxes -- type, figures and hairlines.
   The arrow stays only where a tile opens something (the rule above); the cut
   corner belongs to the tinted card, which this screen no longer draws.
   ====================================================================== */
.ov{border-top:1px solid var(--ink);margin-top:var(--sp-2)}
.ov-front{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(0,1fr);padding:var(--sp-6) 0 var(--sp-8)}
.ov-lead{min-width:0;padding-right:var(--sp-8);border-right:1px solid var(--line)}
.ov-sec{min-width:0;padding-left:var(--sp-8);display:flex;flex-direction:column}

/* every tile on this screen sheds the card */
.ov .bk.sig{background:none;border:0;border-radius:0;box-shadow:none;min-height:0;padding:0;margin:0;
 text-align:left;align-items:stretch;justify-content:flex-start;container-type:normal;transform:none;
 transition:color .15s}
.ov .bk.sig:hover{background:none;border:0;box-shadow:none;transform:none}
.ov .bk.sig > .sig-cut{display:none}
.ov .bk.sig .n{flex:none;display:block;width:auto;margin:0;padding:0;text-align:left;color:var(--ink);
 font-weight:var(--fw-semibold);line-height:1.05}
.ov .bk.sig .v{border:0;padding:0;max-width:none;width:auto;min-height:0;white-space:normal;color:var(--mut);
 font-size:var(--fs-xs);line-height:1.45}
.ov .bk.sig .l{white-space:normal;overflow:visible;max-width:none;order:0}
.ov .bk.sig .flag{margin:0;align-self:auto}
.ov .bk.clickable:focus-visible{outline:2px solid var(--accent);outline-offset:6px;border-radius:var(--r-xs)}
.ov .bk.clickable:hover > .sig-go,.ov .bk.clickable:focus-visible > .sig-go{transform:rotate(45deg)}

/* ---- the lead story ---- */
.ov .bk.ov-as-lead{display:grid;grid-template-columns:max-content minmax(0,1fr);column-gap:var(--sp-10);
 grid-template-areas:"head head" "say say" "dek dek" "n figs" "v figs" "prov prov";align-content:start;
 position:relative}
.ov .ov-as-lead > .khead{grid-area:head;display:flex;align-items:center;flex-wrap:wrap;gap:6px 10px;
 padding-right:60px;min-height:44px}
.ov-kick{font-size:var(--fs-3xs);font-weight:var(--fw-bold);letter-spacing:.16em;text-transform:uppercase;
 color:var(--accent-ink);white-space:nowrap}
.ov-kick::after{content:"·";margin-left:10px;color:var(--dim)}
.ov .bk.ov-as-lead .l{font-size:var(--fs-3xs);font-weight:var(--fw-bold);letter-spacing:.16em;
 text-transform:uppercase;color:var(--ink2)}
.ov-say{grid-area:say;margin:var(--sp-3) 0 0;max-width:30ch;font-size:var(--fs-3xl);font-weight:var(--fw-medium);
 line-height:1.22;letter-spacing:-.022em;color:var(--ink);text-wrap:balance;text-decoration:underline;
 text-decoration-color:transparent;text-decoration-thickness:1px;text-underline-offset:.16em;
 transition:text-decoration-color .15s}
.ov .ov-as-lead.clickable:hover .ov-say,.ov .ov-as-lead.clickable:focus-visible .ov-say{
 text-decoration-color:var(--line2)}
.ov-dek{grid-area:dek;margin:var(--sp-3) 0 0;max-width:58ch;font-size:var(--fs-md);line-height:1.55;
 color:var(--ink2)}
.ov .bk.ov-as-lead .n{grid-area:n;margin-top:var(--sp-8);font-size:var(--fs-5xl);letter-spacing:-.035em}
.ov .bk.ov-as-lead .n .cx{font-size:var(--fs-md)}
.ov .bk.ov-as-lead .n .mag{font-size:var(--fs-2xl)}
.ov .bk.ov-as-lead .n small{font-size:var(--fs-md)}
.ov .bk.ov-as-lead .v{grid-area:v;margin-top:var(--sp-2)}
.ov-figs{grid-area:figs;align-self:end;display:flex;flex-wrap:wrap;gap:var(--sp-4) var(--sp-8);
 padding-left:var(--sp-8);border-left:1px solid var(--line)}
.ov-fig b{display:block;font-size:var(--fs-xl);font-weight:var(--fw-semibold);letter-spacing:-.02em;
 line-height:1.1;color:var(--ink);font-variant-numeric:tabular-nums;white-space:nowrap}
.ov-fig span{display:block;margin-top:6px;font-size:var(--fs-xs);color:var(--mut)}
.ov .ov-as-lead > .flag[data-prov]{grid-area:prov;justify-self:start;margin-top:var(--sp-4)}
.ov .ov-as-lead.clickable > .sig-go{top:0;right:0;bottom:auto;width:44px;height:44px}

/* ---- the column beside it ---- */
.ov .bk.ov-as-sec{display:grid;grid-template-columns:minmax(0,1fr) auto;
 grid-template-areas:"head go" "n go" "v v" "note note" "prov prov";align-items:start;position:relative;
 padding:var(--sp-4) 0;border-top:1px solid var(--line)}
.ov .bk.ov-as-sec:first-child{padding-top:0;border-top:0}
.ov .bk.ov-as-sec:last-child{padding-bottom:0}
.ov .ov-as-sec > .khead{grid-area:head;display:flex;align-items:center;flex-wrap:wrap;gap:6px 8px}
.ov .bk.ov-as-sec .l{font-size:var(--fs-3xs);font-weight:var(--fw-bold);letter-spacing:.14em;
 text-transform:uppercase;color:var(--ink2)}
.ov .bk.ov-as-sec .n{grid-area:n;margin-top:var(--sp-2);font-size:var(--fs-2xl);letter-spacing:-.025em}
.ov .bk.ov-as-sec .n .cx{font-size:var(--fs-xs)}
.ov .bk.ov-as-sec .n .mag{font-size:var(--fs-lg)}
.ov .bk.ov-as-sec .n small{font-size:var(--fs-xs)}
.ov .bk.ov-as-sec .v{grid-area:v;margin-top:var(--sp-1)}
.ov-note{font-size:var(--fs-sm);line-height:1.45;color:var(--ink2)}
.ov .ov-as-sec > .ov-note{grid-area:note;margin-top:var(--sp-1)}
.ov .ov-as-sec > .flag[data-prov]{grid-area:prov;justify-self:start;margin-top:var(--sp-2)}

/* the small arrow of a column line and a register line */
.ov :is(.ov-as-sec,.ov-as-row).clickable > .sig-go{position:static;width:28px;height:28px;background:none;
 color:var(--mut);box-shadow:inset 0 0 0 1px var(--line2);transition:transform .2s,background .15s,color .15s}
.ov :is(.ov-as-sec,.ov-as-row).clickable > .sig-go svg{width:14px;height:14px}
.ov .ov-as-sec.clickable > .sig-go{grid-area:go;align-self:start}
.ov :is(.ov-as-sec,.ov-as-row).clickable:is(:hover,:focus-visible) > .sig-go{background:var(--ink);
 color:var(--surface);box-shadow:none}
.ov :is(.ov-as-sec,.ov-as-row).clickable:is(:hover,:focus-visible) .l{color:var(--accent-ink)}

/* ---- the register ---- */
.ov-reg{border-top:1px solid var(--ink)}
.ov-rows{display:grid;column-gap:var(--sp-5);
 grid-template-columns:minmax(150px,1.15fr) minmax(110px,max-content) max-content max-content minmax(0,2.6fr) 28px}
.ov-rh{grid-column:1 / -1;display:grid;grid-template-columns:subgrid;padding:10px 0 9px;
 border-bottom:1px solid var(--line2);font-size:var(--fs-3xs);font-weight:var(--fw-bold);letter-spacing:.14em;
 text-transform:uppercase;color:var(--dim)}
.ov-rh > span:nth-child(2){text-align:right}
.ov-rh > span:nth-child(3){grid-column:3 / 5}
.ov-rh > span:nth-child(4){grid-column:5}
.ov .bk.ov-as-row{grid-column:1 / -1;display:grid;grid-template-columns:subgrid;align-items:center;
 padding:14px 0;border-bottom:1px solid var(--line)}
.ov .bk.ov-as-row.clickable:is(:hover,:focus-visible){background:var(--hover);
 box-shadow:-10px 0 0 var(--hover),10px 0 0 var(--hover)}
.ov .ov-as-row > .khead{display:contents}
.ov .bk.ov-as-row .l{grid-column:1;grid-row:1 / 3;font-size:var(--fs-sm);font-weight:var(--fw-semibold);
 color:var(--ink);letter-spacing:-.005em;text-transform:none;line-height:1.35}
.ov .bk.ov-as-row .n{grid-column:2;grid-row:1;justify-self:end;text-align:right;font-size:var(--fs-lg);
 letter-spacing:-.01em;font-variant-numeric:tabular-nums;white-space:nowrap}
.ov .bk.ov-as-row .n .cx,.ov .bk.ov-as-row .n small{font-size:var(--fs-2xs)}
.ov .bk.ov-as-row .n .mag{font-size:inherit;color:var(--ink)}
.ov .bk.ov-as-row .v{grid-column:2;grid-row:2;justify-self:end;text-align:right;margin-top:2px;
 font-size:var(--fs-2xs)}
.ov .ov-as-row > .khead > .flag{grid-column:3;grid-row:1 / 3;justify-self:start}
.ov .ov-as-row > .flag[data-prov]{grid-column:4;grid-row:1 / 3;justify-self:start}
.ov .ov-as-row > .ov-note{grid-column:5;grid-row:1 / 3}
.ov .ov-as-row.clickable > .sig-go{grid-column:6;grid-row:1 / 3;justify-self:end}

/* ---- narrower: the columns stack, a register line wraps ---- */
@container panel (max-width:760px){
 .ov-front{grid-template-columns:minmax(0,1fr);padding:var(--sp-5) 0 var(--sp-6)}
 .ov-lead{padding:0 0 var(--sp-6);border-right:0;border-bottom:1px solid var(--line)}
 .ov-sec{padding:var(--sp-5) 0 0}
 .ov .bk.ov-as-lead{grid-template-columns:minmax(0,1fr);grid-template-areas:"head" "say" "dek" "n" "v" "figs" "prov"}
 .ov-say{font-size:var(--fs-xl);line-height:1.3}
 .ov .bk.ov-as-lead .n{margin-top:var(--sp-5);font-size:var(--fs-4xl)}
 .ov-figs{align-self:start;margin-top:var(--sp-4);padding:var(--sp-4) 0 0;border-left:0;border-top:1px solid var(--line)}
 .ov-dek{font-size:var(--fs-sm)}
 .ov-rows{display:block}
 .ov-rh{display:none}
 .ov .bk.ov-as-row{display:flex;flex-direction:row;flex-wrap:wrap;align-items:center;gap:6px 8px;padding:14px 0}
 .ov .bk.ov-as-row.clickable:is(:hover,:focus-visible){box-shadow:none}
 .ov .bk.ov-as-row .l{order:1;flex:1 1 0;min-width:0}
 .ov .bk.ov-as-row .n{order:2}
 .ov .ov-as-row.clickable > .sig-go{order:3;align-self:center}
 .ov .bk.ov-as-row .v{order:4;flex:1 0 100%;margin:0;text-align:right}
 .ov .ov-as-row > .khead > .flag{order:5}
 .ov .ov-as-row > .flag[data-prov]{order:6}
 .ov .ov-as-row > .ov-note{order:7;flex:1 1 12ch;min-width:0}
}

/* ======================================================================
   TABLE TEXT, EVERY SCREEN (16 Nov 2026): a text cell never collapses to a word a line.
   Headers, dates and figures do not wrap (TABLES, above), so beside ten figure columns
   Finances' "Why" column was squeezed to one word wide and one row filled the page.
   legacy/tables.js gives each text cell a band by the length of its text, and its plain
   words one block (.dt-tx) that holds the width: a floor, so it wraps at a readable
   measure, and a ceiling, so it does not run on; an explanation stops at two lines (three
   until 18 Nov 2026: "too busy with plenty text"),
   its whole text in the title (and where the row opens, there). A table then wider
   than its panel scrolls sideways in its own box (.dt-x, .dt-scroll), never the page.
   ====================================================================== */
table.dt td:is(.dt-w1,.dt-w2,.dt-w3){white-space:normal}
table.dt td.dt-w1{min-width:12ch}
table.dt td.dt-w2{min-width:18ch}
table.dt td.dt-w3{min-width:26ch}
table.dt td > .dt-tx{display:block;overflow-wrap:break-word}
table.dt td.dt-w1 > .dt-tx{min-width:12ch;max-width:28ch}
table.dt td.dt-w2 > .dt-tx{min-width:18ch;max-width:34ch}
table.dt td.dt-w3 > .dt-tx{min-width:26ch;max-width:44ch;display:-webkit-box;-webkit-box-orient:vertical;
 -webkit-line-clamp:2;line-clamp:2;overflow:hidden}
@container panel (max-width:560px){
 table.dt td.dt-w3{min-width:24ch}
 table.dt td.dt-w3 > .dt-tx{min-width:24ch;max-width:34ch}
}

/* ======================================================================
   EXECUTIVE SUMMARY -- the memo (16 Nov 2026, the approved mockup-exec-summary.html).
   A board memo with vital signs, above the screen as it was: the heading is its title,
   a heavy rule under it, the week and who it is for, the five vital signs in one ruled
   band, the short version set large, then decisions and risks beside what is going
   well and what is waiting on you. Type, figures and hairlines; no tinted boxes, no
   cards inside the sheet. legacy/summary.js draws it; tokens only.
   ====================================================================== */
.xm{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:26px 30px 18px;
 margin:0 0 var(--sp-8)}
.xm > .topbar{margin:0;padding-bottom:var(--sp-3);border-bottom:1.5px solid var(--ink);align-items:flex-end;
 flex-wrap:wrap;gap:var(--sp-2) var(--sp-6)}
.xm > .topbar h3{font-size:var(--fs-3xl);font-weight:var(--fw-semibold);letter-spacing:-.026em;line-height:1.15}
.xm > .topbar .when{font-size:var(--fs-xs);margin-top:var(--sp-1);color:var(--dim)}
.xm-date{flex:0 1 auto;font-size:var(--fs-xs);color:var(--mut);text-align:right;line-height:1.45;
 font-variant-numeric:tabular-nums;max-width:64ch}
.xm-date:empty,.xm-for:empty{display:none}
.xm-for{margin-top:var(--sp-3);font-size:var(--fs-sm);color:var(--ink2);line-height:1.5}

/* ---- the vital signs: one ruled band, hairlines between ---- */
.xm-vitals{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));margin-top:var(--sp-5);
 border-top:1px solid var(--ink2);border-bottom:1px solid var(--line2)}
.xm-v{appearance:none;background:none;border:0;border-left:1px solid var(--line);border-radius:0;margin:0;
 font:inherit;color:inherit;text-align:left;display:flex;flex-direction:column;gap:var(--sp-1);min-width:0;
 padding:var(--sp-4) var(--sp-3) var(--sp-4) var(--sp-4);cursor:pointer}
.xm-v:nth-child(5n+1){border-left:0;padding-left:0}
.xm-v:disabled{cursor:default}
.xm-v:focus-visible{outline:2px solid var(--accent);outline-offset:-2px;border-radius:var(--r-xs)}
.xm-vl{font-size:var(--fs-xs);font-weight:var(--fw-medium);color:var(--mut);line-height:1.35;transition:color .15s}
.xm-v:not(:disabled):hover .xm-vl{color:var(--accent-ink)}
.xm-vn{font-size:var(--fs-2xl);font-weight:var(--fw-semibold);letter-spacing:-.025em;line-height:1.15;color:var(--ink);
 font-variant-numeric:tabular-nums;white-space:nowrap}
.xm-vn .xm-cx{font-size:var(--fs-xs);font-weight:var(--fw-medium);color:var(--mut);letter-spacing:0;margin-right:5px;
 vertical-align:.3em}
.xm-vn .xm-mag,.xm-vn small{font-size:.62em;font-weight:var(--fw-semibold);color:var(--mut);margin-left:1px;letter-spacing:0}
.xm-vn.none{color:var(--dim)}
.xm-vd{font-size:var(--fs-2xs);font-weight:var(--fw-semibold);color:var(--mut);line-height:1.4;
 font-variant-numeric:tabular-nums}
.xm-vd.good{color:var(--ok)}
.xm-vd.bad{color:var(--crit)}
.xm-vd.wait{font-weight:var(--fw-medium);color:var(--dim)}

/* ---- the sections ---- */
.xm-h{margin:var(--sp-6) 0 var(--sp-3);padding-bottom:6px;border-bottom:1px solid var(--line2);font-size:var(--fs-3xs);
 font-weight:var(--fw-bold);letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.xm-short{margin:0;max-width:74ch;font-size:var(--fs-lg);font-weight:var(--fw-medium);line-height:1.62;
 letter-spacing:-.008em;color:var(--ink);text-wrap:pretty}
.xm-by{margin:var(--sp-2) 0 0;font-size:var(--fs-2xs);line-height:1.5;color:var(--dim)}
.xm-cols{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);column-gap:var(--sp-10)}
.xm-cols > *{min-width:0}
/* numbered by a counter in a column of its own, so the number sits on the first line */
.xm-ol{list-style:none;margin:0;padding:0;counter-reset:xm;font-size:var(--fs-sm);line-height:1.5;color:var(--ink)}
.xm-ol li{counter-increment:xm;display:grid;grid-template-columns:22px minmax(0,1fr);padding:5px 0}
.xm-ol li::before{content:counter(xm) ".";color:var(--dim);font-weight:var(--fw-semibold);
 font-variant-numeric:tabular-nums}
.xm-item{appearance:none;background:none;border:0;padding:0;margin:0;font:inherit;color:var(--ink);
 display:inline;
 font-weight:var(--fw-medium);text-align:left;cursor:pointer;text-decoration:underline;
 text-decoration-color:transparent;text-decoration-thickness:1px;text-underline-offset:.2em;
 transition:text-decoration-color .15s}
.xm-item:hover,.xm-item:focus-visible{text-decoration-color:var(--line2);outline:0}
.xm-k{margin-left:var(--sp-2);font-size:var(--fs-2xs);color:var(--mut);white-space:nowrap}
.xm-k::before{content:"· "}
.xm-sev{margin-left:var(--sp-2);vertical-align:1px}
.xm-well{list-style:none;margin:0;padding:0;font-size:var(--fs-sm);line-height:1.5;color:var(--ink2)}
.xm-well li{display:flex;gap:10px;padding:5px 0}
.xm-well b{color:var(--ink);font-weight:var(--fw-semibold)}
.xm-well li.xm-none{display:block}
/* the tick of a ruled report, drawn with borders so it follows the theme */
.xm-tick{flex:none;position:relative;width:15px;height:15px;margin-top:2px;border-radius:50%;border:1.5px solid var(--ok)}
.xm-tick::after{content:"";position:absolute;left:4px;top:1.5px;width:4px;height:7px;border:solid var(--ok);
 border-width:0 1.5px 1.5px 0;transform:rotate(45deg)}
.xm-none{margin:0;font-size:var(--fs-sm);line-height:1.5;color:var(--mut)}
.xm-counts{list-style:none;margin:0;padding:0}
.xm-count{appearance:none;background:none;border:0;border-bottom:1px solid var(--line);border-radius:0;margin:0;
 font:inherit;color:inherit;width:100%;display:grid;grid-template-columns:44px minmax(0,1fr);align-items:baseline;
 column-gap:var(--sp-2);padding:6px 0;text-align:left;cursor:pointer}
.xm-counts li:last-child .xm-count{border-bottom:0}
.xm-count b{font-size:var(--fs-xl);font-weight:var(--fw-semibold);letter-spacing:-.02em;color:var(--ink);
 font-variant-numeric:tabular-nums;line-height:1.2}
.xm-count span{font-size:var(--fs-sm);color:var(--ink2);transition:color .15s}
.xm-count.zero b{color:var(--dim)}
.xm-count:hover span,.xm-count:focus-visible span{color:var(--accent-ink)}
.xm-count:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:var(--r-xs)}
.xm-link{appearance:none;background:none;border:0;padding:0;margin:var(--sp-2) 0 0;font:inherit;font-size:var(--fs-xs);
 font-weight:var(--fw-semibold);color:var(--accent-ink);cursor:pointer}
.xm-below{margin-top:var(--sp-6);padding-top:var(--sp-2);border-top:1px solid var(--line);font-size:var(--fs-2xs);
 color:var(--dim)}
.xm-below::after{content:" ↓"}
/* the card a decision or a risk scrolls to, marked for a moment */
.alert.xm-reached{box-shadow:0 0 0 2px var(--accent);transition:box-shadow .3s}

/* ---- narrower: the panel, not the window ---- */
@container panel (max-width:1080px){
 .xm-vn{font-size:var(--fs-xl)}
}
@container panel (max-width:860px){
 .xm-vitals{grid-template-columns:repeat(3,minmax(0,1fr))}
 .xm-v,.xm-v:nth-child(5n+1){border-left:1px solid var(--line);padding-left:var(--sp-4)}
 .xm-v:nth-child(3n+1){border-left:0;padding-left:0}
 .xm-v:nth-child(n+4){border-top:1px solid var(--line)}
 .xm-cols{grid-template-columns:minmax(0,1fr)}
}
@container panel (max-width:560px){
 /* a phone: one vital sign to a line, the label left and the figure right */
 .xm{padding:20px 16px 14px;border-radius:var(--r-sm)}
 .xm > .topbar h3{font-size:var(--fs-2xl)}
 .xm-date{text-align:left}
 .xm-vitals{grid-template-columns:minmax(0,1fr)}
 .xm-v,.xm-v:nth-child(5n+1),.xm-v:nth-child(3n+1){display:grid;grid-template-columns:minmax(0,1fr) auto;
  column-gap:var(--sp-3);align-items:baseline;border-left:0;padding:var(--sp-3) 0}
 .xm-v:nth-child(n+2){border-top:1px solid var(--line)}
 .xm-vl{grid-column:1;grid-row:1}
 .xm-vn{grid-column:2;grid-row:1 / span 2;align-self:center;text-align:right}
 .xm-vd{grid-column:1;grid-row:2}
 .xm-short{font-size:var(--fs-md)}
}

/* ---- paper: the memo prints first, whole, on the light page ---- */
@media print{
 .xm{border:0;border-radius:0;padding:0;margin-bottom:var(--sp-6);break-inside:avoid}
 .xm-below{display:none}
}

/* ======================================================================
   The built-in mark (16 Nov 2026): the lens over four bars and a line of ring nodes,
   wherever no logo is uploaded -- the sidebar's .logo (Sidebar.jsx, LensMark.jsx), the
   sign-in page's .auth-mark (command-center-login.html) and the Settings -> Branding
   slots that preview it. Drawn in currentColor on a rounded tile: an ink tile with a
   light mark on a light ground, and the inverse on a dark one (the tokens swap). An
   uploaded logo replaces the tile whole.
   ====================================================================== */
.logo,.auth-mark{color:var(--surface)}
.cc-lens{display:block;width:72%;height:72%;overflow:visible}
/* The four bars inside the lens in the accent chosen under Appearance (as the old mark's
   ring was); the lens, the trend line and its nodes keep the tile's plain colour. */
.cc-lens .cc-lens-b{fill:color-mix(in srgb,var(--accent) 72%,var(--surface))}
/* Ink is the no-colour accent: there the line is simply the mark's own colour. */
[data-accent="ink"] .cc-lens .cc-lens-b{fill:currentColor}
/* The Settings slots are always a light ground, whatever the theme: show the mark as it
   sits on one. */
.st-logo-box .logo{width:44px;height:44px;border-radius:13px}
[data-theme="dark"] .st-logo-box .logo{background:var(--surface);color:var(--ink)}

/* ======================================================================
   The card footer's line (16 Nov 2026). An alert or recommendation card's footer is two
   flex items side by side -- the meta (Records, Owner, Seen since) and the actions (What To
   Do, Ask AI, Done) -- each drawing its own top border (blocks.py). Centred on the line,
   the shorter one sat lower, so the two borders met in a visible 3px step. Stretched to
   the line's full height, both borders start at its top and read as one; their contents
   stay centred (each is a flex row with align-items:center).
   ====================================================================== */
.alert>.ameta,.alert>.acts{align-self:stretch}

/* ======================================================================
   The business card at the foot of the sidebar with a long name (16 Nov 2026). "Gigmann
   Medical Supplies Ltd" broke wherever the column ran out and crowded the line under it.
   Now the name takes at most two lines, balanced so they read as a pair, and ends in an
   ellipsis past that with the full name on hover (title); the "as of" line stays one
   line. The same for the names in the switcher's list.
   ====================================================================== */
.biz-t{flex:1 1 auto}
.biz-t b,.biz-opt-t b{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;
 overflow:hidden;text-wrap:balance;overflow-wrap:anywhere;line-height:1.3}
.biz-t .asof{overflow:hidden;text-overflow:ellipsis}
.biz-opt-t{flex:1 1 auto}
/* The switcher's note on the same 8px inner edge as its rows: the avatar, the note's text
   and its link line up on the left, and the note ends where the names do on the right. */
.biz-menu .biz-note{padding:12px 8px 6px}

/* ======================================================================
   Outstanding Tasks managed here (16 Nov 2026, legacy/work.js, TaskDrawer.jsx,
   ActionDialog.jsx): New Task beside the heading, the tile that filters the list marked
   as chosen, the filter line, rows that open the task's drawer, their four buttons, the
   drawer's facts and comments, and the dialog's optional document and two-up fields.
   ====================================================================== */
.topbar .work-tools{display:flex;gap:var(--sp-2);flex:none;align-items:center}
.bk.work-on{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}
.work-filter{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:var(--sp-3);
 margin:8px 0 4px;padding:10px 14px;border:1px solid var(--line);border-radius:var(--r-sm);
 background:var(--raised);font-size:var(--fs-sm);color:var(--ink2)}
tr.work-row{cursor:pointer}
tr.work-row:hover td{background:var(--raised)}
tr.work-row:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.alert.work-row{cursor:pointer}
td.work-acts{white-space:nowrap}
td.work-acts .btn{margin:0 4px 0 0}
.task-who{font-size:var(--fs-2xl)}
.task-detail{white-space:pre-line}
.task-acts{display:flex;flex-wrap:wrap;gap:var(--sp-2)}
.task-facts{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:8px var(--sp-6);margin:0;
 font-size:var(--fs-sm)}
.task-facts dt{color:var(--mut);font-weight:var(--fw-semibold)}
.task-facts dd{margin:0;color:var(--ink)}
.task-links{display:flex;flex-wrap:wrap;gap:var(--sp-4);margin-top:4px;font-size:var(--fs-sm)}
.task-comments{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:var(--sp-3)}
.task-comments li{padding:10px 14px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--surface)}
.task-comments p{margin:4px 0 0;font-size:var(--fs-sm);line-height:1.55;color:var(--ink2);white-space:pre-line}
.task-c-meta{display:flex;flex-wrap:wrap;gap:var(--sp-2);font-size:var(--fs-xs);color:var(--mut)}
.task-c-meta b{color:var(--ink);font-weight:var(--fw-semibold)}
.dlg-two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:0 var(--sp-3)}
.dlg-doc{margin:16px 0 0;padding:4px 14px 14px;border:1px solid var(--line);border-radius:var(--r-sm)}
.dlg-doc legend{padding:0 6px;font-size:var(--fs-xs);font-weight:var(--fw-semibold);color:var(--mut)}
.ap-act.pri.dgr{background:var(--crit);border-color:var(--crit)}
@media(max-width:600px){
 .dlg-two{grid-template-columns:minmax(0,1fr)}
 .topbar .work-tools{width:100%}
}

/* ---- Settings -> Email -> Email Log (SettingsEmail.jsx): a failed send opens its reason ---- */
.mail-log tr.mail-failed{cursor:pointer}
.mail-log tr.mail-failed:hover td{background:var(--raised)}
.mail-log tr.mail-why td{background:var(--crit-bg);color:var(--ink2);font-size:var(--fs-sm);line-height:1.5;
 white-space:normal}
.mail-log tr.mail-why b{color:var(--crit);font-weight:var(--fw-semibold)}

/* ======================================================================
   Recommendations as a formal list (16 Nov 2026). A report is a professional document:
   its recommendations -- the list under a Recommendations heading (reports.js .md-recs)
   and any list point labelled Recommendation or Projection (markdown.js .md-rec,
   .md-proj) -- are plain numbered or bulleted points in the body text, with no tinted
   box, accent bar or drawn marker, as in the PDF (api/export.py PAGE_CSS). A paragraph
   labelled Recommendation inside a report reads as body text too.
   ====================================================================== */
.md ol.md-recs{list-style:decimal;padding-left:20px;counter-reset:none}
.md ul.md-recs{list-style:disc;padding-left:20px}
.md .md-recs li,.md li.md-rec,.md li.md-proj{position:static;list-style:inherit;background:none;border:0;
 border-radius:0;box-shadow:none;margin:5px 0;padding:0 0 0 2px;color:inherit}
.md .md-recs li::before,.md li.md-rec::before,.md li.md-proj::before{content:none;display:none}
.rp-body .md p.md-rec{position:static;background:none;border:0;border-radius:0;padding:0;color:inherit}
.rp-body .md p.md-rec::before{content:none;display:none}
/* The Projection paragraph too: body text, its label in bold, no box (as the PDF). */
.rp-body .md p.md-proj{position:static;background:none;border:0;border-radius:0;padding:0;color:inherit}
.rp-body .md p.md-proj::before{content:none;display:none}
/* ======================================================================
   Close and bulk actions on Outstanding Tasks (17 Nov 2026, legacy/work.js,
   ActionDialog.jsx BulkChange): a checkbox on each open row, Select All and the count
   above the list, and the bar with Close Selected / Cancel Selected while anything is
   selected -- kept in view at the foot of the panel, and stacked on a phone.
   ====================================================================== */
th.work-pick,td.work-pick{width:36px;padding-right:0;text-align:center}
.work-pick input,.work-all input{width:16px;height:16px;margin:0;accent-color:var(--accent);cursor:pointer}
.work-select{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:var(--sp-3);
 margin:4px 0 8px;font-size:var(--fs-sm);color:var(--ink2)}
.work-all{display:inline-flex;align-items:center;gap:var(--sp-2);cursor:pointer;font-weight:var(--fw-semibold);
 color:var(--ink)}
.work-count{color:var(--mut)}
.work-bulk{position:sticky;bottom:0;z-index:5;display:flex;flex-wrap:wrap;align-items:center;
 justify-content:space-between;gap:var(--sp-3);margin:12px 0 0;padding:10px 14px;
 border:1px solid var(--accent);border-radius:var(--r-sm);background:var(--accent-bg);
 box-shadow:var(--shadow2);font-size:var(--fs-sm);color:var(--ink)}
.work-bulk[hidden]{display:none}
.work-bulk-n{font-weight:var(--fw-semibold)}
.work-bulk-acts{display:flex;flex-wrap:wrap;gap:var(--sp-2)}
.dlg-fails{margin:8px 0 0;padding:0 0 0 18px;max-height:200px;overflow:auto;font-size:var(--fs-sm);
 color:var(--ink2);line-height:1.5}
.dlg-fails b{color:var(--ink);font-weight:var(--fw-semibold)}
@media(max-width:600px){
 .work-bulk{flex-direction:column;align-items:stretch}
 .work-bulk-acts{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--sp-2)}
 .work-bulk-acts .btn{width:100%;margin:0}
 .work-bulk-acts .btn:last-child{grid-column:1 / -1}
}

/* Outstanding Tasks rows: Reassign and the "⋯" menu side by side on one line. */
td.work-acts{white-space:nowrap;vertical-align:middle}
td.work-acts>*{display:inline-flex;vertical-align:middle}
td.work-acts .amenu{margin-left:2px}

/* The sign-in footer's forgotten-password line (16 Nov 2026): the old link went to a page
   the platform does not have; an administrator now emails a set-password link instead. */
body.cc-signin .auth-forgot{display:block;color:var(--ink2)}
body.cc-signin .auth-forgot b{font-weight:var(--fw-semibold);color:var(--ink)}

/* Add Person's password choices: one per line, so three never wrap two-and-one. */
.st-choice[role="radiogroup"]{display:flex;flex-direction:column;align-items:flex-start;gap:8px;margin:4px 0 8px}
.st-choice[role="radiogroup"] .st-check{margin:0}

/* ======================================================================
   The sign-in footer on one line (17 Nov 2026): "Ultrasoft Insights | Built by Ultrasoft
   Systems | +233… | www…". Its two groups sit side by side and wrap as whole groups --
   on a phone, the product and builder over the contacts, as two lines. Separators are a
   thin "|" that takes no room; one that would start a line is hidden (_signin.html marks
   the item .ls), so no line begins with a stray bar.
   ====================================================================== */
.auth-by{display:flex;flex-wrap:wrap;justify-content:center;align-items:baseline;column-gap:24px;row-gap:3px}
.auth-by>.auth-by-l{position:relative;margin:0}
.auth-by>.auth-by-l+.auth-by-l::before,.auth-by-l>span::before{content:"|";position:absolute;
 left:-13px;width:6px;text-align:center;color:var(--dim);font-weight:var(--fw-regular)}
.auth-by-l>span::before{left:-12px}
.auth-by>.auth-by-l.ls::before,.auth-by-l>span.ls::before,.auth-by-l>span:first-child::before{content:none}
@media (max-width:480px){
 .auth-by-c{flex-direction:row;align-items:baseline}
 .auth-by-c>span::before{content:"|"}
 .auth-by-c>span:first-child::before,.auth-by-c>span.ls::before{content:none}
}

/* The sign-in card, crisper (17 Nov 2026): a defined hairline and a tight contact shadow
   under the deep one, so its edge reads sharply against the threads; the foot is two short
   lines, never sentences -- "Forgotten your password?" over "Ask your administrator.", then
   "Management Team Only". */
body.cc-signin .sg-card{border-color:var(--line2);box-shadow:var(--shadow),var(--shadow2)}
body.cc-signin .auth-forgot{display:flex;flex-direction:column;gap:1px}
body.cc-signin .auth-forgot>span{color:var(--mut)}
body.cc-signin .auth-only{color:var(--mut)}
/* The same thin "|" as the footer's, between short items on one line. */
body.cc-signin .auth-sep{font-style:normal;color:var(--dim);margin:0 8px}

/* ======================================================================
   PHONE, EVERY SCREEN (17 Nov 2026): the page never scrolls sideways.
   On an iPhone, Home, the Executive Summary, Today and Approvals scrolled sideways into
   empty space. Not the layout: long unbroken text. An alert's chip said "Email: not
   sent: email is not set up on this platform" on one line (.chip was nowrap), an owner
   or a document name with an email address or a link in it could not break, and each
   pushed its card -- and .main, which scrolls -- wider than the screen. So:
     text      breaks inside its own box (overflow-wrap:anywhere, which also lowers the
               box's smallest width, so a flex or grid child can shrink to its column);
               a table keeps its own rules (below), so a cell is never cut mid-word on a
               laptop
     chips     one line while they fit, wrapping inside themselves when one is longer
               than its row
     tables    on a phone, each row on one line and the table scrolling sideways in its
               own box: the screens' own (tables.js .dt-x), Settings', the drawers' and
               the dialogs'; never the page
     heading   the tools beside a heading (New Task) go under it on a phone, so the
               title and the line under it keep their width
     safety    only then, and only on a phone: the main column never scrolls sideways.
   scripts/test_phone.mjs loads every screen at 375 and 428 wide with long strings and
   fails if the page or the main column is wider than the screen.
   ====================================================================== */
.main{overflow-wrap:anywhere}
.main table,.drawer table,.dlg table{overflow-wrap:normal}
/* A figure is never broken mid-number: it is short, and its box is sized for it. */
.main :is(.val,.n,.afig,.xm-vn,.gauge-mid,.flag,.tag,.dpill,.btn){overflow-wrap:normal}
.chip{max-width:100%;white-space:normal}
.xm-k{white-space:normal}
@media(max-width:600px){
 .topbar{flex-wrap:wrap}
 .topbar .work-tools{flex:1 1 100%}
}
@media(max-width:640px){
 table.dt td{white-space:nowrap}
 table.dt td:is(.dt-w1,.dt-w2,.dt-w3){white-space:nowrap}
 /* A text cell's words (.dt-tx) are one line with a ceiling, and the block clips at the
    ceiling with an ellipsis (the whole text is in its title, and the row opens it): it
    never paints over the next column. These selectors carry the same weight as TABLE
    TEXT's (td.dt-wN > .dt-tx) and come after them, on purpose: the first phone rule here
    was a lighter "td > .dt-tx{max-width:none}", which lost to TABLE TEXT's 28ch and 34ch
    ceilings, so a one-line name or title ran out of its block and over "Given to" on
    Today, Outstanding Tasks, Risk and Internal Audit (17 Nov 2026). test_phone.mjs fails
    any cell whose content is wider than its box and not clipped. */
 table.dt td:is(.dt-w1,.dt-w2,.dt-w3) > .dt-tx{display:block;min-width:0;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
 table.dt td.dt-w1 > .dt-tx{max-width:24ch}
 table.dt td.dt-w2 > .dt-tx{max-width:30ch}
 table.dt td.dt-w3 > .dt-tx{max-width:34ch}
 .drawer table.dt,.dlg table.dt{display:block;max-width:100%;overflow-x:auto}
 :is(.dt-x,.dt-scroll,.fs-wrap,.dw-tbox,.work-table,.vz-table,.scrollbox,.ins-scroll,.sec-scroll) > table.dt{display:table}
}
@media(max-width:900px){
 .main{overflow-x:hidden}
}

/* A refresh that did not come through while the last answers stay on screen
   (LegacyView StaleNote, 17 Nov 2026): one quiet line, never a warning. */
.stale-note{margin:0 0 14px;padding:8px 12px;border-radius:var(--r-sm);background:var(--raised);
 color:var(--mut);font-size:var(--fs-xs);line-height:1.5}

/* A part of the page that failed to draw (components/ErrorBoundary.jsx): one calm line
   and a Reload in its place; the rest of the page stays. */
.cc-crash{display:flex;flex-direction:column;align-items:flex-start;gap:6px;margin:0 0 14px;
 padding:18px 20px;border:1px dashed var(--line2);border-radius:var(--r);background:var(--surface);
 color:var(--mut);font-size:var(--fs-sm);line-height:1.5}
.cc-crash b{color:var(--ink);font-size:var(--fs-md);font-weight:var(--fw-semibold)}
.cc-crash .btn{margin-top:6px}
.askconvs-err{margin-top:8px;font-size:var(--fs-xs);color:var(--mut)}

/* The balance sheet's check when it could not be run: neutral, neither passed nor failed. */
.fs-check.na{background:var(--raised);color:var(--mut)}

/* The drawer's "Biggest Single …": a plain ruled list of documents, not bars, so it never
   reads as a second "Where It Is Concentrated" (Records.jsx Largest). */
.dw-list{list-style:none;margin:0;padding:0}
.dw-list li{border-top:1px solid var(--line)}
.dw-list li:first-child{border-top:0}
.dw-list-row{display:flex;align-items:center;gap:12px;padding:9px 2px;color:inherit;text-decoration:none}
a.dw-list-row:hover .dw-list-t b{color:var(--accent-ink)}
.dw-list-t{display:flex;flex-direction:column;min-width:0;flex:1 1 auto}
.dw-list-t b{font-weight:var(--fw-semibold);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dw-list-t small{font-size:var(--fs-xs);color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dw-list-v{flex:none;font-variant-numeric:tabular-nums;font-weight:var(--fw-semibold)}
/* Stock & Warehouses' Stock Balance and Stock Movements tabs (legacy/stock.js, 17 Nov
   2026): a search and filter bar, a record table that scrolls in its own box, long
   names cut with an ellipsis (whole text in the cell's title), totals at the foot. */
.sk-bar .tcount{white-space:nowrap}
.sk-bar .sk-xl{flex:none}
.sk-dates{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap;min-width:0}
.sk-to{font-size:var(--fs-xs);color:var(--dim)}
.pp-body .filters input.sk-date{flex:0 1 auto;min-width:0;width:auto;padding:5px 9px;
 font-size:var(--fs-xs);color-scheme:light dark}
table.dt.sk-t{width:100%;font-variant-numeric:tabular-nums}
.pp-scroll table.dt.sk-bal{min-width:640px}
.pp-scroll table.dt.sk-mov{min-width:880px}
table.dt.sk-t th{white-space:nowrap}
table.dt.sk-t th.num,table.dt.sk-t td.num{text-align:right;white-space:nowrap}
table.dt.sk-t td.sk-item,table.dt.sk-t td.sk-c{max-width:0}
table.dt.sk-bal td.sk-item{width:40%}
table.dt.sk-bal td.sk-c{width:24%}
table.dt.sk-mov td.sk-item{width:26%}
table.dt.sk-mov td.sk-c{width:14%}
table.dt.sk-t td.sk-v{white-space:nowrap}
.sk-cut{display:block;min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
td.sk-item b.sk-cut{font-weight:var(--fw-semibold);color:var(--ink)}
.sk-code{font-size:var(--fs-2xs);color:var(--dim);margin-top:2px}
table.dt.sk-t td.sk-item,table.dt.sk-t td.sk-c{overflow:hidden}
table.dt tr.sk-row{cursor:pointer}
table.dt tr.sk-row:hover td,table.dt tr.sk-row:focus-visible td{background:var(--hover);outline:none}
table.dt.sk-t tfoot td{border-top:1px solid var(--line2);border-bottom:0;background:var(--raised);
 font-weight:var(--fw-semibold);color:var(--ink)}
@media(max-width:640px){
 .pp-scroll table.dt.sk-bal{min-width:560px}
 .pp-scroll table.dt.sk-mov{min-width:760px}
 table.dt.sk-t td.sk-item,table.dt.sk-t td.sk-c{min-width:120px}
}

/* ======================================================================
   EXECUTIVE SUMMARY GROUPS (17 Nov 2026): the recommendations' areas read at a glance.
   "Categorizations under the executive summary are not noticeable at first glance, so it
   just feels like a long list of things." Each area (legacy/recommend.js .rec-group) is
   set off as a section of a printed report: a hairline rule above it, room before it, its
   name a step below the "Recommendations" heading, and its count in a small plain pill
   beside the name rather than at the far edge where the eye never went. Content and order
   are as they were. Tokens only, so both themes and every accent hold; no tint or shadow.
   ====================================================================== */
.rec-live-list>.rec-group{margin:var(--sp-10) 0 0;padding-top:var(--sp-4);border-top:1px solid var(--line2)}
.rec-live-list>.rec-group:first-child{margin-top:var(--sp-3)}
.rec-group>.rec-area{display:flex;align-items:center;justify-content:flex-start;flex-wrap:wrap;gap:var(--sp-2) 10px;
 margin:0 0 var(--sp-4);font-size:var(--fs-lg);font-weight:var(--fw-semibold);color:var(--ink);line-height:1.3;
 letter-spacing:-.01em}
.rec-group>.rec-area span{display:inline-flex;align-items:center;padding:2px 10px;border:1px solid var(--line2);
 border-radius:var(--r-pill);color:var(--ink2);font-size:var(--fs-xs);font-weight:var(--fw-medium);
 font-variant-numeric:tabular-nums;white-space:nowrap}
.rec-group>.alert:last-child{margin-bottom:0}
.rec-group-closed>.rec-area{color:var(--ink2)}
/* A section heading keeps its words whole on a phone: "Recommendations" broke as
   "Recommendation / s" beside its count line (.main breaks anywhere). The count goes under
   it instead. */
.main .sect{flex-wrap:wrap;column-gap:var(--sp-3)}
.main .sect>span:first-child{overflow-wrap:normal}
@media(max-width:640px){
 .rec-live-list>.rec-group{margin-top:var(--sp-8);padding-top:var(--sp-3)}
 .rec-group>.rec-area{margin-bottom:var(--sp-3)}
}
/* ======================================================================
   NUMBERED ROWS (17 Nov 2026; legacy/fold.js. The owner's choice, "E · Numbered list",
   over the first folded cards.)
   An approval, a recommendation, an alert, a task marked done and a debtor are each one
   numbered row, and open in place for the rest. Editorial, not cards: hairlines between
   the rows, no box, no tint, no coloured pill. Tokens only, so both themes and every
   accent hold.
     row     the number (the list's own count) | the title, one line, and under it one
             quiet line in small capitals ("CRITICAL · SALES · FINANCE") | the figure |
             the primary button, on the lists that have one | the chevron. One line at
             any width: the title ellipsises, nothing else wraps or shrinks.
     colour  only Critical, and a debt overdue past 90 days, is in the danger colour;
             the primary button is a neutral filled one, the rest are hairline-outlined
     open    hung from a hairline at the title's left edge, so everything in it starts
             where the title starts: the why and the step, the figure box to their right,
             then ONE line -- the facts on the left, the buttons on the right
     narrow  under 480px of panel the figure leaves the row for the expansion
             (.fold-fig-x), and the buttons go under the facts, still on one line
   ====================================================================== */
.fold,.debt-cols{--fold-pad:8px;--fold-num:28px;--fold-gap:16px}
:has(> .fold),[data-fold-list]{counter-reset:fold}
[data-fold-list] .rec-group{counter-reset:none}
.alert.fold{display:block;padding:0;margin:0;background:none;border:0;border-top:1px solid var(--line);
 border-radius:0;box-shadow:none;counter-increment:fold}
.alert.fold:not(:has(+ .alert.fold)){border-bottom:1px solid var(--line);margin-bottom:var(--sp-3)}
.alert.fold:hover,.alert.fold:is(.crit,.high,.med,.info):hover{border-color:var(--line)}
.fold-row{display:flex;align-items:center;gap:var(--fold-gap);min-width:0;padding:12px var(--fold-pad);cursor:pointer}
.fold-row:hover{background:var(--hover)}
.fold-t{display:grid;grid-template-columns:var(--fold-num) minmax(0,1fr) auto;column-gap:var(--fold-gap);
 align-items:baseline;flex:1 1 auto;min-width:0;margin:0;padding:0;border:0;background:none;font:inherit;
 color:inherit;text-align:left;cursor:pointer}
.fold-t:focus-visible{outline:2px solid var(--accent);outline-offset:6px;border-radius:var(--r-xs)}
.fold-t::before{content:counter(fold,decimal-leading-zero);content:counter(fold,decimal-leading-zero) / "";
 font-size:var(--fs-xs);font-weight:var(--fw-medium);color:var(--dim);font-variant-numeric:tabular-nums;
 letter-spacing:.02em}
.fold-tt{display:flex;flex-direction:column;gap:3px;min-width:0}
.fold-t .fold-title{display:block;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
 font-size:var(--fs-md);font-weight:var(--fw-semibold);letter-spacing:-.01em;line-height:1.4;color:var(--ink)}
.fold-t .debt-name b{font-weight:inherit}
.fold-on .fold-t .fold-title{white-space:normal;overflow-wrap:anywhere}
.fold-k{display:block;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
 font-size:var(--fs-2xs);font-weight:var(--fw-medium);letter-spacing:.08em;text-transform:uppercase;
 line-height:1.4;color:var(--mut)}
.fold-crit{color:var(--crit);font-weight:var(--fw-semibold)}
.fold-t>.afig{background:none;padding:0;border-radius:0;font-size:var(--fs-md);font-weight:var(--fw-semibold);
 letter-spacing:-.01em;line-height:1.4;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.fold-t>.afig .cx{font-size:var(--fs-2xs);color:var(--mut);font-weight:var(--fw-medium);margin-right:4px}
.fold-t>.afig .mag{font-size:inherit;color:var(--ink2);font-weight:inherit;margin-left:1px}
.fold-t>.afig small{display:inline;margin:0 0 0 4px;font-size:var(--fs-2xs);color:var(--mut)}
.fold-on.fold-boxed>.fold-row .fold-t>.afig{visibility:hidden}
.fold-pri{flex:none;display:inline-flex}
.fold-chev{flex:none;width:16px;height:16px;display:grid;place-items:center;color:var(--dim)}
.fold-chev::before{content:"";width:6px;height:6px;border-right:1.5px solid currentColor;
 border-bottom:1.5px solid currentColor;transform:translateY(-2px) rotate(45deg);transition:transform .15s}
.fold-on>.fold-row .fold-chev::before{transform:translateY(2px) rotate(-135deg)}
.fold-row:hover .fold-chev{color:var(--ink2)}
/* Buttons: restrained corners; the primary is the ink itself, the rest a hairline. */
.fold .btn,.fold .amenu-b{border-radius:6px;padding:5px 12px;background:transparent;border:1px solid var(--line2);
 color:var(--ink2);font-size:var(--fs-xs);font-weight:var(--fw-medium);line-height:1.4;box-shadow:none}
.fold .amenu-b{width:auto;height:auto;padding:5px 10px;display:inline-flex;align-items:center}
.fold .btn:hover,.fold .amenu-b:hover,.fold .amenu.on .amenu-b{border-color:var(--mut);color:var(--ink);background:transparent}
.fold .btn.pri{background:var(--ink);border-color:var(--ink);color:var(--surface)}
.fold .btn.pri:hover{background:var(--ink);border-color:var(--ink);color:var(--surface);filter:none;opacity:.86}
.fold .btn.dgr{color:var(--crit);border-color:var(--line2)}
.fold .btn.dgr:hover{border-color:var(--crit)}
/* The expansion: one left edge, the title's. The hairline sits in the gap before it. */
.fold-b{margin:0 var(--fold-pad) 16px calc(var(--fold-pad) + var(--fold-num) + var(--fold-gap) / 2);
 padding:2px 0 2px calc(var(--fold-gap) / 2 - 1px);border-left:1px solid var(--line2);border-radius:0;min-width:0}
.fold-b[hidden]{padding:0;border:0;margin:0}
.fold-b>*{min-width:0}
.fold-b>*+*{margin-top:var(--sp-3)}
.fold-main{display:grid;grid-template-columns:minmax(0,1fr) auto;column-gap:var(--sp-6);align-items:start}
.fold-text{min-width:0}
.fold-text>*+*,.fold-what>*+*{margin-top:6px}
.fold-b .awhy{margin:0;font-size:var(--fs-sm);color:var(--ink2);line-height:1.55}
.fold-b .asw{margin:0;font-size:var(--fs-sm);color:var(--ink);font-weight:var(--fw-medium);line-height:1.55}
.fold-what>.asw,.fold-text>.asw{margin-top:6px}
.fold-b .rec-why-now{margin:0;font-size:var(--fs-xs);color:var(--mut);line-height:1.5}
.fold-b .work-detail{margin:6px 0 0}
.fold-b .fold-what.work-row{cursor:pointer;border-radius:var(--r-xs)}
.fold-b .fold-what.work-row:hover .awhy{color:var(--ink)}
.fold-b .fold-what.work-row:focus-visible{outline:2px solid var(--accent);outline-offset:4px}
.fold-box{display:flex;flex-direction:column;align-items:flex-end;gap:8px;padding:10px 14px;border:1px solid var(--line);
 border-radius:6px;background:none;text-align:right}
.fold-box .afig{background:none;padding:0;font-size:var(--fs-xl);font-weight:var(--fw-semibold);letter-spacing:-.02em;
 font-variant-numeric:tabular-nums}
.fold-box .afig .cx{font-size:var(--fs-xs);color:var(--mut)}
.fold-box .afig .mag{font-size:var(--fs-lg);color:var(--ink2)}
.fold-box .afig small{display:block;margin-top:2px;text-align:right}
.fold-b>.rec-steps{padding:var(--sp-3) 0 0;border-top:1px solid var(--line);border-radius:0;background:none;
 font-size:var(--fs-sm);color:var(--ink2);line-height:1.55}
.fold-b>.rec-steps .rec-learned{margin-top:10px;padding-top:8px;border-top:1px solid var(--line)}
.fold-b>.rec-reason{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.fold-b>.afig.fold-fig-x{background:none;padding:0;font-size:var(--fs-lg);font-weight:var(--fw-semibold)}
.fold-fig-x,.fold-b .afig.fold-fig-x,.fold-foot .debt-a.fold-fig-x{display:none}
/* The last line: the facts as plain grey words on the left, the buttons on the right. */
.fold-foot{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-2) var(--sp-4);min-width:0}
/* Each fact's dot sits in the gap before it; the first on each line falls outside the box
   and is clipped, so a line never starts with one. */
.fold-foot>.ameta{flex:1 1 auto;display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 17px;min-width:0;margin:0;
 overflow:hidden;font-size:var(--fs-xs);color:var(--mut);line-height:1.5}
.fold-foot>.ameta>*{position:relative}
.fold-foot>.ameta>*::before{content:"·";position:absolute;left:-11px;color:var(--dim);font-weight:var(--fw-regular)}
.fold-foot .chip,.fold-foot .chip.src,.fold-foot a.chip{background:none;border:0;border-radius:0;padding:0;
 font-size:var(--fs-xs);color:var(--mut);white-space:nowrap;max-width:none}
.fold-foot .chip b{color:var(--ink2);font-weight:var(--fw-medium)}
.fold-foot .chip.src,.fold-foot a.chip{cursor:pointer;text-decoration:underline;text-decoration-color:var(--line2);
 text-underline-offset:3px;white-space:normal}
.fold-foot .chip.src b{color:inherit;font-weight:inherit}
.fold-foot .chip.src:hover,.fold-foot a.chip:hover{background:none;color:var(--ink);text-decoration-color:currentColor}
.fold-foot .rec-src{cursor:help}
.fold-foot>.acts{flex:none;display:flex;flex-wrap:nowrap;align-items:center;gap:6px;margin:0 0 0 auto}
/* Largest Receivables: the customer and the Customer Ledger Balance, the heading's two
   columns over them; the line under it ends in Open Ledger. */
.debt-cols{display:grid;grid-template-columns:minmax(0,1fr) auto;
 padding-left:calc(22px + var(--fold-num) + var(--fold-gap));padding-right:calc(22px + 16px + var(--fold-gap))}
.debt-cols span:last-child{text-align:right}
.debt-rows>.debt-row.fold{--fold-pad:22px;display:block;padding:0;border:0;border-bottom:1px solid var(--line);
 cursor:default;counter-increment:fold}
.debt-rows>.debt-row.fold:last-child{border-bottom:0}
.debt-rows>.debt-row.fold:hover{background:none}
.debt-row .fold-t>.debt-a{align-items:flex-end}
.debt-row .fold-t>.debt-a b{font-size:var(--fs-md)}
.debt-row .fold-t>.debt-a b .cx{color:var(--mut);font-size:var(--fs-2xs);font-weight:var(--fw-medium)}
.debt-row .fold-t>.debt-a small{display:none}
.fold-foot .debt-open{display:inline-flex;align-items:baseline;gap:6px;width:auto;margin:0;padding:0;border:0;
 background:none;font:inherit;font-size:var(--fs-xs);font-weight:var(--fw-medium);color:var(--ink2);cursor:pointer;
 text-decoration:underline;text-decoration-color:var(--line2);text-underline-offset:3px;white-space:nowrap}
.fold-foot .debt-open:hover{color:var(--ink);text-decoration-color:currentColor}
.fold-foot .debt-open:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.fold-foot .debt-open .debt-arrow{text-decoration:none;color:inherit}
@container panel (max-width:720px){
 .debt-rows>.debt-row.fold{--fold-pad:16px}
}
@container panel (max-width:480px){
 .fold,.debt-rows>.debt-row.fold{--fold-num:20px;--fold-gap:10px}
 .alert.fold{--fold-pad:4px}
 .fold-t>.afig,.fold-t>.debt-a{display:none}
 .fold-fig-x,.fold-b .afig.fold-fig-x{display:block}
 .fold-foot .debt-a.fold-fig-x{display:inline-flex;flex-direction:row-reverse;align-items:baseline;gap:4px}
 .fold-foot .debt-a.fold-fig-x b{font-size:var(--fs-xs);font-weight:var(--fw-medium);color:var(--ink2)}
 .fold-foot .debt-a.fold-fig-x b .cx{display:none}
 .fold-foot .debt-a.fold-fig-x small{font-size:var(--fs-xs);color:var(--mut)}
 .fold-main{grid-template-columns:minmax(0,1fr)}
 .fold-box{justify-self:start;align-items:flex-start;text-align:left;margin-top:var(--sp-3)}
 .fold-box .afig small{text-align:left}
 .fold-foot{flex-wrap:wrap}
 .fold-foot>.acts{flex:1 0 100%;justify-content:flex-end}
 .fold-pri .btn{padding:5px 10px}
 .fold-t .fold-title{white-space:normal;overflow-wrap:anywhere;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2}
 .fold-on .fold-t .fold-title{display:block;-webkit-line-clamp:none}
}

/* ======================================================================
   LEAN CARDS (18 Nov 2026; legacy/lean.js). "Some of the cards are too busy with plenty
   text": a card leads with its heading, its figure or chart and one line of reading. A
   subtitle, a note, a finding's sentence and a screen's banner show one line; a panel's
   list of explanations three; words cut short end in a chevron and open on a click. A
   "How This Works" box is its heading until clicked. The words themselves are unchanged.
   ====================================================================== */
.lean.lean:not(.lean-open){display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:var(--lean,1);
 line-clamp:var(--lean,1);overflow:hidden}
.lean.lean-open{display:block}
.lean-box.lean-box:not(.lean-open){max-height:calc(var(--lean,3) * 1lh);overflow:hidden;
 -webkit-mask-image:linear-gradient(#000 55%,transparent);mask-image:linear-gradient(#000 55%,transparent)}
.lean-can{position:relative;cursor:pointer;padding-right:20px}
.lean-can:is([data-lean="pad"]){padding-right:34px}
.lean-can::after{content:"";position:absolute;right:4px;top:calc(var(--lean-pt,0px) + .5lh - 5px);width:6px;height:6px;
 border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;color:var(--mut);opacity:.75;
 transform:rotate(45deg);transition:transform .15s,opacity .15s}
.lean-can[data-lean="pad"]::after{right:16px}
.lean-can:hover::after{opacity:1}
.lean-can[aria-expanded="true"]::after{transform:rotate(-135deg);top:calc(var(--lean-pt,0px) + .5lh - 1px)}
.lean-can:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
.warn > b{display:block;margin-bottom:2px}
.warn > .warn-t{margin-bottom:2px}
.lean-note > h4{cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:0}
.lean-note > h4::after{content:"";flex:none;width:7px;height:7px;border-right:1.5px solid currentColor;
 border-bottom:1.5px solid currentColor;transform:rotate(45deg) translate(-2px,-2px);color:var(--mut);transition:transform .15s}
.lean-note.lean-open > h4{margin-bottom:10px}
.lean-note.lean-open > h4::after{transform:rotate(-135deg) translate(-2px,-2px)}
.lean-note:not(.lean-open) > :not(h4){display:none}
.lean-note > h4:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:4px}
"""
