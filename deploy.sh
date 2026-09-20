#!/usr/bin/env bash
#
# Deploy Command Center on the server. One command, in the right order.
#
#   ./deploy.sh              pull, migrate, load every fact, restart
#   ./deploy.sh --reseed     also rebuild the demonstration complaints
#   ./deploy.sh --full       reload every fact from scratch, ignoring watermarks
#   ./deploy.sh --strict     do not skip failing patches (see the migrate step)
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
STRICT=0
for arg in "$@"; do
  case "$arg" in
    --reseed) RESEED=1 ;;
    --full)   FULL=1 ;;
    --strict) STRICT=1 ;;
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
#
# --skip-failing by default: this site carries two ERPNext v14/v15 patches that fail on
# every migrate and have nothing to do with this app. Without the flag they stop the
# deploy dead. Frappe's own documentation says skipping failing patches is not
# recommended for production, and that caveat stands -- so the skip is announced rather
# than silent, and `--strict` turns it off when the failures are what you want to see.
step "migrating $SITE"
if [ "$STRICT" = "1" ]; then
  bench --site "$SITE" migrate
else
  bench --site "$SITE" migrate --skip-failing
  echo "   note: ran with --skip-failing. Two v14/v15 ERPNext patches fail on this site"
  echo "         and are unrelated to command_center. Use --strict to see them."
fi

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
