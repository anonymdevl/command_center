#!/usr/bin/env bash
#
# A health report for this server and the platform. Reads only: it changes nothing,
# restarts nothing, installs nothing.
#
#   cd ~/insights-platform && ./deploy/health.sh            # the report
#   ./deploy/health.sh --backup                            # and test tonight's backup now
#
# Each line is OK, WARN (worth fixing soon) or BAD (fix now); the warnings are repeated
# at the end. sudo is asked for once, to read what only root can (nginx config,
# certificates, the kernel log).

DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$DIR/.venv-platform/bin/python"
CONFIG="$DIR/insights.json"
export INSIGHTS_CONFIG="$CONFIG" DJANGO_SETTINGS_MODULE=insights.settings
ISSUES=()
ok()   { printf '   OK    %s\n' "$*"; }
warn() { printf '   WARN  %s\n' "$*"; ISSUES+=("WARN  $*"); }
bad()  { printf '   BAD   %s\n' "$*"; ISSUES+=("BAD   $*"); }
info() { printf '         %s\n' "$*"; }
step() { printf '\n== %s\n' "$1"; }
pct()  { awk -v a="$1" -v b="$2" 'BEGIN{printf "%d", (b>0)? a*100/b : 0}'; }

sudo -v || { echo "sudo is needed to read the root-only parts" >&2; exit 1; }

step "the machine"
. /etc/os-release 2>/dev/null
info "$(hostname) | ${PRETTY_NAME:-?} | kernel $(uname -r) | up $(uptime -p | sed 's/^up //')"
CPUS="$(nproc)"
read -r L1 L5 L15 _ < /proc/loadavg
info "CPUs $CPUS, load $L1 / $L5 / $L15 (1 / 5 / 15 min)"
if awk -v l="$L15" -v c="$CPUS" 'BEGIN{exit !(l > c)}'; then bad "15-minute load $L15 is above the $CPUS CPUs"
elif awk -v l="$L15" -v c="$CPUS" 'BEGIN{exit !(l > c*0.7)}'; then warn "15-minute load $L15 is near the $CPUS CPUs"
else ok "CPU load"; fi
if [ -f /var/run/reboot-required ]; then
  warn "a reboot is pending (updates installed $(stat -c %y /var/run/reboot-required | cut -d' ' -f1)); plan one at a quiet hour"
else ok "no reboot pending"; fi
UPG="$(apt list --upgradable 2>/dev/null | grep -c upgradable)"
SEC="$(apt list --upgradable 2>/dev/null | grep -c -- '-security')"
if [ "$SEC" -gt 0 ]; then warn "$UPG updates waiting, $SEC of them security"
elif [ "$UPG" -gt 0 ]; then ok "$UPG updates waiting, none security"
else ok "packages up to date"; fi
if systemctl is-enabled unattended-upgrades >/dev/null 2>&1; then ok "automatic security updates on"
else warn "automatic security updates are off (unattended-upgrades)"; fi
if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes; then ok "clock synchronised"
else warn "clock not synchronised (NTP)"; fi

step "memory"
read -r MT MA ST SF < <(awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}/SwapTotal/{st=$2}/SwapFree/{sf=$2}END{print t,a,st,sf}' /proc/meminfo)
info "RAM $((MT/1024)) MB, available $((MA/1024)) MB; swap $((ST/1024)) MB, used $(((ST-SF)/1024)) MB"
U="$(pct $((MT-MA)) "$MT")"
if [ "$U" -ge 90 ]; then bad "RAM ${U}% used"; elif [ "$U" -ge 80 ]; then warn "RAM ${U}% used"; else ok "RAM ${U}% used"; fi
if [ "$ST" -eq 0 ]; then warn "no swap: when memory runs out the kernel kills a process outright"
elif [ "$(pct $((ST-SF)) "$ST")" -ge 50 ]; then warn "swap $(pct $((ST-SF)) "$ST")% used"; else ok "swap"; fi
OOM="$(sudo journalctl -k --since '14 days ago' --no-pager 2>/dev/null | grep -ci 'killed process')"
if [ "$OOM" -gt 0 ]; then bad "$OOM process(es) killed for lack of memory in 14 days"
  sudo journalctl -k --since '14 days ago' --no-pager 2>/dev/null | grep -i 'killed process' | tail -3 | sed 's/^/         /'
else ok "no out-of-memory kills in 14 days"; fi
info "largest by memory:"
ps -eo rss,comm --sort=-rss | awk 'NR>1&&NR<=8{printf "           %6d MB  %s\n", $1/1024, $2}'

step "disk"
while read -r src size used avail usep mnt; do
  p="${usep%\%}"
  line="$mnt: $used of $size used, $avail free"
  if [ "$p" -ge 90 ]; then bad "$line ($usep)"; elif [ "$p" -ge 80 ]; then warn "$line ($usep)"; else ok "$line ($usep)"; fi
done < <(df -hP -x tmpfs -x devtmpfs -x squashfs -x overlay 2>/dev/null | awk 'NR>1')
IP="$(df -iP / | awk 'NR==2{print $5}' | tr -d %)"
if [ "${IP:-0}" -ge 80 ]; then warn "inodes on / ${IP}% used"; else ok "inodes on / ${IP}% used"; fi
JD="$(journalctl --disk-usage 2>/dev/null | grep -oE '[0-9.]+[KMGT]' | head -1)"
info "system journal ${JD:-?}; /var/log $(sudo du -sh /var/log 2>/dev/null | cut -f1)"
for b in "$HOME"/frappe-bench*; do
  [ -d "$b" ] || continue
  info "$(basename "$b"): logs $(du -sh "$b/logs" 2>/dev/null | cut -f1), site backups $(du -shc "$b"/sites/*/private/backups 2>/dev/null | tail -1 | cut -f1)"
done

step "services the sites share"
for s in nginx mariadb mysql redis-server supervisor cron fail2ban; do
  systemctl list-unit-files "$s.service" >/dev/null 2>&1 || continue
  st="$(systemctl is-active "$s" 2>/dev/null)"
  [ "$st" = "inactive" ] && [ "$s" = "mysql" ] && continue
  if [ "$st" = "active" ]; then ok "$s running"; elif [ "$s" = "fail2ban" ]; then warn "fail2ban not running (blocks repeated sign-in attempts over SSH)"; else bad "$s is $st"; fi
done
FAILED="$(systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' | tr '\n' ' ')"
if [ -n "$FAILED" ]; then warn "failed units: $FAILED"; else ok "no failed units"; fi
if sudo nginx -t >/dev/null 2>&1; then ok "nginx configuration valid"; else bad "nginx configuration has errors (sudo nginx -t)"; fi
if command -v supervisorctl >/dev/null; then
  NOTRUN="$(sudo supervisorctl status 2>/dev/null | grep -vc RUNNING)"
  if [ "$NOTRUN" -gt 0 ]; then warn "$NOTRUN supervisor process(es) not running:"
    sudo supervisorctl status 2>/dev/null | grep -v RUNNING | sed 's/^/         /'
  else ok "every supervisor process (bench workers) running"; fi
fi
UFW="$(sudo ufw status 2>/dev/null | head -1)"
info "firewall: ${UFW:-ufw not installed}"
info "listening to the outside: $(sudo ss -Hltn 2>/dev/null | awk '{print $4}' | grep -vE '^(127\.|\[::1\])' | sed -E 's/.*://' | sort -un | tr '\n' ' ')"

step "certificates"
if sudo test -d /etc/letsencrypt/live; then
  for c in $(sudo find /etc/letsencrypt/live -mindepth 2 -name cert.pem 2>/dev/null); do
    n="$(basename "$(dirname "$c")")"
    end="$(sudo openssl x509 -enddate -noout -in "$c" | cut -d= -f2)"
    days=$(( ( $(date -d "$end" +%s) - $(date +%s) ) / 86400 ))
    if [ "$days" -lt 7 ]; then bad "$n expires in $days days"
    elif [ "$days" -lt 20 ]; then warn "$n expires in $days days (renewal should have happened at 30)"
    else ok "$n: $days days left"; fi
  done
  if systemctl is-active certbot.timer >/dev/null 2>&1 || systemctl is-active snap.certbot.renew.timer >/dev/null 2>&1 \
     || sudo test -f /etc/cron.d/certbot; then ok "automatic certificate renewal scheduled"
  else warn "no automatic certificate renewal found (certbot timer or cron)"; fi
else info "no Let's Encrypt certificates on this server"; fi

step "MariaDB"
if [ -f "$CONFIG" ] && [ -x "$PY" ]; then
  "$PY" - <<'PYDB' 2>/dev/null || warn "could not read MariaDB's status"
import django; django.setup()
from django.db import connection
if connection.vendor != "mysql":
    print("         (the platform is on SQLite here)"); raise SystemExit
with connection.cursor() as c:
    c.execute("SHOW GLOBAL STATUS WHERE Variable_name IN ('Uptime','Threads_connected','Max_used_connections','Aborted_connects','Slow_queries')")
    st = dict(c.fetchall())
    c.execute("SHOW GLOBAL VARIABLES WHERE Variable_name IN ('max_connections','innodb_buffer_pool_size','version')")
    va = dict(c.fetchall())
    c.execute("SELECT table_schema, ROUND(SUM(data_length+index_length)/1024/1024) FROM information_schema.tables WHERE table_schema = DATABASE() GROUP BY 1")
    size = c.fetchone()
mx, used = int(va["max_connections"]), int(st["Max_used_connections"])
print(f"         MariaDB {va['version']}, up {int(st['Uptime'])//86400} days; buffer pool {int(va['innodb_buffer_pool_size'])//1024**2} MB")
flag = "WARN " if used >= 0.8 * mx else "OK   "
print(f"   {flag} connections: {st['Threads_connected']} now, peak {used} of {mx} allowed")
print(f"         the platform's database: {size[1] if size else 0} MB")
PYDB
else info "the platform is not installed here"; fi

step "the platform"
for s in insights-web insights-scheduler; do
  st="$(systemctl is-active "$s" 2>/dev/null)"
  r="$(systemctl show -p NRestarts --value "$s" 2>/dev/null)"
  since="$(systemctl show -p ActiveEnterTimestamp --value "$s" 2>/dev/null)"
  if [ "$st" != "active" ]; then bad "$s is $st"
  elif [ "${r:-0}" -gt 3 ]; then warn "$s restarted itself $r times (since $since)"
  else ok "$s running since $since"; fi
done
if [ -f "$CONFIG" ]; then
  [ "$(stat -c %a "$CONFIG")" = "600" ] && ok "insights.json readable by its owner only" \
    || warn "insights.json permissions are $(stat -c %a "$CONFIG"), should be 600"
fi
RAN="$(journalctl -u insights-scheduler --since '24 hours ago' --no-pager 2>/dev/null | grep -c ' ran ')"
info "scheduled jobs run in the last 24 hours: $RAN"
if [ -x "$PY" ] && [ -f "$CONFIG" ]; then
  "$PY" - "$@" <<'PYPLAT' 2>/dev/null || warn "could not read the platform's own state"
import sys, datetime as dt, django; django.setup()
from insights.core.models import ErrorLog, ConnectedBusiness
from insights.core import maintenance
day = dt.datetime.now() - dt.timedelta(days=1)
errs = ErrorLog.objects.using("aux").filter(creation__gte=day)
n = errs.count()
print(f"   {'WARN ' if n > 20 else 'OK   '} {n} error(s) logged in 24 hours")
for t in errs.values_list("title", flat=True).distinct()[:5]:
    print(f"           {t[:90]}")
import frappe
from insights.compat import run_as
with run_as("Administrator"):
    for b in ConnectedBusiness.objects.all():
        rows = frappe.get_all("Command Center Ingest State", filters={"business_code": b.business_code},
                              fields=["fact", "status", "last_run"])
        failed = [r.fact for r in rows if (r.status or "").lower() in ("failed", "error")]
        last = max((r.last_run for r in rows if r.last_run), default=None)
        flag = "WARN " if failed or not last or (dt.datetime.now() - frappe.utils.get_datetime(last)).total_seconds() > 26 * 3600 else "OK   "
        print(f"   {flag} {b.business_name}: {b.status}, last loaded {last or 'never'}"
              + (f", failing: {', '.join(failed)}" if failed else ""))
d = maintenance.backup_dir()
dumps = sorted(d.glob("insights-*.sql.gz")) + sorted(d.glob("insights-*.sqlite3")) if d.exists() else []
if "--backup" in sys.argv:
    try:
        print(f"   OK    backup written now: {maintenance.backup()}")
        dumps = sorted(d.glob("insights-*.sql.gz")) + sorted(d.glob("insights-*.sqlite3"))
    except Exception as e:
        print(f"   BAD   backup failed: {e}")
if dumps:
    age = (dt.datetime.now() - dt.datetime.fromtimestamp(dumps[-1].stat().st_mtime)).total_seconds() / 3600
    print(f"   {'WARN ' if age > 36 else 'OK   '} last backup {age:.0f} h ago ({dumps[-1].name}, {dumps[-1].stat().st_size // 1024} KB), {len(dumps)} kept in {d}")
else:
    print(f"   WARN  no backup yet in {d} (the first runs tonight at 01:45; ./deploy/health.sh --backup tests it now)")
PYPLAT
fi

printf '\n== summary\n'
if [ ${#ISSUES[@]} -eq 0 ]; then echo "   nothing to fix"; else printf '   %s\n' "${ISSUES[@]}"; fi
echo "   (lines the platform printed itself are not repeated here; look for WARN/BAD above)"
