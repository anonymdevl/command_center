#!/usr/bin/env python3
"""Emit the design system and the legacy view markup for the React frontend.

    python3 scripts/build_interface.py

The interface is moving from generated vanilla markup to React components. This
script is the bridge, and it produces two things:

    frontend/src/styles/command-center.css   the approved design system
    frontend/src/legacy/views.json           each view's markup, as data

A view with a real component renders that component. A view without one renders
its legacy markup, so the whole interface keeps working while it is converted a
screen at a time. `legacy/` shrinks to nothing as components land, and when it is
empty this script and `interface/` go with it.

The CSS is not legacy. It is the design system, it transfers unchanged, and Vite
bundles it.
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IFACE = os.path.join(ROOT, "interface")
FE = os.path.join(ROOT, "frontend", "src")

CSS_OUT = os.path.join(FE, "styles", "command-center.css")
VIEWS_OUT = os.path.join(FE, "legacy", "views.json")
NAV_OUT = os.path.join(FE, "legacy", "nav.json")
EXTRAS_OUT = os.path.join(FE, "legacy", "extras.json")


def main() -> int:
    sys.path.insert(0, IFACE)

    def _src(name: str) -> str:
        return open(os.path.join(IFACE, name)).read()

    ns = {"IFACE": IFACE, "_src": _src, "__name__": "__interface__"}
    exec(compile(_src("build.py"), os.path.join(IFACE, "build.py"), "exec"), ns)

    css = ns["PARTS"]["css"]

    # Each view's markup, keyed the way the nav refers to it.
    views = {k: v for k, v in ns["VIEWS"].items()}
    views["denied"] = (
        '<div class="denied"><div class="big">⛔</div>'
        "<h4>Not available to your role</h4><p>You are signed in as a role that has "
        "not been granted this area. Nothing is hidden on the screen — the "
        "figures were never fetched.</p></div>"
    )

    nav = {
        "groups": [
            {
                "label": gname,
                "items": [
                    {
                        "key": it[0],
                        "label": it[1],
                        "badge": it[2] if len(it) == 4 else "",
                        "roles": it[3] if len(it) == 4 else it[2],
                        "sub": gname == "Areas of the business",
                    }
                    for it in items
                ],
            }
            for gname, items in ns["NAVGROUPS"]
        ]
    }

    extras = {
        "drawers": ns["DR"],
        "explainers": ns["EXH"],
        "drill": ns["DRH"],
        "brain": ns["BRAIN"],
        # Each swatch is a split disc of its light and dark accent. The
        # generated markup carried that gradient inline; the component needs the
        # same two colours or every swatch renders as an empty circle.
        "accents": [
            {"key": k, "label": lab, "group": g, "light": li, "dark": dk, "note": n}
            for k, lab, g, li, dk, n in ns["ACCENTS"]
        ],
    }

    for path, content in (
        (CSS_OUT, css),
        (VIEWS_OUT, json.dumps(views, indent=0)),
        (NAV_OUT, json.dumps(nav, indent=1)),
        (EXTRAS_OUT, json.dumps(extras, indent=0)),
    ):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        print(f"  {len(content):>9,} bytes  {os.path.relpath(path, ROOT)}")

    print(f"\n  {len(views)} views, {len(extras['drawers'])} drawers, "
          f"{len(extras['explainers'])} explainers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
