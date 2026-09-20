#!/usr/bin/env python3
"""Build the Command Center interface into the app.

    python3 scripts/build_interface.py

The interface is generated, not hand-edited. `interface/` holds the generators
that produced the design we agreed; this script runs them and splits the result
into three files the app serves:

    command_center/public/css/command-center.css
    command_center/public/js/command-center.js
    command_center/www/command-center.html

Editing the generated files directly is how the two copies drift, and it has
already cost one rebuild on this project. Change `interface/`, run this, commit
both.

No build toolchain: the interface is vanilla HTML, CSS and JavaScript, so there
is no Vite, no npm and nothing for `bench build` to compile. Files under
`public/` are served through the assets symlink the moment they exist.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IFACE = os.path.join(ROOT, "interface")
APP = os.path.join(ROOT, "command_center")

CSS_OUT = os.path.join(APP, "public", "css", "command-center.css")
JS_OUT = os.path.join(APP, "public", "js", "command-center.js")
WWW_OUT = os.path.join(APP, "www", "command-center.html")

PAGE = """{%- raw -%}
<!DOCTYPE html>
<html lang="en" data-theme="dark" data-accent="petrol" data-signal="muted">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Intelligent Command Center</title>
<link rel="icon" href="/assets/command_center/images/command-center.svg">
<link rel="stylesheet" href="/assets/command_center/css/command-center.css?v=__V__">
</head>
<body>
__BODY__
{%- endraw -%}
<script>window.CC_BOOT = {{ boot }};</script>
{%- raw -%}
<script src="/assets/command_center/js/command-center.js?v=__V__"></script>
</body>
</html>
{%- endraw -%}
"""


def main() -> int:
    sys.path.insert(0, IFACE)

    def _src(name: str) -> str:
        return open(os.path.join(IFACE, name)).read()

    ns = {"IFACE": IFACE, "_src": _src, "__name__": "__interface__"}
    exec(compile(_src("build.py"), os.path.join(IFACE, "build.py"), "exec"), ns)

    parts = ns["PARTS"]
    css, body, js = parts["css"], parts["body"], parts["js"]

    # A cache-buster so a manager does not have to hard-refresh after a deploy.
    version = str(abs(hash(css + body + js)))[:10]

    for path, content in (
        (CSS_OUT, css),
        (JS_OUT, js),
        (WWW_OUT, PAGE.replace("__BODY__", body).replace("__V__", version)),
    ):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        rel = os.path.relpath(path, ROOT)
        print(f"  {len(content):>9,} bytes  {rel}")

    print(f"\n  version {version}")
    print("  views:", body.count('class="view"'))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
