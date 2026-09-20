# -*- coding: utf-8 -*-
# Severity expressed three ways. Same meaning, very different volume.
SIGNAL_CSS = """
/* ============ SIGNAL: MUTED ============ */
/* same four steps, chroma pulled right down so colour stops competing with content */
[data-signal="muted"]{
 --crit:#e0a09b; --crit-bg:rgba(224,160,155,.10); --crit-line:rgba(224,160,155,.26);
 --high:#d4ab87; --high-bg:rgba(212,171,135,.10); --high-line:rgba(212,171,135,.26);
 --med:#c6bb92; --med-bg:rgba(198,187,146,.10); --med-line:rgba(198,187,146,.26);
 --ok:#93b8a8;  --ok-bg:rgba(147,184,168,.10);  --ok-line:rgba(147,184,168,.26);
 --ok-glow:rgba(147,184,168,.40); --stale:#c6bb92;
}
[data-theme="light"][data-signal="muted"]{
 --crit:#9c4440; --crit-bg:rgba(156,68,64,.08); --crit-line:rgba(156,68,64,.22);
 --high:#8a6136; --high-bg:rgba(138,97,54,.09); --high-line:rgba(138,97,54,.22);
 --med:#70633c;  --med-bg:rgba(112,99,60,.10);  --med-line:rgba(112,99,60,.22);
 --ok:#3f6355;   --ok-bg:rgba(63,99,85,.09);    --ok-line:rgba(63,99,85,.22);
 --ok-glow:rgba(63,99,85,.28); --stale:#8a6136;
}

/* ============ SIGNAL: QUIET ============ */
/* muted hues, and severity moves from a coloured block to a single coloured dot */
[data-signal="quiet"]{
 --crit:#e0a09b; --crit-bg:rgba(224,160,155,.09); --crit-line:rgba(224,160,155,.22);
 --high:#d4ab87; --high-bg:rgba(212,171,135,.09); --high-line:rgba(212,171,135,.22);
 --med:#c6bb92; --med-bg:rgba(198,187,146,.09); --med-line:rgba(198,187,146,.22);
 --ok:#93b8a8;  --ok-bg:rgba(147,184,168,.09);  --ok-line:rgba(147,184,168,.22);
 --ok-glow:rgba(147,184,168,.36); --stale:#c6bb92;
}
[data-theme="light"][data-signal="quiet"]{
 --crit:#9c4440; --crit-bg:rgba(156,68,64,.07); --crit-line:rgba(156,68,64,.20);
 --high:#8a6136; --high-bg:rgba(138,97,54,.08); --high-line:rgba(138,97,54,.20);
 --med:#70633c;  --med-bg:rgba(112,99,60,.09);  --med-line:rgba(112,99,60,.20);
 --ok:#3f6355;   --ok-bg:rgba(63,99,85,.08);    --ok-line:rgba(63,99,85,.20);
 --ok-glow:rgba(63,99,85,.26); --stale:#8a6136;
}
[data-signal="quiet"] .tag{background:var(--raised);color:var(--mut);border:1px solid var(--line2);
 display:inline-flex;align-items:center;gap:7px;font-weight:560}
[data-signal="quiet"] .tag::before{content:"";width:6px;height:6px;border-radius:50%;flex:none}
[data-signal="quiet"] .t-od::before{background:var(--crit)}
[data-signal="quiet"] .t-wt::before{background:var(--high)}
[data-signal="quiet"] .t-ok::before{background:var(--ok)}
[data-signal="quiet"] .t-dr::before{background:var(--dim)}
[data-signal="quiet"] .kpi .flag{background:var(--raised);color:var(--mut);border-color:var(--line2)}
[data-signal="quiet"] .asw{color:var(--mut)}
[data-signal="quiet"] .num[style*="--crit"]{font-weight:650}
"""
SIGNAL_OPTIONS = ('<option value="vivid">Vivid</option>'
                  '<option value="muted">Muted</option>'
                  '<option value="quiet">Quiet</option>')

APPEAR_CSS = """
.appear{position:relative}
.appearmenu{position:absolute;top:calc(100% + 10px);right:0;width:292px;background:var(--panel);
 border:1px solid var(--line2);border-radius:var(--r2);padding:15px 16px;z-index:60;
 box-shadow:var(--shadow2);display:none}
.appearmenu.on{display:block}
.amsec{font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);
 font-weight:700;margin:0 0 9px}
.amsec:not(:first-child){margin-top:17px}
.seg{display:flex;background:var(--raised);border:1px solid var(--line);border-radius:999px;padding:3px}
.seg button{flex:1;background:none;border:none;color:var(--mut);font:540 11.5px var(--sans);
 padding:6px 4px;border-radius:999px;cursor:pointer;white-space:nowrap;transition:.14s}
.seg button:hover{color:var(--ink)}
.seg button.on{background:var(--surface);color:var(--ink);box-shadow:var(--shadow)}
.swatches{display:grid;grid-template-columns:repeat(8,1fr);gap:7px}
.sw{width:100%;aspect-ratio:1;border-radius:999px;border:1px solid var(--line2);cursor:pointer;
 padding:0;position:relative;transition:transform .12s}
.sw:hover{transform:scale(1.13)}
.sw.on{box-shadow:0 0 0 2px var(--panel),0 0 0 3.5px var(--ink)}
.swname{font-size:11px;color:var(--mut);margin-top:9px;text-align:center;min-height:14px}
"""

def swatches(ACC):
    out=[]
    for k,lab,grp,li,dk,note in ACC:
        out.append(f'<button class="sw" data-a="{k}" title="{lab} — {note}" '
                   f'onclick="setAccent(\'{k}\')" '
                   f'style="background:linear-gradient(135deg,{dk} 0 50%,{li} 50% 100%)"></button>')
    return "".join(out)
