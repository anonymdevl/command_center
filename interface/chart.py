SQ=chr(39)
# -*- coding: utf-8 -*-
def _n(v): return f"{v:,.0f}"

def line_chart(labels, series, h=150, fmt=lambda v:_n(v), color="var(--accent)", fill=True):
    vals=[v for s in series for v in s["data"] if v is not None]
    if not vals: vals=[0]
    mx=max(vals) or 1; n=len(labels); w=100.0
    step = w/(n-1) if n>1 else w
    out=[f'<svg viewBox="0 0 100 40" preserveAspectRatio="none" style="width:100%;height:{h}px;display:block">']
    for gy in (0,.25,.5,.75,1):
        y=2+36*gy
        out.append(f'<line x1="0" y1="{y:.1f}" x2="100" y2="{y:.1f}" stroke="var(--line)" stroke-width=".15"/>')
    for s in series:
        pts=[]
        for i,v in enumerate(s["data"]):
            if v is None: continue
            x=i*step; y=38-(v/mx)*36
            pts.append(f"{x:.2f},{y:.2f}")
        if not pts: continue
        c=s.get("color",color)
        if fill and len(pts)>1:
            out.append(f'<polygon points="{pts[0].split(",")[0]},38 {" ".join(pts)} {pts[-1].split(",")[0]},38" fill="{c}" opacity=".13"/>')
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{c}" stroke-width=".7" stroke-linejoin="round"/>')
    out.append('</svg>')
    lab=''.join(f'<span style="flex:1;text-align:center">{l}</span>' for l in labels)
    return (f'<div class="chartwrap">{"".join(out)}'
            f'<div class="xlab">{lab}</div>'
            f'<div class="ymax">peak {fmt(mx)}</div></div>')

def bar_chart(rows, h=None, fmt=lambda v:_n(v), color="var(--accent)"):
    mx=max([r[1] for r in rows]) or 1
    out=['<div class="bars">']
    for r in rows:
        lab,val=r[0],r[1]
        c=r[2] if len(r)>2 else color
        note=r[3] if len(r)>3 else ""
        pct=val/mx*100
        out.append(f'''<div class="barrow"><div class="barlab">{lab}</div>
<div class="bartrack"><div class="barfill" style="width:{pct:.1f}%;background:{c}"></div></div>
<div class="barval">{fmt(val)}{f'<span class="barnote">{note}</span>' if note else ''}</div></div>''')
    out.append('</div>')
    return "".join(out)

def stacked(segments, h=26):
    tot=sum(s[1] for s in segments) or 1
    segs="".join(f'<div style="width:{s[1]/tot*100:.2f}%;background:{s[2]}" title="{s[0]}"></div>' for s in segments)
    key="".join(f'<span class="kdot" style="background:{s[2]}"></span>{s[0]} <b>{_n(s[1])}</b>' for s in segments)
    return f'<div class="stack" style="height:{h}px">{segs}</div><div class="stackkey">{key}</div>'

def funnel(stages):
    mx=max(s[1] for s in stages) or 1
    out=['<div class="funnel">']
    for name,cnt,val,note in stages:
        pct=cnt/mx*100
        out.append(f'''<div class="fstage"><div class="fbar" style="width:{max(pct,2):.1f}%"></div>
<div class="ftxt"><b>{name}</b> · {_n(cnt)}{f" · GHS {_n(val)}" if val else ""}</div>
<div class="fnote">{note}</div></div>''')
    out.append('</div>')
    return "".join(out)

CHART_CSS = """
.chartwrap{position:relative;background:var(--surface);border:1px solid var(--line);
 border-radius:9px;padding:12px 12px 6px}
.chartwrap svg{overflow:visible}
.xlab{display:flex;margin-top:6px;font-size:9px;color:var(--dim)}
.ymax{position:absolute;top:8px;right:12px;font-size:10px;color:var(--dim)}
.bars{display:flex;flex-direction:column;gap:6px}
.barrow{display:grid;grid-template-columns:1fr 3fr auto;gap:10px;align-items:center;font-size:12px}
.barlab{color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bartrack{background:var(--raised);border-radius:4px;height:16px;overflow:hidden}
.barfill{height:100%;border-radius:4px}
.barval{font-variant-numeric:tabular-nums;font-weight:550;white-space:nowrap;font-size:11.5px}
.barnote{color:var(--dim);font-weight:400;margin-left:6px;font-size:10.5px}
.stack{display:flex;border-radius:5px;overflow:hidden;margin:4px 0 8px}
.stackkey{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--mut);align-items:center}
.kdot{width:9px;height:9px;border-radius:2px;display:inline-block;margin-right:5px}
.funnel{display:flex;flex-direction:column;gap:7px}
.fstage{position:relative;background:var(--raised);border-radius:6px;padding:9px 12px;overflow:hidden}
.fbar{position:absolute;inset:0;background:var(--accent);opacity:.17}
.ftxt{position:relative;font-size:12.5px}
.fnote{position:relative;font-size:10.5px;color:var(--mut);margin-top:2px}
.thin{background:var(--thin-bg);border:1px dashed var(--line2);border-radius:8px;
 padding:11px 13px;font-size:11.5px;color:var(--dim);line-height:1.5}
.thin b{color:var(--mut)}
"""
