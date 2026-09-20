#!/usr/bin/env bash
# Commits the apps-tile routing fix and pushes. Self-deleting.
set -e
cd "$(dirname "$0")"

rm -f .git/index.lock .git/HEAD.lock .git/objects/maintenance.lock
find .git/objects -name 'tmp_obj_*' -delete 2>/dev/null || true

python3 scripts/preflight.py

git add -A ':!.push-4.sh'
git commit -q -F - <<'MSG'
apps screen: set app_home, and build the workspace the way v16 expects

The tile did not appear. frappe/boot.py builds each app's app_route from the
`app_home` hook, falling back to the first permitted workspace, and finally to an
empty string. The `route` key inside add_to_apps_screen is never read for the tile
-- only the sidebar switcher uses it. With no app_home and no workspace, the route
was empty and the tile had nowhere to go.

Two causes, then:

  - app_home was not set. It is now "/command-center".
  - The workspace was never created. desk.py assigned `name` on a new document,
    which fights Workspace's autoname (field:label), and wrote `public` through
    update() although it is a read_only field. Neither is set that way now:
    the label names the document, and public is written after the insert.

Verified against the v16 source rather than inferred -- boot.py and
workspace.json -- after confirming on the site that every child table and the
content blocks are accepted exactly as this code builds them.

/command-center now redirects a permitted user to the desk workspace until the
interface is built, and keeps sending everyone else to /management-only. Routing
the tile through the guard rather than straight at the workspace is deliberate:
non-managers get our page rather than Frappe's generic refusal.

The patch that builds the desk views no longer fails invisibly. It printed
nothing and logged nothing the first time, so a workspace that never appeared
left no trace at all; it now prints the traceback into the migrate output as well
as logging it, and commits that log.
MSG

git push -q
echo "pushed: $(git log --oneline | head -1)"
echo
echo "On the server:"
echo "  cd ~/frappe-bench-16/apps/command_center && git pull"
echo "  cd ~/frappe-bench-16"
echo "  bench --site biomed.ultrasoft-systems.com migrate"
echo "  bench build --app command_center"
echo "  bench --site biomed.ultrasoft-systems.com clear-cache"
echo "  bench restart"

rm -- "$0"
