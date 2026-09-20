#!/usr/bin/env bash
# Chevron glyph, footnote clearance, banner width. Self-deleting.
set -e
cd "$(dirname "$0")"

rm -f .git/index.lock .git/HEAD.lock .git/objects/maintenance.lock
find .git/objects -name 'tmp_obj_*' -delete 2>/dev/null || true

python3 scripts/build_interface.py
( cd frontend && npm install --no-fund --no-audit --silent && npm run build )
python3 scripts/preflight.py

git add -A ':!.push-16.sh'
git commit -q -F - <<'MSG'
cards: write the chevron as a character, not a CSS escape

The arrow was `content:"\203a"`. That is a valid escape for U+203A, but the
minifier resolved it as U+0203 followed by a stray "a" -- which is why every card
showed a missing-glyph box and the letter a where the arrow belongs, and why the
footnote looked like it was running into it. Written as the literal character,
the way the original rule did it.

Two rules were also styling the same pseudo-element: the original at bottom:7px
and the new one at bottom:16px. The later won, so the position was right, but
both shipped. Same duplication as .hello and .tod, one file further on. The old
one is removed.

Footnote clearance goes from 15px to 18px.

The illustrative banner carried a 26px horizontal margin while sitting inside
.main, which already insets by 34px -- so it was narrower than the view's own
banners. It has no horizontal margin now and lines up with them.
MSG

git push -q
echo "pushed: $(git log --oneline | head -1)"
echo
echo "On the server:"
echo "  cd ~/frappe-bench-16/apps/command_center && git pull"
echo "  cd ~/frappe-bench-16"
echo "  bench --site biomed.ultrasoft-systems.com clear-cache && bench restart"

rm -- "$0"
