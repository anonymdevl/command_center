#!/usr/bin/env bash
#
# Put the platform on its own address with HTTPS. Safe to run again.
#
#   cd ~/insights-platform && ./deploy/domain.sh insights.example.com [you@example.com]
#
# The name's DNS must already point at this server. It:
#   1. adds an nginx site for that name only (/etc/nginx/conf.d/zz-insights-<name>.conf),
#      leaving every other site on this server -- Frappe benches included -- alone. It
#      records how every other site answers before, checks again after, and takes its
#      own site out again if any of them changed;
#   2. gets a Let's Encrypt certificate (certbot, webroot; renews on its own and reloads
#      nginx);
#   3. switches the site to HTTPS (http redirects to https);
#   4. tells the platform its address (allowed hosts, trusted origins, secure cookies,
#      host_name for links in emails) and restarts it.
# The SSH tunnel keeps working as a way in.
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
[ -n "$DOMAIN" ] || { echo "usage: $0 <domain> [email for certificate notices]" >&2; exit 1; }
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${INSIGHTS_PORT:-8200}"
CONFIG="$DIR/insights.json"
PY="$DIR/.venv-platform/bin/python"
# "zz-": nginx sends a request that matches no site name to the first site it loaded
# on that port (unless one is marked default_server). Loading last, this one can never
# become that fallback for the server's other sites.
CONF="/etc/nginx/conf.d/zz-insights-$DOMAIN.conf"
WEBROOT="/var/www/insights-acme"
CERT="/etc/letsencrypt/live/$DOMAIN"
step() { printf '\n== %s\n' "$1"; }

[ -f "$CONFIG" ] || { echo "run ./deploy/platform.sh first (no insights.json yet)" >&2; exit 1; }
command -v nginx >/dev/null || { echo "nginx is not installed on this server" >&2; exit 1; }
command -v certbot >/dev/null || { echo "certbot is missing: sudo apt install certbot" >&2; exit 1; }

step "DNS"
HERE="$(curl -4 -s -m 10 https://api.ipify.org || true)"
THERE="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}')"
echo "   $DOMAIN -> ${THERE:-nothing}; this server -> ${HERE:-unknown}"
if [ -z "$THERE" ]; then echo "   $DOMAIN does not resolve yet" >&2; exit 1; fi
if [ -n "$HERE" ] && [ "$HERE" != "$THERE" ]; then
  echo "   $DOMAIN points elsewhere; the certificate would fail" >&2; exit 1
fi

# Every other site nginx serves here, by name, and how each answers (http and https,
# asked of this server directly). Taken before the change and compared after it.
other_sites() {
  # A server_name's names may run over several lines up to its ";" (Frappe writes them
  # one per line), so names are collected until the semicolon.
  sudo nginx -T 2>/dev/null | awk '
    { sub(/#.*/, "")
      for (i = 1; i <= NF; i++) {
        n = $i
        if (!on) { if (n == "server_name") on = 1; continue }
        e = (n ~ /;/); sub(/;.*/, "", n); if (n != "") print n; if (e) on = 0 } }' \
    | grep -vE '^(_|localhost|~.*|.*\*.*|[0-9.]+|'"${DOMAIN//./\\.}"')$' | sort -u || true
}
answers() {
  local n h s
  for n in $(other_sites); do
    h="$(curl -s -o /dev/null -m 10 -w '%{http_code}' --resolve "$n:80:127.0.0.1" "http://$n/" || true)"
    s="$(curl -sk -o /dev/null -m 10 -w '%{http_code}' --resolve "$n:443:127.0.0.1" "https://$n/" || true)"
    echo "$n $h $s"
  done
}
ok() { case "$1" in 2??|3??|401|403|404) return 0;; *) return 1;; esac; }

step "the server's other sites, before"
BEFORE="$(answers)"
echo "$BEFORE" | awk 'NF{printf "   %-45s http %s  https %s\n", $1, $2, $3}'
[ -n "$BEFORE" ] || echo "   (no other named sites found)"

# The site's locations, shared by the http (before a certificate) and https versions.
locations() {
  cat <<NGX
    client_max_body_size 20m;

    location /assets/command_center/ {
        alias $DIR/command_center/public/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }
    location /static/ {
        alias $DIR/staticfiles/;
        expires 30d;
    }
    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        # A deeper look can take minutes; Claude's answers stream for up to 150 s.
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
NGX
}
acme() {
  cat <<NGX
    location /.well-known/acme-challenge/ { root $WEBROOT; }
NGX
}
# Write the site; if nginx rejects it, put back what was there before (or nothing).
install_conf() {
  local backup=""
  if sudo test -f "$CONF"; then backup="$(mktemp)"; sudo cp "$CONF" "$backup"; fi
  sudo tee "$CONF" >/dev/null
  if ! sudo nginx -t 2>"$DIR/.nginx-test.log"; then
    cat "$DIR/.nginx-test.log" >&2
    if [ -n "$backup" ]; then sudo cp "$backup" "$CONF"; else sudo rm -f "$CONF"; fi
    echo "   nginx rejected the new site; the previous one is back, nothing else changed" >&2
    exit 1
  fi
  rm -f "$DIR/.nginx-test.log" ${backup:+"$backup"}
  sudo systemctl reload nginx
}

if ! sudo test -f "$CERT/fullchain.pem"; then
  step "nginx (http, to prove the name for the certificate)"
  sudo mkdir -p "$WEBROOT"
  { echo "server {"; echo "    listen 80;"; echo "    server_name $DOMAIN;"; acme; locations; echo "}"; } \
    | install_conf
  echo "   $CONF"

  step "certificate"
  if [ -n "$EMAIL" ]; then WHO=(--email "$EMAIL"); else WHO=(--register-unsafely-without-email); fi
  sudo certbot certonly --webroot -w "$WEBROOT" -d "$DOMAIN" --non-interactive --agree-tos \
    "${WHO[@]}" --deploy-hook "systemctl reload nginx"
fi

step "nginx (https)"
{
  echo "server {"
  echo "    listen 80;"
  echo "    server_name $DOMAIN;"
  acme
  echo "    location / { return 301 https://\$host\$request_uri; }"
  echo "}"
  echo "server {"
  # Plain "listen 443 ssl": options such as http2 on a listen line apply to every
  # site on that port, so none are set here; TLS settings are the server's own.
  echo "    listen 443 ssl;"
  echo "    server_name $DOMAIN;"
  echo "    ssl_certificate $CERT/fullchain.pem;"
  echo "    ssl_certificate_key $CERT/privkey.pem;"
  echo "    add_header Strict-Transport-Security \"max-age=31536000\" always;"
  locations
  echo "}"
} | install_conf
echo "   $CONF"

step "the server's other sites, after"
AFTER="$(answers)"
CHANGED=""
while read -r n h s; do
  [ -n "$n" ] || continue
  read -r _ h2 s2 <<<"$(echo "$AFTER" | awk -v n="$n" '$1==n')"
  mark="same"
  if { ok "$h" && ! ok "${h2:-000}"; } || { ok "$s" && ! ok "${s2:-000}"; }; then
    mark="CHANGED"; CHANGED="$CHANGED $n"
  elif [ "$h" != "${h2:-}" ] || [ "$s" != "${s2:-}" ]; then
    mark="different code, still answering"
  fi
  printf "   %-45s http %s -> %s  https %s -> %s  %s\n" "$n" "$h" "${h2:-?}" "$s" "${s2:-?}" "$mark"
done <<<"$BEFORE"
if [ -n "$CHANGED" ]; then
  echo "   a site that answered before no longer does:$CHANGED" >&2
  echo "   taking the platform's nginx site out again" >&2
  sudo rm -f "$CONF" && sudo nginx -t && sudo systemctl reload nginx
  exit 1
fi
echo "   every other site answers as before"

step "the platform's address"
CONFIG="$CONFIG" DOMAIN="$DOMAIN" "$PY" - <<'PYCFG'
import json, os
path, d = os.environ["CONFIG"], os.environ["DOMAIN"]
with open(path) as fh:
    cfg = json.load(fh)
hosts = [h for h in cfg.get("allowed_hosts") or [] if h != d]
cfg["allowed_hosts"] = [d] + hosts + [h for h in ("localhost", "127.0.0.1") if h not in hosts]
origins = [o for o in cfg.get("csrf_trusted_origins") or [] if o != f"https://{d}"]
cfg["csrf_trusted_origins"] = [f"https://{d}"] + origins
cfg["secure_cookies"] = True
cfg["host_name"] = f"https://{d}"
with open(path, "w") as fh:
    json.dump(cfg, fh, indent=1)
os.chmod(path, 0o600)
print(f"   allowed_hosts {cfg['allowed_hosts']}; secure cookies on; host_name {cfg['host_name']}")
PYCFG
sudo systemctl restart insights-web
sleep 2

step "check"
CODE="$(curl -s -o /dev/null -m 15 -w '%{http_code}' "https://$DOMAIN/command-center-login" || true)"
echo "   https://$DOMAIN/command-center-login -> HTTP ${CODE:-no answer}"
[ "$CODE" = "200" ] || echo "   not 200: see sudo journalctl -u insights-web -n 50" >&2

printf '\n== done.\n'
echo "   The platform:    https://$DOMAIN/command-center-login"
echo "   Administration:  https://$DOMAIN/admin/"
