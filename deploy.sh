#!/usr/bin/env bash
#
# Deploy Command Center on the server. One command, in the right order.
#
#   ./deploy.sh              pull, migrate, load every fact, restart
#   ./deploy.sh --reseed     also rebuild the demonstration complaints
#   ./deploy.sh --full       reload every fact from scratch, ignoring watermarks
#
# This exists because deploying was a list of bench commands pasted one at a time,
# which is a sequence that can be got wrong: the order matters (migrate before
# ingest, restart last), a multi-line paste loses its first character, and "did I
# need migrate this time?" is not a question anyone should have to answer.
#
# Run it from the app directory on the server:
#   cd ~/frappe-bench-16/apps/command_center && ./deploy.sh
set -euo pipefail

SITE="${CC_SITE:-biomed.ultrasoft-systems.com}"
RESEED=0
FULL=0
for arg in "$@"; do
  case "$arg" in
    --reseed) RESEED=1 ;;
    --full)   FULL=1 ;;
    --site=*) SITE="${arg#--site=}" ;;
    -h|--help) sed -n '3,12p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
BENCH_DIR="$(cd "$APP_DIR/../.." && pwd)"

step() { printf '\n== %s\n' "$1"; }

step "pulling $APP_DIR"
git -C "$APP_DIR" pull --ff-only

cd "$BENCH_DIR"

# Always. It is idempotent, and it is the step whose absence produces a missing-table
# error twenty minutes later rather than now.
step "migrating $SITE"
bench --site "$SITE" migrate

if [ "$RESEED" = "1" ]; then
  step "rebuilding the demonstration complaints"
  bench --site "$SITE" execute command_center.demo.seed.reseed
  # Reseeding deletes documents, and an incremental load would leave their fact rows
  # behind to be counted forever. A full rebuild is the only correct follow-up.
  FULL=1
fi

step "loading facts$([ "$FULL" = 1 ] && echo ' (full rebuild)')"
if [ "$FULL" = "1" ]; then
  bench --site "$SITE" execute command_center.api.ingest.run --kwargs "{'full': True}"
else
  bench --site "$SITE" execute command_center.api.ingest.run
fi

step "what the figures now rest on"
bench --site "$SITE" execute command_center.api.ingest.status

step "checking the figures against each other"
bench --site "$SITE" execute command_center.api.kpi.verify

# Last, so nothing serves a half-updated app.
step "clearing cache and restarting"
bench --site "$SITE" clear-cache
bench restart

printf '\n== done. %s/command-center\n' "https://$SITE"
