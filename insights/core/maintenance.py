"""The platform's own upkeep, so it can run for years without anyone tending it.

Run every night by the scheduler (manage.py scheduler), or by hand:

    manage.py execute insights.core.maintenance.daily

- the error log keeps `error_log_days` (default 30) days, the sign-in record
  `security_event_days` (default 730);
- expired sign-in sessions are cleared (Django never clears them by itself);
- the platform's database is backed up to `backup_dir` (default ~/insights-backups),
  with a copy of insights.json and the uploaded logos, keeping `backup_days` (default 14)
  days of them. A backup is skipped, and the reason logged, when the disk has less
  than 2 GB free -- a full disk would hurt every site on the server, not only this one.

The business logic's own pruning (load log, consumed change events) is in its hooks.
"""

from __future__ import annotations

import datetime as dt
import gzip
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("insights.maintenance")
MIN_FREE = 2 * 1024 ** 3


def _conf(key, default):
    from django.conf import settings
    return settings.CONFIG.get(key) or default


def prune_error_log() -> int:
    from insights.core.models import ErrorLog
    cutoff = dt.datetime.now() - dt.timedelta(days=int(_conf("error_log_days", 30)))
    n, _ = ErrorLog.objects.using("aux").filter(creation__lt=cutoff).delete()
    return n


def prune_security_events() -> int:
    """The sign-in record is append-only for everyone (models._AppendOnly); its one
    exception is age. Kept `security_event_days` (default 730, two years) -- long enough
    for any incident review -- then dropped here, by date only."""
    from django.db import connections

    from insights.core.models import SecurityEvent
    cutoff = dt.datetime.now() - dt.timedelta(days=int(_conf("security_event_days", 730)))
    conn = connections[SecurityEvent.objects.db]
    table = conn.ops.quote_name(SecurityEvent._meta.db_table)
    with conn.cursor() as cur:
        cur.execute(f"delete from {table} where at < %s", [cutoff])
        return cur.rowcount or 0


def clear_sessions() -> None:
    from django.contrib.sessions.backends.db import SessionStore
    SessionStore.clear_expired()


def backup_dir() -> Path:
    return Path(os.path.expanduser(_conf("backup_dir", "~/insights-backups")))


def backup() -> str:
    """One compressed copy of the platform's database (and its configuration)."""
    from django.conf import settings
    target = backup_dir()
    target.mkdir(parents=True, exist_ok=True)
    os.chmod(target, 0o700)
    free = shutil.disk_usage(target).free
    if free < MIN_FREE:
        raise RuntimeError(f"backup skipped: only {free / 1024 ** 3:.1f} GB free on the disk")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    db = settings.DATABASES["default"]
    if db["ENGINE"].endswith("mysql"):
        out = target / f"insights-{stamp}.sql.gz"
        _dump_mariadb(db, out)
    else:
        import sqlite3
        out = target / f"insights-{stamp}.sqlite3"
        src, dst = sqlite3.connect(db["NAME"]), sqlite3.connect(out)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
    os.chmod(out, 0o600)
    cfg = Path(os.environ.get("INSIGHTS_CONFIG") or settings.CONFIG_PATH)
    if cfg.exists():
        copy = target / f"insights-{stamp}.json"
        shutil.copy2(cfg, copy)
        os.chmod(copy, 0o600)
    _backup_logos(target, stamp)
    _drop_old(target)
    return str(out)


def _backup_logos(target: Path, stamp: str) -> None:
    """The uploaded logos (Settings, Branding) beside the database copy: insights.json
    names them, so a restore needs the files too."""
    import tarfile

    from command_center import branding
    folder = Path(branding.folder())
    if not folder.is_dir() or not any(folder.iterdir()):
        return
    out = target / f"insights-{stamp}-logos.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        tar.add(folder, arcname=folder.name)
    os.chmod(out, 0o600)


def _dump_mariadb(db: dict, out: Path) -> None:
    exe = shutil.which("mariadb-dump") or shutil.which("mysqldump")
    if not exe:
        raise RuntimeError("backup skipped: neither mariadb-dump nor mysqldump is installed")
    # The password goes in a private options file, never on the command line.
    with tempfile.NamedTemporaryFile("w", suffix=".cnf", delete=False) as fh:
        fh.write(f"[client]\nuser={db['USER']}\npassword={db['PASSWORD']}\n"
                 f"host={db['HOST']}\nport={db['PORT']}\n")
        opts = fh.name
    os.chmod(opts, 0o600)
    part = out.with_suffix(".part")
    try:
        # --single-transaction: a consistent copy without locking the tables, so the
        # platform (and nothing else on this MariaDB) waits for it.
        proc = subprocess.Popen([exe, f"--defaults-extra-file={opts}", "--single-transaction",
                                 "--quick", "--routines", db["NAME"]],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with gzip.open(part, "wb", compresslevel=6) as gz:
            shutil.copyfileobj(proc.stdout, gz, 1024 * 1024)
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise RuntimeError(f"backup failed: {err.strip()[:500]}")
        part.rename(out)
    finally:
        os.unlink(opts)
        if part.exists():
            part.unlink()


def _drop_old(target: Path) -> None:
    keep = dt.datetime.now() - dt.timedelta(days=int(_conf("backup_days", 14)))
    for f in target.glob("insights-*"):
        if dt.datetime.fromtimestamp(f.stat().st_mtime) < keep:
            f.unlink()


def daily() -> dict:
    import frappe  # insights.compat
    done = {"error_log_pruned": prune_error_log(),
            "security_events_pruned": prune_security_events()}
    clear_sessions()
    done["sessions"] = "cleared expired"
    try:
        done["backup"] = backup()
    except Exception as e:  # recorded, and the rest of the upkeep still counts
        frappe.log_error(title="Platform backup", message=str(e))
        done["backup"] = f"failed: {e}"
    log.info("maintenance %s", done)
    return done
