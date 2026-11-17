# -*- coding: utf-8 -*-
# ============ FINANCIAL STATEMENTS (the head of the Finances screen) ============
# The empty frame only: the period switch, the export buttons, and one tab per statement.
# Every figure, account, date and the currency are the business's own, read when the
# screen opens (api/statements.py) and drawn by frontend/src/legacy/statements.js. The
# block carries data-lead, so tabify() keeps it at the top, above the screen's own cards
# and tabs: the first thing a chief executive sees on Finances.
FS_PERIODS = [("this_month", "This Month"), ("last_month", "Last Month"), ("quarter", "This Quarter"),
              ("ytd", "Year to Date"), ("last_year", "Last Year"), ("custom", "Custom")]
FS_TABS = ["Profit and Loss", "Balance Sheet", "Trial Balance", "Cash Flow", "Key Ratios"]
FS_PARTS = ["pl", "bs", "tb", "cf", "ratios"]


def fs_block():
    periods = "".join(
        f'<button type="button" class="fs-p{" on" if k == "ytd" else ""}" data-period="{k}" '
        f'data-cc-wired="1" aria-pressed="{"true" if k == "ytd" else "false"}">{lab}</button>'
        for k, lab in FS_PERIODS)
    tabs = "".join(f'<button class="tab{" on" if i == 0 else ""}" onclick="tab(this,\'fs\',{i})">{t}</button>'
                   for i, t in enumerate(FS_TABS))
    panes = "".join(f'<div class="tabpane{" on" if i == 0 else ""}" data-g="fs" data-i="{i}">'
                    f'<div class="fs-body" data-part="{p}"></div></div>'
                    for i, p in enumerate(FS_PARTS))
    return (
        '<div class="fs" id="fs" data-lead="1">'
        '<div class="fs-head"><div class="fs-title"><b>Financial Statements</b>'
        '<span id="fs-when"></span></div>'
        '<div class="fs-tools">'
        f'<div class="fs-periods" role="group" aria-label="Period">{periods}</div>'
        '<div class="fs-custom" id="fs-custom" hidden>'
        '<label>From <input type="date" id="fs-from"></label>'
        '<label>To <input type="date" id="fs-to"></label>'
        '<button type="button" class="btn" id="fs-apply" data-cc-wired="1">Show</button></div>'
        '<div class="fs-exports">'
        '<button type="button" class="btn" id="fs-xlsx" data-cc-wired="1">Excel</button>'
        '<button type="button" class="btn" id="fs-pdf" data-cc-wired="1">PDF</button></div>'
        '</div></div>'
        '<div class="fs-state" id="fs-state" hidden></div>'
        '<div class="kpis fs-cards ribbon" id="fs-cards"></div>'
        f'<div class="tabbar" data-g="fs">{tabs}</div>{panes}'
        '</div>')


FS_CSS = """
/* ============ FINANCIAL STATEMENTS ============ */
.fs{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:18px 20px;
 margin:0 0 18px}
.fs-head{display:flex;justify-content:space-between;align-items:flex-start;gap:var(--sp-3);flex-wrap:wrap;
 margin-bottom:var(--sp-4)}
.fs-title b{display:block;font-size:var(--fs-lg);font-weight:var(--fw-semibold);letter-spacing:-.015em}
.fs-title span{display:block;margin-top:3px;font-size:var(--fs-xs);color:var(--mut)}
.fs-tools{display:flex;flex-wrap:wrap;gap:var(--sp-2);align-items:center;justify-content:flex-end;
 min-width:0;max-width:100%}
.fs-title{min-width:0}
.fs-periods{display:flex;flex-wrap:wrap;gap:2px;min-width:0;max-width:100%;background:var(--raised);border:1px solid var(--line);
 border-radius:var(--r-pill);padding:3px}
.fs-p{background:none;border:0;border-radius:var(--r-pill);padding:6px 12px;font:var(--fw-semibold) var(--fs-xs) var(--sans);
 color:var(--mut);cursor:pointer;white-space:nowrap}
.fs-p:hover{color:var(--ink)}
.fs-p.on{background:var(--surface);color:var(--ink);box-shadow:var(--shadow-hover)}
.fs-custom{display:flex;gap:var(--sp-2);align-items:center;flex-wrap:wrap;font-size:var(--fs-xs);color:var(--mut)}
.fs-custom[hidden]{display:none}
.fs-custom input{font:var(--fw-medium) var(--fs-xs) var(--sans);color:var(--ink);background:var(--bg);
 border:1px solid var(--line2);border-radius:var(--r-xs);padding:5px 8px;margin-left:4px}
.fs-exports{display:flex;gap:6px}
.fs-state{margin:0 0 var(--sp-4);font-size:var(--fs-sm);color:var(--mut)}
.fs-cards{margin-bottom:var(--sp-2);grid-template-columns:repeat(5,minmax(0,1fr))}
.fs-cards:empty{display:none}
.fs .kpi .delta.up{color:var(--ok)}
.fs .kpi .delta.down{color:var(--crit)}
.fs-body{min-height:40px}
.fs-body h4{font-size:var(--fs-sm);font-weight:var(--fw-semibold);margin:var(--sp-5) 0 var(--sp-2)}
.fs-body h4:first-child{margin-top:0}
.fs-sub{font-size:var(--fs-xs);color:var(--mut);margin:-4px 0 var(--sp-2)}
.fs-notes{margin:var(--sp-3) 0 0;padding-left:18px;font-size:var(--fs-xs);color:var(--mut);line-height:1.55}
.fs-notes li{margin:3px 0}
.fs-check{display:inline-flex;align-items:center;gap:6px;font-size:var(--fs-xs);font-weight:var(--fw-semibold);
 border-radius:var(--r-pill);padding:4px 10px;margin:var(--sp-3) 0 0}
.fs-check.ok{background:var(--ok-bg);color:var(--ok)}
.fs-check.bad{background:var(--crit-bg);color:var(--crit)}
.fs-wait{font-size:var(--fs-sm);color:var(--mut);padding:var(--sp-3) 0}
.fs-wrap{overflow-x:auto;max-width:100%}
.fs-wrap.tall{max-height:560px;overflow-y:auto;border:1px solid var(--line);border-radius:var(--r-sm)}
.fs-wrap.tall table.dt th{position:sticky;top:0;background:var(--surface);z-index:1}
table.dt.fs-t{width:100%;font-variant-numeric:tabular-nums}
table.dt.fs-t td,table.dt.fs-t th{padding:8px 12px}
table.dt.fs-t td.n,table.dt.fs-t th.n{text-align:right;white-space:nowrap}
table.dt.fs-t tr.fs-group td,table.dt.fs-t tr.fs-heading td{font-weight:var(--fw-semibold)}
table.dt.fs-t tr.fs-total td{font-weight:var(--fw-bold);border-top:1px solid var(--line2)}
table.dt.fs-t tr.fs-heading td{color:var(--mut)}
table.dt.fs-t td.neg{color:var(--crit)}
table.dt.fs-t td.pos{color:var(--ok)}
table.dt.fs-t tr.fs-deep{display:none}
.fs-all table.dt.fs-t tr.fs-deep{display:table-row}
table.dt.fs-t a.fs-acc{color:inherit;text-decoration:none;border-bottom:1px dotted var(--line2)}
table.dt.fs-t a.fs-acc:hover{color:var(--accent);border-bottom-color:var(--accent)}
.fs-more{margin-top:var(--sp-2)}
.fs-mean{font-size:var(--fs-xs);color:var(--mut);line-height:1.5}
@container panel (max-width:1199px){
 .fs-cards{grid-template-columns:repeat(3,minmax(0,1fr))}}
@container panel (max-width:560px){
 .fs{padding:14px 12px}
 .fs-head,.fs-tools{justify-content:flex-start}
 .fs-periods{overflow-x:auto;flex-wrap:nowrap;max-width:100%;scrollbar-width:none}
 .fs-periods::-webkit-scrollbar{display:none}
 table.dt.fs-t td,table.dt.fs-t th{padding:7px 8px}}
"""
