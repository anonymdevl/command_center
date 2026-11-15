#!/usr/bin/env bash
#
# Install or update the standalone platform on this server. Safe to run again.
#
#   cd ~/insights-platform && ./deploy/platform.sh
#
# First run (no insights.json yet): creates its own MariaDB database and user, writes
# the configuration with new keys, creates the tables, asks for your administrator
# account, the Anthropic key and the first business, runs the first full load, and
# installs two systemd services (web on 127.0.0.1:PORT, and the scheduler).
# Later runs: pull, install, migrate, restart; they ask only for what a first run left
# unfinished (no administrator yet, no Claude key, no business).
#
# It never touches a Frappe bench or site. Secrets are read without echo and passed in
# the environment, never on a command line.
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${INSIGHTS_PORT:-8200}"
CONFIG="$DIR/insights.json"
PY="$DIR/.venv-platform/bin/python"
cd "$DIR"
step() { printf '\n== %s\n' "$1"; }
ask() { local p="$1" d="${2:-}" v; read -r -p "   $p${d:+ [$d]}: " v; echo "${v:-$d}"; }
secret() { local p="$1" v; read -r -s -p "   $p: " v; echo >&2; echo "$v"; }
export INSIGHTS_CONFIG="$CONFIG" DJANGO_SETTINGS_MODULE=insights.settings

# Bash reads a script as it runs, so a pull that changes this file must not be followed
# by reading the rest of it: the whole update is one function (read in full before it
# runs) that starts the new script afresh when the code changed.
update_code() {
  local before; before="$(git rev-parse HEAD)"
  git pull --ff-only || echo "   (not pulled: $(git rev-parse --abbrev-ref HEAD) has local changes)"
  echo "   $(git log -1 --format='%h %s' | cut -c1-90)"
  if [ "$(git rev-parse HEAD)" != "$before" ] && [ -z "${INSIGHTS_UPDATED:-}" ]; then
    echo "   updated: starting the new version of this script"
    INSIGHTS_UPDATED=1 exec "$DIR/deploy/platform.sh" "$@"
  fi
}
step "code"
update_code "$@"

step "python"
if [ ! -x "$PY" ]; then
  BASE=""
  for c in python3.12 python3.13 python3.11; do
    if command -v "$c" >/dev/null 2>&1; then BASE="$(command -v "$c")"; break; fi
  done
  if [ -z "$BASE" ] && command -v uv >/dev/null 2>&1; then
    uv python install 3.12 >/dev/null 2>&1 || true
    BASE="$(uv python find 3.12)"
  fi
  [ -n "$BASE" ] || { echo "   need Python 3.11-3.13 (or uv) on this server" >&2; exit 1; }
  "$BASE" -m venv "$DIR/.venv-platform"
fi
"$DIR/.venv-platform/bin/pip" install -q --upgrade pip
"$DIR/.venv-platform/bin/pip" install -q -r requirements-platform.txt
echo "   $("$PY" -c 'import sys,django; print("python", sys.version.split()[0], "django", django.get_version())')"

if [ ! -f "$CONFIG" ]; then
  step "database (its own, on this server's MariaDB)"
  DB_NAME="$(ask 'Database name' 'insights')"
  DB_USER="$(ask 'Database user' 'insights')"
  DB_PASS="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(24))')"
  echo "   creating it (MariaDB asks for its root password)"
  mysql -u root -p <<SQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';
ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
SQL
  DB_NAME="$DB_NAME" DB_USER="$DB_USER" DB_PASS="$DB_PASS" PORT="$PORT" "$PY" - <<'PYCFG'
import json, os
cfg = {"db": {"engine": "mysql", "name": os.environ["DB_NAME"], "user": os.environ["DB_USER"],
              "password": os.environ["DB_PASS"], "host": "127.0.0.1", "port": 3306},
       # Reached through an SSH tunnel (http://localhost) until it has a domain with
       # HTTPS; then set allowed_hosts to the domain and secure_cookies to true.
       "allowed_hosts": ["localhost", "127.0.0.1"],
       "csrf_trusted_origins": [f"http://localhost:{os.environ['PORT']}",
                                f"http://127.0.0.1:{os.environ['PORT']}"],
       "secure_cookies": False, "debug": False,
       "command_center_ai_provider": "claude"}
path = os.environ["INSIGHTS_CONFIG"]
with open(path, "w") as fh:
    json.dump(cfg, fh, indent=1)
os.chmod(path, 0o600)
PYCFG
  unset DB_PASS
fi

step "tables, cache, role"
"$PY" manage.py setup
"$PY" manage.py collectstatic --noinput -v 0

# What a first run still has to do, judged from what is there -- so a run that stopped
# part-way (a rejected password, a typo) picks up where it left off when run again.
read -r HAS_ADMIN HAS_BUSINESS <<<"$("$PY" - <<'PYSTATE'
import django; django.setup()
from django.contrib.auth import get_user_model
from insights.core.models import ConnectedBusiness
print(int(get_user_model().objects.filter(is_superuser=True, is_active=True).exists()),
      int(ConnectedBusiness.objects.exists()))
PYSTATE
)"
HAS_KEY=0
grep -q '"command_center_anthropic_key"' "$CONFIG" && HAS_KEY=1

if [ "$HAS_ADMIN" = "0" ]; then
  step "your administrator account"
  ADMIN="$(ask 'Your email (you sign in with it)' '')"
  "$PY" manage.py add_manager "$ADMIN" "$(ask 'Your full name' '')" --admin
fi

if [ "$HAS_KEY" = "0" ]; then
  step "Claude"
  CC_KEY="$(secret 'Anthropic API key (sk-ant-..., blank to set later)')"
  if [ -n "$CC_KEY" ]; then
    CC_KEY="$CC_KEY" "$PY" - <<'PYKEY'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "insights.settings")
import django; django.setup()
import frappe
frappe.installer.update_site_config("command_center_anthropic_key", os.environ["CC_KEY"])
print("   key stored in insights.json")
PYKEY
  fi
  unset CC_KEY
fi

if [ "$HAS_BUSINESS" = "0" ]; then
  step "the first business"
  if [ "$(ask 'Connect a business now? (y/n)' y)" = "y" ]; then
    "$PY" manage.py register_business
    step "first full load (several minutes)"
    "$PY" manage.py execute command_center.api.ingest.run_all --kwargs '{"full": true}'
    "$PY" manage.py execute command_center.api.kpi.verify
  fi
fi

step "services"
for unit in insights-web insights-scheduler; do
  sed -e "s#__USER__#$(id -un)#g" -e "s#__DIR__#$DIR#g" -e "s#__PORT__#$PORT#g" \
    "deploy/$unit.service" | sudo tee "/etc/systemd/system/$unit.service" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable --now insights-web insights-scheduler >/dev/null
sudo systemctl restart insights-web insights-scheduler
sleep 2
systemctl --no-pager --lines=0 status insights-web insights-scheduler | grep -E "Active|●" || true

if [ -f "$CONFIG" ] && grep -q command_center_anthropic_key "$CONFIG"; then
  step "checking Claude"
  "$PY" manage.py execute command_center.api.ask.check_analyst || true
fi

printf '\n== done.\n'
echo "   Open it from your own computer through a tunnel (nothing is exposed publicly):"
echo "     ssh -L $PORT:127.0.0.1:$PORT $(id -un)@<this server>"
echo "     then http://localhost:$PORT/command-center-login"
echo "   Administration (businesses, people, error log): http://localhost:$PORT/admin/"
echo "   With a domain: ./deploy/domain.sh <domain> <your email> (nginx + HTTPS)."
