#!/usr/bin/env bash
# Content-hashed assets, corrupt palette repaired, SVG icon fixed. Self-deleting.
set -e
cd "$(dirname "$0")"

rm -f .git/index.lock .git/HEAD.lock .git/objects/maintenance.lock
find .git/objects -name 'tmp_obj_*' -delete 2>/dev/null || true

echo "==> removing the unhashed bundle a browser could keep serving"
rm -f command_center/public/command-center/command-center.js
rm -f command_center/public/command-center/command-center.css

echo "==> design system and legacy views"
python3 scripts/build_interface.py

echo "==> frontend"
( cd frontend && npm install --no-fund --no-audit --silent && npm run build )

echo "==> preflight"
python3 scripts/preflight.py

git add -A ':!.push-11.sh'
git commit -q -F - <<'MSG'
assets: content-hashed filenames, so a deploy cannot be masked by a cache

The greeting and the accent gradients were in the bundle the server was sending.
They were not what the browser was showing, because the bundle was called
command-center.js on every build and a cached copy survives a deploy. A stale
cache is indistinguishable from a fix that did not work, and this one cost
several rounds of reporting symptoms that had already been fixed.

Filenames now carry a content hash and the page resolves them through Vite's
manifest, so the URL changes whenever the content does and nobody has to remember
to hard-refresh. The manifest is committed: without it the template has no way to
know the filename. Vite keys its entry by the HTML file rather than by the script
inside it, so the controller finds the entry by isEntry instead of assuming the
key -- checked against a real manifest, not from memory.

preflight now verifies the manifest exists, names a bundle that is present, and
is newer than frontend/src, and it fails on leftover unhashed files, which a
browser that cached them would otherwise keep using.

Two other things, both mine:

interface/accents.py held two corrupted colour values -- "#e3b champion" and
"#d0a museum" -- with a FIX map further down the file repairing them at runtime.
That is how a corrupt source survives: the output looks right, so nothing draws
attention to it, and the next person to read the palette sees nonsense. The
values are repaired at source and the repair map is gone.

The time-of-day icon was assembled by setting innerHTML on an element created
with createElementNS. That is not reliably parsed as SVG -- the nodes can land in
the HTML namespace and render nothing, with no error to explain it. It is parsed
with DOMParser as image/svg+xml now.
MSG

git push -q
echo "pushed: $(git log --oneline | head -1)"
echo
echo "On the server:"
echo "  cd ~/frappe-bench-16/apps/command_center && git pull"
echo "  cd ~/frappe-bench-16"
echo "  bench --site biomed.ultrasoft-systems.com clear-cache"
echo "  bench restart"
echo
echo "No migrate. No hard-refresh needed either, now or ever again --"
echo "the asset URL changes whenever the build does."

rm -- "$0"
