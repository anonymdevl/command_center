#!/usr/bin/env bash
# Tiles, chevron alignment, theme glyph, banner spacing. Self-deleting.
set -e
cd "$(dirname "$0")"

rm -f .git/index.lock .git/HEAD.lock .git/objects/maintenance.lock
find .git/objects -name 'tmp_obj_*' -delete 2>/dev/null || true

python3 scripts/build_interface.py
( cd frontend && npm install --no-fund --no-audit --silent && npm run build )
python3 scripts/preflight.py

git add -A ':!.push-14.sh'
git commit -q -F - <<'MSG'
cards: the same contract on every tile, on every screen

Four things, each applied everywhere rather than where it was noticed.

My day, Work handed out, Control Health, The whole business and Risk and
compliance were untouched by the card work because they do not use .kpi cards at
all -- they use .bk tiles, and there are twenty-five hand-written .bk sites with
no shared function. kpi() at least existed twice; this had no single definition
to fix.

Rewriting all twenty-five by hand would be a large edit of markup that components
will replace anyway, so the contract is applied once to whatever the generators
produce. Control Health nearly escaped again: its six questions are class="bk q",
and the first pattern only matched the bare class, so that screen stayed behind a
second time. 102 of 102 tiles across all fifteen screens now carry the
affordance.

The chevron sat at bottom:7px, below the footnote instead of beside it. The
footnote box is 26px tall and ends 15px above the card's lower edge, so its text
centres at about 22.5px and a 13px glyph starts at 16px. Both tile types use the
same rule, and the footnote gains right padding so long text does not run under
the arrow. .bk already uses ::after for the hairline on tiles with no footnote,
so its chevron is on ::before.

The appearance button was the character U+25D1, which renders as a missing-glyph
box in any font that lacks it -- which is what it had become. It is drawn as an
SVG half-disc now, so it does not depend on what is installed.

And the illustrative banner sat directly on the greeting; it now has space below
it.
MSG

git push -q
echo "pushed: $(git log --oneline | head -1)"
echo
echo "On the server:"
echo "  cd ~/frappe-bench-16/apps/command_center && git pull"
echo "  cd ~/frappe-bench-16"
echo "  bench --site biomed.ultrasoft-systems.com clear-cache && bench restart"

rm -- "$0"
