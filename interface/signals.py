# -*- coding: utf-8 -*-
"""Severity expressed three ways. Same meaning, three volumes.

The three levels used to be three hand-written colour tables, and Quiet's hexes
were an exact copy of Muted's -- only the background alpha differed, by 0.01.
Switching between them changed nothing anyone could see. Three tables cannot be
kept in step by hand, so they are derived from one:

    vivid   the base palette, full chroma. Colour does the work.
    muted   chroma pulled down. Still colour-coded, no longer shouting.
    quiet   chroma pulled down hard and the blocks nearly gone. Severity survives
            as a dot and as weight -- the numbers carry it.

Each level is a saturation factor and a pair of alphas, so the gaps between them
are a property of the arithmetic rather than of someone's typing.
"""
import colorsys


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _to(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c * 255))) for c in rgb)


def _rgba(h, a):
    r, g, b = (round(c * 255) for c in _hex(h))
    return f"rgba({r},{g},{b},{a})"


def desaturate(h, factor, lift=0.0):
    """Pull chroma out, optionally nudging lightness back toward mid.

    Lightness is held deliberately: dropping saturation alone can leave a colour
    too dark to read against the surface, and the point of a quieter level is
    less shout, not less legible.
    """
    r, g, b = _hex(h)
    hu, li, sa = colorsys.rgb_to_hls(r, g, b)
    sa *= (1 - factor)
    li = min(1.0, max(0.0, li + lift))
    return _to(colorsys.hls_to_rgb(hu, li, sa))


# (saturation removed, background alpha, border alpha, glow alpha, lightness lift)
LEVELS = {
    "muted": (0.42, 0.10, 0.26, 0.40, 0.00),
    "quiet": (0.82, 0.045, 0.13, 0.22, 0.00),
}

BASE = {
    "dark": {"crit": "#f4726e", "high": "#f5a15c", "med": "#f2cc6b", "ok": "#5ed6a4"},
    "light": {"crit": "#b8382f", "high": "#a45a0e", "med": "#87630a", "ok": "#0c6a4d"},
}
# No lift. Raising lightness as chroma comes out was meant to keep quiet colours
# legible, but on a pale surface lighter means *less* contrast -- it pushed the
# light theme's quiet critical to 4.43:1, under the 4.5 threshold. Desaturating
# alone keeps every level above it.
LIFT = {"dark": 0.0, "light": 0.0}


def _block(selector, theme, level):
    sat, bg, line, glow, _ = LEVELS[level]
    out = [f"{selector}{{"]
    for name, base in BASE[theme].items():
        c = desaturate(base, sat, LIFT[theme] if level == "quiet" else 0.0)
        out.append(f" --{name}:{c}; --{name}-bg:{_rgba(c, bg)}; "
                   f"--{name}-line:{_rgba(c, line)};")
    ok = desaturate(BASE[theme]["ok"], sat, LIFT[theme] if level == "quiet" else 0.0)
    med = desaturate(BASE[theme]["med"], sat, LIFT[theme] if level == "quiet" else 0.0)
    out.append(f" --ok-glow:{_rgba(ok, glow)}; --stale:{med};")
    out.append("}")
    return "\n".join(out)


SIGNAL_CSS = "\n".join([
    "/* ============ SIGNAL LEVELS (derived, see module docstring) ============ */",
    "/* vivid is the base palette in :root -- it needs no rules of its own. */",
    _block('[data-signal="muted"]', "dark", "muted"),
    _block('[data-theme="light"][data-signal="muted"]', "light", "muted"),
    _block('[data-signal="quiet"]', "dark", "quiet"),
    _block('[data-theme="light"][data-signal="quiet"]', "light", "quiet"),
]) + """

/* Quiet also changes the treatment, not just the hue: a severity block becomes a
   neutral chip with a single coloured dot, so colour marks the row without
   filling it. */
[data-signal="quiet"] .tag{background:var(--raised);color:var(--mut);border:1px solid var(--line2);
 display:inline-flex;align-items:center;gap:7px;font-weight:560}
[data-signal="quiet"] .tag::before{content:"";width:6px;height:6px;border-radius:50%;flex:none}
[data-signal="quiet"] .t-od::before{background:var(--crit)}
[data-signal="quiet"] .t-wt::before{background:var(--high)}
[data-signal="quiet"] .t-ok::before{background:var(--ok)}
[data-signal="quiet"] .t-dr::before{background:var(--dim)}
[data-signal="quiet"] .kpi .flag{background:var(--raised);color:var(--mut);border-color:var(--line2)}
[data-signal="quiet"] .asw{color:var(--mut)}
[data-signal="quiet"] .alert{border-left-width:2px}
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
