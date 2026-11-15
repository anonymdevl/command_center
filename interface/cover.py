# -*- coding: utf-8 -*-
"""Promised Orders — Cover (15 Nov 2026): the state filter, the table of order lines and
the line drawer. frontend/src/legacy/cover.js builds every node; the panel itself is the
designed .panel. Tokens only, both themes."""

COVER_CSS = """
/* ============ PROMISED ORDERS — COVER (cover.py) ============ */
.cover{min-width:0}
.cv-states{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
.cv-s{display:inline-flex;align-items:center;gap:7px;background:var(--surface);border:1px solid var(--line2);
 border-radius:var(--r-pill);padding:5px 11px;font:var(--fw-medium) var(--fs-xs) var(--sans);color:var(--mut);
 cursor:pointer;max-width:100%}
.cv-s:hover{border-color:var(--accent);color:var(--ink)}
.cv-s.on{background:var(--accent-bg);border-color:var(--accent);color:var(--accent-ink)}
.cv-s:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.cv-dot{width:7px;height:7px;border-radius:50%;flex:none}
.cv-l{font-weight:var(--fw-semibold);white-space:nowrap}
.cv-n{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--dim)}
.cv-s.on .cv-n{color:inherit}
.cv-flags{font-size:var(--fs-xs);color:var(--mut);margin:0 0 10px;line-height:1.5}
.cv-scroll{overflow-x:auto;max-width:100%}
.cv-scroll table.dt.cv-t{min-width:860px;width:100%}
table.dt.cv-t td{vertical-align:top}
table.dt.cv-t th,table.dt.cv-t td.num,table.dt.cv-t td.cv-o{white-space:nowrap}
table.dt.cv-t td.cv-item{min-width:180px}
table.dt.cv-t tr.cv-row{cursor:pointer}
table.dt.cv-t tr.cv-row:hover td,table.dt.cv-t tr.cv-row:focus-visible td{background:var(--hover);outline:none}
table.dt.cv-t td.cv-item{max-width:260px;overflow-wrap:anywhere}
table.dt.cv-t td.cv-by{font-size:var(--fs-xs);color:var(--mut);min-width:120px}
.cv-late{font-size:var(--fs-2xs);color:var(--crit);margin-top:3px}
.cv-tags{display:inline-flex;flex-wrap:wrap;gap:5px;align-items:center}
.cv-pill{font-size:var(--fs-2xs);font-weight:var(--fw-semibold);color:var(--mut);border-radius:var(--r-pill);
 padding:2px 8px;box-shadow:inset 0 0 0 1px var(--line2);white-space:nowrap}
.cv-pill.late{color:var(--high);box-shadow:inset 0 0 0 1px var(--high)}
.tag.t-oo{color:var(--on-solid);background:var(--accent)}
.tag.t-rq{color:var(--on-solid);background:var(--med-solid)}
.cv-more{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:10px 0 0}
.cv-count{font-size:var(--fs-xs);color:var(--dim)}
.cv-note{margin-top:12px}
.cover .guide{margin-top:12px}
.cv-d .dhead h4{overflow-wrap:anywhere}
.cv-sub{font-size:var(--fs-xs);color:var(--mut);margin-top:3px}
.cv-say{font-size:var(--fs-sm);line-height:1.6;margin:12px 0 14px;color:var(--ink)}
.cv-kv{grid-template-columns:130px minmax(0,1fr)}
.cv-kv dd{min-width:0;overflow-wrap:anywhere}
.cv-list{list-style:none;margin:0;padding:0}
.cv-list li{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid var(--line);
 font-size:var(--fs-sm);align-items:baseline}
.cv-list li:last-child{border-bottom:0}
.cv-list li > span:first-child{min-width:0;overflow-wrap:anywhere}
.cv-list li > span:last-child{color:var(--mut);font-size:var(--fs-xs);text-align:right}
.cv-c{border:1px solid var(--line);border-radius:var(--r-sm);padding:10px 12px;margin:0 0 10px;background:var(--surface)}
.cv-ch{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px}
.cv-ch .lnk{font-weight:var(--fw-semibold)}
.cv-m{font-size:var(--fs-xs);color:var(--mut)}
.cv-k{font-size:var(--fs-2xs);font-weight:var(--fw-bold);letter-spacing:.04em;text-transform:uppercase;
 border-radius:var(--r-pill);padding:2px 8px}
.cv-k.linked{background:var(--ok-bg);color:var(--ok)}
.cv-k.likely{background:var(--med-bg);color:var(--stale)}
.cv-why{font-size:var(--fs-xs);color:var(--mut);margin:6px 0 2px;line-height:1.5}
.cv-docs{margin-top:6px;border-top:1px dashed var(--line2)}
.cv-empty{font-size:var(--fs-sm);color:var(--dim);padding:6px 0}
.cv-miss{font-size:var(--fs-sm);color:var(--crit);font-weight:var(--fw-semibold);margin:8px 0 0}
.cv-tip{font-size:var(--fs-xs);color:var(--mut);margin:8px 0 0;line-height:1.5}
.cv-split .drfoot{margin-top:8px}
@container panel (max-width:560px){
 .cv-kv{grid-template-columns:minmax(0,1fr)}
 .cv-kv dt{margin-top:6px}
 .cv-list li{flex-direction:column;gap:2px}
 .cv-list li > span:last-child{text-align:left}
 .cv-s{padding:5px 9px}
}
@media (max-width:560px){
 .cv-d .dhead{gap:10px}
 table.dt.cv-t th,table.dt.cv-t td{padding:8px 6px}
}
"""
