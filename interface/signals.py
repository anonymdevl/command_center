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
    # The vivid level is the base palette in p1.py; these must stay equal to it.
    "dark": {"crit": "#f0695e", "high": "#e8994a", "med": "#e3c063", "ok": "#3fc48e"},
    "light": {"crit": "#c2392f", "high": "#a85a0a", "med": "#856307", "ok": "#127a55"},
}
# The solid pills (status as a filled pill with white words, 18 Oct 2026). Darker than
# the text colours above so white reads on them; each level desaturates them by the
# same factor as everything else, so Vivid, Muted and Quiet differ on pills too.
# One set for both themes: the brighter dark-theme set left white words under 4.5:1
# (amber 3.7:1), and a deep pill still stands out on a dark surface.
_SOLID = {"crit": "#c2392f", "high": "#b35a0b", "med": "#946f05", "ok": "#127a55"}
SOLID = {"dark": _SOLID, "light": _SOLID}

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
    # Pills take half the level's desaturation: a filled pill already carries less
    # chroma per pixel than a word does, and at full strength Muted's pills went dusty.
    out.append(" " + " ".join(f"--{n}-solid:{desaturate(c, sat / 2)};" for n, c in SOLID[theme].items()))
    out.append("}")
    return "\n".join(out)


def _solid(selector, theme):
    # --*-dot is Quiet's single mark of severity, so no level desaturates it: a grey dot
    # says nothing.
    return (f"{selector}{{" + " ".join(f"--{n}-solid:{c}; --{n}-dot:{c};"
                                       for n, c in SOLID[theme].items())
            + " --on-solid:#fff}")


SIGNAL_CSS = "\n".join([
    "/* ============ SIGNAL LEVELS (derived, see module docstring) ============ */",
    "/* vivid is the base palette in :root; only the solid pills need stating here. */",
    _solid(":root", "dark"),
    _solid('[data-theme="light"]', "light"),
    _block('[data-signal="muted"]', "dark", "muted"),
    _block('[data-theme="light"][data-signal="muted"]', "light", "muted"),
    _block('[data-signal="quiet"]', "dark", "quiet"),
    _block('[data-theme="light"][data-signal="quiet"]', "light", "quiet"),
]) + """

/* Quiet also changes the treatment, not just the hue: a severity block becomes a
   neutral chip with a single coloured dot, so colour marks the row without
   filling it. */
[data-signal="quiet"] .tag{background:var(--raised);color:var(--mut);border:1px solid var(--line2);
 display:inline-flex;align-items:center;gap:7px;font-weight:var(--fw-semibold)}
[data-signal="quiet"] .tag::before{content:"";width:6px;height:6px;border-radius:50%;flex:none}
[data-signal="quiet"] .t-od::before{background:var(--crit)}
[data-signal="quiet"] .t-wt::before{background:var(--high)}
[data-signal="quiet"] .t-ok::before{background:var(--ok)}
[data-signal="quiet"] .t-dr::before{background:var(--dim)}
[data-signal="quiet"] .kpi .flag{background:var(--raised);color:var(--mut);border-color:var(--line2)}
[data-signal="quiet"] .asw{color:var(--mut)}
[data-signal="quiet"] .alert{border-left-width:2px}
[data-signal="quiet"] .num[style*="--crit"]{font-weight:var(--fw-bold)}
"""

SIGNAL_OPTIONS = ('<option value="vivid">Vivid</option>'
                  '<option value="muted">Muted</option>'
                  '<option value="quiet">Quiet</option>')

# The appearance menu is styled in shell.py with the rest of the shell.


def swatches(ACC):
    out=[]
    for k,lab,grp,li,dk,note in ACC:
        out.append(f'<button class="sw" data-a="{k}" title="{lab} — {note}" '
                   f'onclick="setAccent(\'{k}\')" '
                   f'style="background:linear-gradient(135deg,{dk} 0 50%,{li} 50% 100%)"></button>')
    return "".join(out)
