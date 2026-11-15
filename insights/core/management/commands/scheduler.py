"""The platform's timed work, run as its own process (systemd keeps it alive):

    manage.py scheduler

The schedule is the one the business logic always declared (command_center/hooks.py
scheduler_events): the 15-minute refresh of each business, the hourly alerts and due
reports, the nightly load, the weekly full rebuild -- plus the platform's own upkeep
(insights/core/maintenance.py: old errors, expired sessions, the nightly backup). Each run is a unit of work as
Administrator; a failure is recorded in the error log and stops nothing else.
"""

import logging
import signal
import threading

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management.base import BaseCommand

import frappe  # insights.compat
from insights.compat import get_attr, run_as

FIXED = {
    "all": CronTrigger(minute="*/4"),
    "hourly": CronTrigger(minute=5), "hourly_long": CronTrigger(minute=10),
    "daily": CronTrigger(hour=1, minute=15), "daily_long": CronTrigger(hour=2, minute=0),
    "weekly": CronTrigger(day_of_week="sun", hour=3, minute=0),
    "weekly_long": CronTrigger(day_of_week="sun", hour=3, minute=30),
    "monthly": CronTrigger(day=1, hour=4, minute=0),
    "monthly_long": CronTrigger(day=1, hour=4, minute=30),
}

log = logging.getLogger("insights.scheduler")


def _job(path):
    def run():
        try:
            with run_as("Administrator"):
                get_attr(path)()
            log.info("ran %s", path)
        except Exception:
            frappe.log_error(title=f"Scheduled job failed: {path}",
                             message=frappe.get_traceback())
    run.__name__ = path
    return run


class Command(BaseCommand):
    help = "Run the platform's scheduled jobs (hooks.scheduler_events)."

    def handle(self, **opts):
        from command_center import hooks
        sched = BlockingScheduler(timezone=None, job_defaults={"coalesce": True,
                                                               "max_instances": 1,
                                                               "misfire_grace_time": 600})
        events = getattr(hooks, "scheduler_events", {})
        n = 0
        for when, paths in events.items():
            if when == "cron":
                for expr, cron_paths in paths.items():
                    for p in cron_paths:
                        sched.add_job(_job(p), CronTrigger.from_crontab(expr), id=f"{expr}:{p}")
                        n += 1
                continue
            trigger = FIXED.get(when)
            if trigger is None:
                log.warning("unknown schedule %r", when)
                continue
            for p in paths:
                sched.add_job(_job(p), trigger, id=f"{when}:{p}")
                n += 1
        # The platform's own upkeep: logs, sessions, the nightly backup (maintenance.py).
        sched.add_job(_job("insights.core.maintenance.daily"), CronTrigger(hour=1, minute=45),
                      id="daily:insights.core.maintenance.daily")
        n += 1
        # Plans: the day's seats and businesses per customer, licence reminders, and on
        # the 1st the administrator's "usage statements are ready" (plans.py).
        sched.add_job(_job("insights.core.plans.daily"), CronTrigger(hour=0, minute=30),
                      id="daily:insights.core.plans.daily")
        n += 1
        # Settings -> Security: the read-only checks of every connected ERPNext.
        sched.add_job(_job("insights.core.security_watch.scheduled"),
                      CronTrigger(minute="*/30"), id="cron:insights.core.security_watch.scheduled")
        n += 1
        self.stdout.write(f"scheduler: {n} jobs")
        for job in sched.get_jobs():
            self.stdout.write(f"  {job.id}")
        signal.signal(signal.SIGTERM, lambda *a: threading.Thread(target=sched.shutdown).start())
        sched.start()
