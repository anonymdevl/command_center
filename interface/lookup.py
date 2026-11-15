# -*- coding: utf-8 -*-
"""The HR screen's People Lookup and Leave (15 Nov 2026): their search bar, results,
profile drawer and leave tables. frontend/src/legacy/people.js builds every node; the
card itself is .ppanel (blocks.py, beside .panel). Tokens only, both themes."""

LOOKUP_CSS = """
/* ============ PEOPLE LOOKUP AND LEAVE (lookup.py) ============ */
.pp-body{min-width:0}
.pp-body .filters input{flex:1 1 220px;min-width:0}
.pp-body .filters select{max-width:100%}
.pp-scroll{overflow-x:auto;max-width:100%}
.pp-scroll table.dt{min-width:620px}
.pp-scroll.narrow table.dt{min-width:0}
table.dt tr.pp-row{cursor:pointer}
table.dt tr.pp-row:focus-visible td{background:var(--hover);outline:none}
.pp-who{display:flex;align-items:center;gap:10px;min-width:0}
.pp-who b{font-weight:var(--fw-semibold);color:var(--ink)}
.pp-sub{font-size:var(--fs-2xs);color:var(--dim);margin-top:2px}
.pp-av{width:32px;height:32px;border-radius:50%;background:var(--accent-bg);color:var(--accent-ink);
 display:inline-flex;align-items:center;justify-content:center;font-size:var(--fs-2xs);
 font-weight:var(--fw-semibold);flex:none;overflow:hidden}
.pp-av img{width:100%;height:100%;object-fit:cover;display:block}
.pp-av.big{width:56px;height:56px;font-size:var(--fs-lg)}
.pp-pager{display:flex;align-items:center;gap:8px;margin-top:12px;flex-wrap:wrap}
.pp-pager .tcount{margin-left:0}
.pp-sort{background:none;border:0;color:inherit;font:inherit;cursor:pointer;padding:0;text-align:inherit}
.pp-sort:hover{color:var(--ink)}
.pp-note{font-size:var(--fs-xs);color:var(--mut);margin-top:10px;line-height:1.5}
.pp-empty{font-size:var(--fs-sm);color:var(--dim);padding:6px 0}
.pp-list{list-style:none;margin:0;padding:0}
.pp-list li{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid var(--line);
 font-size:var(--fs-sm);align-items:baseline}
.pp-list li:last-child{border-bottom:0}
.pp-list li > span:last-child{color:var(--mut);font-size:var(--fs-xs);white-space:nowrap;text-align:right}
.pp-list .lnk{font-family:var(--sans);font-size:var(--fs-sm)}
.pp-h{font-size:var(--fs-xs);color:var(--dim);font-weight:var(--fw-semibold);margin:12px 0 2px}
.pp-head{display:flex;gap:14px;align-items:center;min-width:0}
.pp-head h4{font-size:var(--fs-xl);font-weight:var(--fw-semibold);letter-spacing:-.015em;margin:2px 0 0}
.pp-prof .sect{margin:20px 0 8px}
.pp-prof .kv{grid-template-columns:130px minmax(0,1fr)}
.pp-prof .kv dd{min-width:0;overflow-wrap:anywhere}
.pp-meter{height:6px;border-radius:var(--r-pill);background:var(--raised);overflow:hidden;margin-top:5px;min-width:48px}
.pp-meter > span{display:block;height:100%;background:var(--accent)}
.pp-chips{display:flex;flex-wrap:wrap;gap:6px}
.pp-prof table.dt th,.pp-prof table.dt td{padding:9px 8px}
@media (max-width:560px){
 .pp-prof table.dt{font-size:var(--fs-xs)}
 .pp-prof table.dt th,.pp-prof table.dt td{padding:8px 5px}
 .pp-prof .pp-meter{min-width:36px}
}
@container panel (max-width:560px){
 .pp-prof .kv{grid-template-columns:minmax(0,1fr)}
 .pp-prof .kv dt{margin-top:6px}
 .pp-list li{flex-direction:column;gap:2px}
 .pp-list li > span:last-child{text-align:left;white-space:normal}
}
"""
