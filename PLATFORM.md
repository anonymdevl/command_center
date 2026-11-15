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

## Everyday tasks

| Task | How |
|---|---|
| Add a manager | Admin → Users → add (email as username), set a password, add the group *Insights Dashboard Manager*. Or `manage.py add_manager email "Name"`. |
| Remove a manager | Admin → Users → untick *Active* (or remove the group). |
| Connect a business | Admin → Connected businesses → add; its secret is write-only. Or `manage.py register_business`. Then `manage.py execute command_center.api.ingest.run_all --kwargs '{"full": true}'`. |
| What went wrong | Admin → Error log. |
| Change the Claude key | `manage.py shell -c "import frappe; frappe.installer.update_site_config('command_center_anthropic_key', input())"`. No restart needed. |
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

- **The Settings page:** the designed screen for businesses, people and keys. Until then, the admin covers it.
- **Approvals and delegation from the platform:** these work with each manager's own ERPNext key, linked in Admin → Site credentials.
- **Agent mode** (Claude proposing actions you confirm).
- **Sign-in wording:** the sign-in page still mentions ERPNext in its error messages.
