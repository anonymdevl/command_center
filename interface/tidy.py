# -*- coding: utf-8 -*-
import re

def split_blocks(html):
    """Split a view's HTML into top-level sibling blocks."""
    out=[];depth=0;buf=""
    i=0
    for m in re.finditer(r'<(/?)(\w+)([^>]*?)(/?)>', html):
        seg=html[i:m.end()]; buf+=seg; i=m.end()
        tag=m.group(2); closing=m.group(1)=='/'; selfclose=m.group(4)=='/' or tag in ('br','img','input','hr','meta')
        if tag not in ('div','table','ul','ol','p','svg','dl'): continue
        if selfclose: continue
        if closing:
            depth-=1
            if depth==0:
                out.append(buf); buf=""
        else:
            depth+=1
    if html[i:].strip(): 
        if out: out[-1]+=html[i:]
        else: out.append(html[i:])
    return [b for b in out if b.strip()]

def _merge_headers(blocks):
    """A bare <div class="sect"> heading belongs with the block that follows it."""
    out=[];pending=""
    for b in blocks:
        stripped=re.sub(r'<[^>]+>','',b).strip()
        is_header = 'class="sect"' in b and len(b)<400 and b.count('<div')<=2
        if is_header:
            pending+=b
        else:
            out.append(pending+b); pending=""
    if pending:
        if out: out[-1]+=pending
        else: out.append(pending)
    return out

def tabify(view_html, tabs=("Overview","Detail","Not yet measured"), ov_count=3):
    """Header (topbar+kpis) stays; remaining blocks are split across tabs."""
    blocks=_merge_headers(split_blocks(view_html))
    head=[];rest=[]
    for b in blocks:
        if 'class="topbar"' in b or 'class="kpis' in b or 'class="banner"' in b:
            head.append(b)
        else:
            rest.append(b)
    gaps=[];body=[]
    for b in rest:
        # a block is a "gap" block if its only substantive content is a thin note
        thin=b.count('class="thin"')
        has_data = ('<table' in b and 'drt' not in b) or 'chartwrap' in b or 'class="bars"' in b \
                   or 'class="funnel"' in b or 'class="stack"' in b or 'class="bk"' in b \
                   or 'class="alert' in b or 'class="bul"' in b or 'class="kv"' in b
        if thin and not has_data: gaps.append(b)
        else: body.append(b)
    ov=body[:ov_count]; det=body[ov_count:]
    if not det: det=[]
    panes=[]
    names=[]
    if ov: names.append(tabs[0]); panes.append("".join(ov))
    if det: names.append(tabs[1]); panes.append("".join(det))
    if gaps: names.append(tabs[2]); panes.append("".join(gaps))
    if len(panes)<=1:
        return "".join(head)+"".join(panes)
    tid="t"+str(abs(hash(view_html))%99999)
    bar="".join(f'<button class="tab{" on" if i==0 else ""}" onclick="tab(this,\'{tid}\',{i})">{n}'
                f'{f"<span class=tc>{panes[i].count(chr(60)+chr(100)+chr(105)+chr(118)+chr(32)+chr(99)+chr(108)+chr(97)+chr(115)+chr(115)+chr(61)+chr(34)+chr(112)+chr(97)+chr(110)+chr(101)+chr(108))}</span>" if False else ""}</button>'
                for i,n in enumerate(names))
    pn="".join(f'<div class="tabpane{" on" if i==0 else ""}" data-g="{tid}" data-i="{i}">{p}</div>'
               for i,p in enumerate(panes))
    return "".join(head)+f'<div class="tabbar" data-g="{tid}">{bar}</div>'+pn

TIDY_CSS = """
[data-theme="light"] .kpi:hover,[data-theme="light"] .bk:hover{border-color:var(--accent);
 box-shadow:0 3px 8px rgba(28,24,16,.09),0 12px 26px rgba(28,24,16,.10)}

.scrollbox{max-height:330px;overflow-y:auto;border:1px solid var(--line);border-radius:var(--r)}
.scrollbox table.dt th{position:sticky;top:0;background:var(--surface);z-index:1}
.scrollbox table.dt td:first-child,.scrollbox table.dt th:first-child{padding-left:12px}

/* breathing room under charts, tables and lists before a following note */
.thin{margin-top:12px}
.bars + .thin, table + .thin, .stack + .thin, .chartwrap + .thin, .funnel + .thin{margin-top:14px}
.panel + .warn, table + .warn{margin-top:16px}
.bars{margin-bottom:2px}
.panel table.dt{margin-bottom:0}
/* wide tables inside half-width panels get room rather than wrapping */
.two .panel table.dt{font-size:12px}
.two .panel table.dt th,.two .panel table.dt td{padding:7px 7px}
.wide{grid-column:1/-1}
.panel.full table.dt th{white-space:nowrap}

.tabbar{display:flex;gap:2px;border-bottom:1px solid var(--line);margin:18px 0 16px}
.tab{background:none;border:none;border-bottom:2px solid transparent;color:var(--mut);
 padding:9px 15px;font-size:12.5px;font-weight:540;cursor:pointer;margin-bottom:-1px;white-space:nowrap}
.tab:hover{color:var(--ink)}
.tab.on{color:var(--accent);border-bottom-color:var(--accent)}
.tabpane{display:none}.tabpane.on{display:block}
/* --- left nav hierarchy --- */
.side{padding:14px 9px}
.navgrp{margin-bottom:4px}
.navsec{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);
 padding:14px 10px 6px;font-weight:700;display:flex;align-items:center;gap:7px}
.navsec::after{content:"";flex:1;height:1px;background:var(--line)}
.navi{padding:7px 10px;border-radius:7px;font-size:12.5px;margin:1px 0}
.navi.on{background:linear-gradient(90deg,var(--accent-bg2),transparent);
 color:var(--ink);font-weight:600;box-shadow:inset 2px 0 0 var(--accent)}
.navi.sub{padding-left:20px;font-size:12px}
.navi.sub::before{content:"";width:4px;height:4px;border-radius:50%;background:var(--line2);
 position:absolute;margin-left:-12px;margin-top:6px}
.navi{position:relative}
.navi.sub.on::before{background:var(--accent)}
/* --- alert actions: one primary + overflow --- */
.acts{gap:6px;align-items:center}
.more{position:relative}
.morebtn{background:none;border:1px solid var(--line2);color:var(--mut);border-radius:999px;
 padding:6px 11px;font-size:12px;cursor:pointer;line-height:1;white-space:nowrap}
.morebtn:hover{color:var(--ink)}
.moremenu{position:absolute;bottom:calc(100% + 6px);left:0;background:var(--raised);
 border:1px solid var(--line2);border-radius:8px;padding:5px;display:none;z-index:20;
 box-shadow:0 10px 30px var(--shadow2);min-width:168px}
.moremenu.on{display:block}
.moremenu button{display:block;width:100%;text-align:left;background:none;border:none;
 color:var(--mut);padding:7px 11px;font-size:12px;border-radius:7px;cursor:pointer;white-space:nowrap}
.moremenu button:hover{background:var(--hover);color:var(--ink)}
.moremenu button.dgr{color:var(--crit)}
"""
