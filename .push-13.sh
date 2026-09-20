#!/usr/bin/env bash
# Diagnostics must resolve hashed filenames too. Self-deleting.
set -e
cd "$(dirname "$0")"

rm -f .git/index.lock .git/HEAD.lock .git/objects/maintenance.lock
find .git/objects -name 'tmp_obj_*' -delete 2>/dev/null || true

python3 scripts/build_interface.py
( cd frontend && npm install --no-fund --no-audit --silent && npm run build )
python3 scripts/preflight.py

git add -A ':!.push-13.sh'
git commit -q -F - <<'MSG'
diagnostics: resolve the bundle through the manifest, not by fixed name

deployed() reported the bundle and stylesheet as missing on a perfectly good
deploy. It looked for command-center.js and command-center.css, which content
hashing replaced and the previous commit correctly deleted.

A diagnostic that raises a false alarm is worth less than none: it was written
precisely so we would stop guessing whether a deploy landed, and instead it would
have sent us looking for a problem that did not exist. It now reads Vite's
manifest, the same way the page does, so it reports the files actually being
served.

contains() resolves the same way.
MSG

git push -q
echo "pushed: $(git log --oneline | head -1)"
echo
echo "On the server:"
echo "  cd ~/frappe-bench-16/apps/command_center && git pull"
echo "  cd ~/frappe-bench-16"
echo "  bench --site biomed.ultrasoft-systems.com clear-cache && bench restart"

rm -- "$0"
