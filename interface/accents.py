# -*- coding: utf-8 -*-
def hx(h): 
    h=h.lstrip('#'); return tuple(int(h[i:i+2],16) for i in (0,2,4))
def to(rgb): return '#%02x%02x%02x'%tuple(max(0,min(255,round(c))) for c in rgb)
def mix(a,b,t):
    ra,rb=hx(a),hx(b); return to(tuple(ra[i]+(rb[i]-ra[i])*t for i in range(3)))
def rgba(h,a):
    r,g,b=hx(h); return f"rgba({r},{g},{b},{a})"
def lum(h):
    r,g,b=[c/255 for c in hx(h)]
    f=lambda c: c/12.92 if c<=.03928 else ((c+.055)/1.055)**2.4
    return .2126*f(r)+.7152*f(g)+.0722*f(b)
def ratio(a,b):
    la,lb=lum(a),lum(b); hi,lo=max(la,lb),min(la,lb); return (hi+.05)/(lo+.05)

# (key, label, group, light accent, dark accent, note)
ACCENTS=[
 ("gold","Gold","Golds and browns","#8c6108","#e3b champion","the original — classic with cream"),
 ("brass","Brass","Golds and browns","#786012","#d9c069","softer, more antique than gold"),
 ("bronze","Bronze","Golds and browns","#7d5626","#d0a museum","browner, less yellow"),
 ("copper","Copper","Golds and browns","#9c4f24","#e09062","warm and strong — sits near the warning orange"),
 ("coffee","Coffee","Golds and browns","#584234","#c0a89a","deep espresso brown, very quiet"),
 ("petrol","Petrol","Blues and teals","#0d5c6b","#7fd4dd","deep teal-cyan — the classic cream partner"),
 ("teal","Teal","Blues and teals","#126b63","#68cfc2","greener than petrol"),
 ("ink","Ink","Blues and teals","#1f3d63","#8fb4f0","deep navy — quiet and institutional"),
 ("steel","Steel","Blues and teals","#2c5773","#8cb8d6","mid blue, a little softer than ink"),
 ("slate","Slate","Blues and teals","#3f4f63","#a3b4c9","blue-grey, deliberately recessive"),
 ("plum","Plum","Purples and reds","#5e2d54","#d49ccd","aubergine — editorial, warm-leaning"),
 ("wine","Wine","Purples and reds","#6d2739","#d69aa6","oxblood — rich, sits near the critical red"),
 ("violet","Violet","Purples and reds","#5348c7","#9aa0f5","the indigo you had before"),
 ("olive","Olive","Greens","#55601f","#bcc77a","earthy and dry"),
 ("sage","Sage","Greens","#44604f","#9dc2ac","muted green — sits near the success green"),
 ("charcoal","Charcoal","Neutral","#33343a","#a8aab4","no colour at all; the numbers carry it"),
]
# fix the two placeholder typos deterministically
FIX={"gold":"#e3b95e","bronze":"#d0a071"}
ACCENTS=[(k,l,g,li,FIX.get(k,dk),n) for k,l,g,li,dk,n in ACCENTS]

def css():
    out=[]
    for k,lab,grp,li,dk,note in ACCENTS:
        out.append(f'/* {lab} — {note} */')
        out.append(
          f'[data-accent="{k}"]{{--accent:{dk};--accent-ink:{mix(dk,"#ffffff",.35)};'
          f'--accent-dim:{mix(dk,"#0a0c11",.72)};'
          f'--accent-bg:{rgba(dk,".10")};--accent-bg2:{rgba(dk,".17")};'
          f'--info:{dk};--star:{mix(dk,"#ffffff",.45)};--moon:{dk};--solid:{dk};'
          f'--grad:linear-gradient(135deg,{dk},{mix(dk,"#0a0c11",.28)})}}')
        out.append(
          f'[data-theme="light"][data-accent="{k}"]{{--accent:{li};--accent-ink:{mix(li,"#000000",.22)};'
          f'--accent-dim:{mix(li,"#ffffff",.76)};'
          f'--accent-bg:{rgba(li,".08")};--accent-bg2:{rgba(li,".15")};'
          f'--info:{li};--star:{li};--moon:{li};--solid:#1a1a20;'
          f'--grad:linear-gradient(135deg,{li},{mix(li,"#ffffff",.22)})}}')
    return "\n".join(out)

def options():
    out=[];seen=[]
    for k,lab,grp,li,dk,note in ACCENTS:
        if grp not in seen: 
            if seen: out.append('</optgroup>')
            out.append(f'<optgroup label="{grp}">'); seen.append(grp)
        out.append(f'<option value="{k}">{lab}</option>')
    out.append('</optgroup>')
    return "".join(out)
