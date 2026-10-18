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

# The five accents approved with the restyle mockup (17 Oct 2026). They replace the
# sixteen of the first design, gold included: a long menu of near-neighbours was part
# of what made the interface read as generated rather than designed.
#
# (key, label, group, light accent, dark accent, note)
# Each dark variant was picked to clear 4.5:1 against the dark surface, and Amber's
# light variant was deepened from the mockup's #B5650B, which reads 4.35:1 on white.
ACCENTS=[
 ("cobalt","Cobalt","Accents","#2443e8","#6a7fef","the default — clear, confident blue"),
 ("emerald","Emerald","Accents","#0c7a62","#5aa594","deep green, calm and medical"),
 ("ink","Ink","Accents","#1b1e24","#e4e6ea","no colour at all; the numbers carry it"),
 ("amber","Amber","Accents","#a85e09","#cd9659","warm, sits near the warning colour"),
 ("plum","Plum","Accents","#6a3d9e","#9a7bbd","quiet purple, editorial"),
]
DEFAULT_ACCENT="cobalt"

# Surfaces the accents are judged against -- the --surface of each theme in p1.py.
SURFACE={"light":"#ffffff","dark":"#141518"}

def on(c):
    """Text on an accent fill: whichever of white or ink reads better.

    A fixed white failed the moment an accent was pale, which every dark-theme
    variant is -- white on #6a7fef is 3.3:1.
    """
    return "#ffffff" if ratio("#ffffff",c)>=ratio("#111317",c) else "#111317"

def css():
    out=[]
    for k,lab,grp,li,dk,note in ACCENTS:
        out.append(f'/* {lab} — {note} */')
        out.append(
          f'[data-accent="{k}"]{{--accent:{dk};--accent-ink:{mix(dk,"#ffffff",.35)};'
          f'--accent-dim:{mix(dk,SURFACE["dark"],.72)};'
          f'--accent-bg:{rgba(dk,".10")};--accent-bg2:{rgba(dk,".17")};'
          f'--info:{dk};--star:{mix(dk,"#ffffff",.45)};--moon:{dk};--solid:{dk};'
          f'--on-accent:{on(dk)};--grad:linear-gradient({dk},{dk})}}')
        out.append(
          f'[data-theme="light"][data-accent="{k}"]{{--accent:{li};--accent-ink:{mix(li,"#000000",.22)};'
          f'--accent-dim:{mix(li,"#ffffff",.76)};'
          f'--accent-bg:{rgba(li,".08")};--accent-bg2:{rgba(li,".14")};'
          f'--info:{li};--star:{li};--moon:{li};--solid:{li};'
          f'--on-accent:{on(li)};--grad:linear-gradient({li},{li})}}')
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
