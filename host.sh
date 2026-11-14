#!/usr/bin/env bash
#
# Set up the hosted service: a site on this bench that Gigmann's businesses' ERPNext
# sites plug into over their API. Run once per hosted site; safe to run again (each
# step checks before it acts). After this, deploys are ./deploy.sh --site=<site>.
#
#   cd ~/frappe-bench-16/apps/command_center && ./host.sh biomed.ultrasoft-systems.com
#
# Biomed is the hosted site (Michael, 14 Nov 2026): the app is already installed there,
# and registering "Gigmann Medical Supplies Ltd" switches its record from Biomed's own
# 2025 copy of their data to their live ERPNext, keeping the business's conversations,
# alerts and schedules. A new site name works too; the site is then created.
#
# It asks for what it needs as it goes -- the site's administrator password (bench
# asks), the Anthropic API key, and for each business its ERPNext URL and the API key
# and secret of a read-only user there. Secrets are read without echo and handed over
# in the environment, so they never appear in the shell history or a command line.
#
# Nothing is installed on a business's own ERPNext. The only change there is the
# read-only API user its administrator creates, and (optionally) an "Ask AI" link on
# their workspace -- configuration, made in their desk.
set -euo pipefail

SITE="${1:-}"
if [ -z "$SITE" ]; then
  echo "Usage: ./host.sh <site>   e.g. ./host.sh intelligence.ultrasoft-systems.com" >&2
  exit 2
fi
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
BENCH_DIR="$(cd "$APP_DIR/../.." && pwd)"
step() { printf '\n== %s\n' "$1"; }
ask() { local p="$1" d="${2:-}" v; read -r -p "   $p${d:+ [$d]}: " v; echo "${v:-$d}"; }
secret() { local p="$1" v; read -r -s -p "   $p: " v; echo >&2; echo "$v"; }

cd "$BENCH_DIR"

step "this bench"
echo "   $(bench version 2>/dev/null | tr '\n' ' ')"
git -C "$APP_DIR" pull --ff-only
echo "   command_center at $(git -C "$APP_DIR" log -1 --format='%h %s')"

step "the anthropic package"
if ! "$BENCH_DIR/env/bin/python" -c "import anthropic" 2>/dev/null; then
  "$BENCH_DIR/env/bin/pip" install -q "anthropic>=0.125"
fi
echo "   anthropic $("$BENCH_DIR/env/bin/python" -c 'import anthropic; print(anthropic.__version__)')"

step "the site $SITE"
EXISTED=0
if [ -d "$BENCH_DIR/sites/$SITE" ]; then
  EXISTED=1
  echo "   exists -- reused (nothing on it is removed)"
else
  echo "   creating it (bench asks for the MariaDB root password and the Administrator password)"
  bench new-site "$SITE"
fi
if ! bench --site "$SITE" list-apps 2>/dev/null | grep -q '^command_center'; then
  bench --site "$SITE" install-app command_center
fi
bench --site "$SITE" migrate
bench --site "$SITE" execute command_center.install.prepare_hosted_site
bench --site "$SITE" enable-scheduler
bench --site "$SITE" set-config command_center_ai_provider claude

step "Claude"
if bench --site "$SITE" show-config 2>/dev/null | grep -q "command_center_anthropic_key"; then
  echo "   an Anthropic key is already set (enter a new one to replace it, or leave blank)"
fi
CC_ANTHROPIC_KEY="$(secret 'Anthropic API key (sk-ant-..., blank to keep)')"
if [ -n "$CC_ANTHROPIC_KEY" ]; then
  CC_ANTHROPIC_KEY="$CC_ANTHROPIC_KEY" bench --site "$SITE" execute \
    command_center.install.set_secret_from_env \
    --kwargs "{'key': 'command_center_anthropic_key', 'env': 'CC_ANTHROPIC_KEY'}"
fi
unset CC_ANTHROPIC_KEY

step "connected businesses"
while true; do
  more="$(ask 'Register a business? (y/n)' y)"
  [ "$more" = "y" ] || break
  export CC_BUSINESS_NAME CC_SITE_URL CC_API_KEY CC_API_SECRET CC_COMPANY \
    CC_SSO_CLIENT_ID CC_SSO_CLIENT_SECRET
  CC_BUSINESS_NAME="$(ask 'Business name' 'Gigmann Medical Supplies Ltd')"
  CC_SITE_URL="$(ask 'Its ERPNext URL' 'https://gigmann.powersoftsystem.com')"
  CC_COMPANY="$(ask 'Its ERPNext company (blank: read from the site)' '')"
  CC_API_KEY="$(ask 'API key of its read-only user' '')"
  CC_API_SECRET="$(secret 'API secret of its read-only user')"
  echo "   Sign-in with that ERPNext (blank to set up later). Its OAuth Client must have the"
  echo "   redirect URI https://$SITE/api/method/command_center.api.sso.callback"
  CC_SSO_CLIENT_ID="$(ask 'OAuth Client ID' '')"
  CC_SSO_CLIENT_SECRET=""
  if [ -n "$CC_SSO_CLIENT_ID" ]; then
    CC_SSO_CLIENT_SECRET="$(secret 'OAuth Client Secret')"
  fi
  bench --site "$SITE" execute command_center.install.register_from_env
  unset CC_API_SECRET CC_API_KEY CC_SSO_CLIENT_SECRET
  echo "   what that user may read, and whether it is read-only:"
  bench --site "$SITE" execute command_center.api.ingest.check_access
done

step "managers"
while true; do
  more="$(ask 'Add a manager who may sign in? (y/n)' n)"
  [ "$more" = "y" ] || break
  email="$(ask 'Their email' '')"
  name="$(ask 'Their full name' '')"
  bench --site "$SITE" execute command_center.install.add_manager \
    --kwargs "{'email': '$email', 'full_name': '$name'}"
done

step "first load (every fact of every business, from scratch -- several minutes)"
bench --site "$SITE" execute command_center.api.ingest.run_all --kwargs "{'full': True}"

step "what the figures now rest on"
bench --site "$SITE" execute command_center.api.ingest.status

step "checking the figures against each other"
bench --site "$SITE" execute command_center.api.kpi.verify

step "checking Claude (two short requests: the second must read the cache)"
bench --site "$SITE" execute command_center.api.ask.check_analyst || true

step "web server"
if [ "$EXISTED" = "1" ]; then NGINX_DEFAULT=n; else NGINX_DEFAULT=y; fi
if [ "$(ask 'Set up nginx for the site now? Needs sudo, and DNS already pointing here (y/n)' "$NGINX_DEFAULT")" = "y" ]; then
  bench setup nginx --yes
  sudo service nginx reload
  if [ "$(ask 'Issue its HTTPS certificate with Lets Encrypt now? (y/n)' y)" = "y" ]; then
    sudo -H bench setup lets-encrypt "$SITE"
  fi
fi

step "clearing cache and restarting"
bench --site "$SITE" clear-cache
bench restart

printf '\n== done. https://%s/command-center\n' "$SITE"
echo "   The Ask AI link for each business's ERPNext workspace:"
bench --site "$SITE" execute command_center.install.sign_in_links || true
echo "   From now on: ./deploy.sh --site=$SITE"
