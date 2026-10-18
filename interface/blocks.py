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

/* ---- alerts: the severity edge stays, the box gets quieter ---- */
.alert{background:var(--surface);border:1px solid var(--line);border-left-width:3px;border-radius:var(--r-sm);
 padding:18px 20px;margin-bottom:12px;box-shadow:none}
.awhat{font-size:var(--fs-lg);font-weight:var(--fw-semibold);letter-spacing:-.015em}
.awhy{font-size:var(--fs-sm);color:var(--mut)}
.asw{font-size:var(--fs-sm)}
.afig{font-weight:var(--fw-semibold)}
.chip{font-size:var(--fs-xs);padding:5px 12px;background:var(--surface)}

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

/* ---- the records drawer ---- */
.drawer{border-left:0;border-radius:24px 0 0 24px;box-shadow:var(--shadow2)}
"""
