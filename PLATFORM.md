# The standalone platform

The intelligence layer as its own service: a Django application with its own database,
its own sign-in and its own administration, on the UTS server. It has no Frappe site
and no ERPNext. Businesses plug in by giving it a key to read their ERPNext over the
standard API; nothing is installed on their side.

## How it fits together

| Piece | What it is |
|---|---|
| `command_center/` | The business logic, unchanged: loading each business's data, the 85 figures, Claude, alerts, reports, exports, the screens' calls. |
| `insights/compat/` | The platform's own runtime under the name `frappe`, so the business logic runs as it was tested. Database calls go through Django's ORM; the figures' queries through PyPika; plus cache, jobs, PDFs and mail. No Frappe code anywhere. |
| `insights/core/` | Django models generated from the 19 doctypes (same tables), the admin, the web layer and the commands. |
| `frontend/` | The designed screens, unchanged. Built into `command_center/public/command-center/`. |
| Database | MariaDB on the server (its own database and user); SQLite on a laptop. |
| People | Django users. A manager holds the group **Insights Dashboard Manager**; the platform administrator is a superuser. |
| Secrets | A business's API secret is encrypted with `encryption_key` (in `insights.json`), never stored readable. |

## Install on the server (first time)

```bash
git clone -b standalone https://github.com/anonymdevl/command_center.git ~/insights-platform
cd ~/insights-platform && ./deploy/platform.sh
```

It asks for:
- the MariaDB root password, to create the platform's own database;
- your administrator email and password;
- the Anthropic key;
- the first business: its ERPNext address and the API key and secret it reads with.

Then it runs the first full load and starts two services: `insights-web`, on `127.0.0.1:8200`, and `insights-scheduler`. It does not touch any bench or site.

**Back up `insights.json`.** Without its `encryption_key`, stored business secrets can't be read.

## Open it

There's no domain yet, so open it through an SSH tunnel from your own computer. Nothing is exposed publicly:

```bash
ssh -L 8200:127.0.0.1:8200 erpnext@<server>
```

Then:
- the platform: http://localhost:8200/command-center-login
- administration: http://localhost:8200/admin/

With a domain (its DNS pointing at this server), one command puts it on HTTPS:

```bash
./deploy/domain.sh insights.ultrasoft-systems.com you@ultrasoft-systems.com
```

It adds an nginx site for that name only (no other site or bench is touched), gets a
Let's Encrypt certificate that renews on its own, redirects http to https, sets the
platform's address in `insights.json` and restarts it. The tunnel keeps working too.

**The server's other sites are not affected.** The platform's nginx site matches its own
name only, loads last (so it can never be the fallback for unknown names) and sets no
port-wide options. `domain.sh` records how every other site answers before the change and
checks them again after; if one that answered stops, it takes its own site out again.
The platform's services run at lower CPU and disk priority with a 2 GB memory ceiling,
in their own database, and read the businesses' ERPNext a page at a time.

## Everyday tasks

| Task | How |
|---|---|
| Add a manager | Settings → People → Add Person (in the platform's sidebar, administrators only): email, name, a password typed twice or "set it later", tick Manager. Or `manage.py add_manager email "Name"`. |
| Remove a manager | Settings → People → Manage → Deactivate (their sign-ins end at once) or Remove Manager. Make Administrator, Reset Password are there too; the last administrator cannot be removed. |
| Connect a business | Settings → Businesses → Add Business (address, API key and secret; it is checked at once and says who it reads as and whether it can write). Then Manage → Reload Everything for its first full load, in the background. Edit, Test Connection and Pause are there too; secrets are write-only. Or `manage.py register_business`. |
| Are the figures right? | Settings → Businesses → Manage → Check Figures: each figure the screens rest on (unpaid invoices, the customer and supplier ledger balances, payments not matched, sales, orders, stock, people, tasks, cases), from the platform and from the business's ERPNext now, with the difference and why. Or `manage.py execute command_center.api.audit.reconcile --kwargs '{"business_code": "..."}'` for the same as a table. Reads only. |
| What went wrong | Admin → Error log. |
| Is everything healthy? | `./deploy/health.sh`: the server (load, memory, disk, updates, certificates, shared services) and the platform (services, errors, loads, backups). Reads only. `--backup` also tests the backup now. |
| Backups | Every night at 01:45 into `~/insights-backups` (the database and `insights.json`), 14 days kept. Copy them off the server now and then. |
| Change the Claude key | Settings → Claude → Replace Key, then Check. No restart needed. |
| Let a manager help with Settings | Settings → People → Manage → Settings Access (administrator only): tick Businesses (add, edit, test, pause, reload businesses), People (add managers, deactivate/reactivate them, reset their passwords) and/or Personal ERPNext Keys (managers' keys). They see Settings in their sidebar, with only those sections, after they reload the platform. They can never make an administrator, give Settings access, or change an administrator or anyone else with Settings access. The Claude key, Email, Changes and Settings Access stay with the administrator. Each grant is a Django group ("Settings: Businesses", "Settings: People", "Settings: Personal Keys"); removing someone as a manager takes their access away too. Every grant and removal is under Changes. |
| Email (scheduled reports) | Settings → Email (administrator only): mail server, port, security (STARTTLS, SSL or none), username, password (never shown again; blank keeps it), From address and name, then Send Test Email. Saved to `insights.json` "mail" and used from the next email by both the web server and the scheduler, no restart. The Notifications panel above it says whether email is set up, how many report schedules and alert rules are on, the last email sent or not, and which schedules failed. A message that cannot be sent (email not set up, server refused it) is never dropped: it is in Admin → Error log as "Email not sent", and the report schedule's last status says why. Alerts are shown in the bell; they are not emailed. |
| A manager's own ERPNext key (approvals) | Settings → Personal ERPNext Keys → Add Key. |
| Who changed what | Settings → Changes (also Admin → Recent actions). Secrets are never recorded. |
| Update | `./deploy/platform.sh` (pull, install, migrate, restart). |
| Run any function | `manage.py execute <dotted.path> --kwargs '{...}'` (as `bench execute` was). |

## Checks

`python3 scripts/preflight.py` must pass before every push. It now also runs `manage.py test insights`. That test:
- registers a business;
- loads every fact from a fake ERPNext;
- checks that the figures agree;
- calls the screens as a signed-in manager.

It also checks that the generated models match the doctype JSON and that migrations exist.

## Not done yet

- **The Settings page** is built (people, businesses, the Claude key, email, personal ERPNext keys, changes), for the administrator, who can give managers the Businesses, People and Personal ERPNext Keys sections. Not there yet: removing a business, editing its overdue days or approval threshold, and its ERPNext sign-in (OAuth client); those stay in Admin → Connected businesses.
- **Approvals and delegation from the platform:** these work with each manager's own ERPNext key, linked in Settings → Personal ERPNext Keys.
- **Agent mode** (Claude proposing actions you confirm).
- **Sign-in wording:** the sign-in page still mentions ERPNext in its error messages.
