# Intelligent Command Center

An executive intelligence layer over ERPNext. Installs as an ordinary Frappe app.

**Product:** Intelligent Command Center · **App:** `command_center` · **First deployment:** Gigmann Medical Supplies Ltd

The platform is a reusable product, not a one-off build. Nothing is named after a client:
doctypes are prefixed `Command Center …`, custom fields `icc_…`, the API namespace is
`command_center.api.…`.

## Install

```bash
bench get-app https://github.com/<you>/command_center.git
bench --site <site> install-app command_center
bench --site <site> migrate
```

Give each manager the **Command Center Manager** role. There is no general staff role —
the platform is management-only by design.

## Architecture

One app. No separate service, no second database, no external front end.

| Concern | Where it lives |
|---|---|
| Custom doctypes, change feed, write endpoints | this app, inside the site |
| Authentication | Frappe session — nothing to build |
| Permissions | the site's own, via `frappe.set_user` on every write |
| Audit trail | the site's own `Version` records |
| Interface | SPA in `frontend/`, built into `public/frontend`, served at `/command-center` |

### Multiple businesses

A second site is the same calls pointed at a different URL with different credentials.
That is the whole of it.

```
Site A (Business A)  ←── mutual link ──→  Site B (Business B)
  app installed                             app installed
  owns A's data                             owns B's data

Open the Command Center on either → ALL · SITE A · SITE B · …
```

Three navigation levels:

1. **ALL** — every connected business at once
2. **SITE A / SITE B / …** — one business, the full set of screens
3. **detail** — the records and reports underneath

Four rules make it work:

- **The host site is connector number one.** The app never treats the site it is installed
  on as a special case — it is the `Connected Business` flagged `is_local`. Moving the
  platform to another site is a configuration change, not a rewrite.
- **Each site is authoritative for its own business, and a window onto everyone else's.**
  No setting is writable in two places, so there is nothing to reconcile and alerts fire
  once. Peer settings are read and shown read-only.
- **The platform is a live window, not a warehouse.** A balance sheet for another business
  is computed by the site that owns the ledger and returned over REST. Nothing of that
  ledger is stored here. Sites may be on entirely different servers.
- **The platform carries authority; it never grants it.** Each manager links their own
  account to each business they work in. A change made from here arrives at the owning
  site as *them* — checked against their permissions there, recorded under their name in
  its history, and revocable by deleting the key on that site. The platform's own service
  account is read-only and used solely by the scheduled refresh, where no human is present
  to attribute anything to. No write ever uses it.

Membership is the only thing shared across a group. Compute is not. That keeps
configuration linear as sites are added rather than growing with the square of them.

## Layout

```
command_center/
├── pyproject.toml
└── command_center/
    ├── hooks.py                  doc_events → change feed · SPA route · scheduler
    ├── install.py                creates the Command Center Manager role
    ├── connectors/
    │   ├── base.py               the seam — identity travels with every call
    │   ├── local.py              this site, via frappe.*, under the acting user
    │   ├── remote.py             a peer, via REST; writes refuse
    │   └── registry.py           which businesses exist and how to reach them
    ├── api/
    │   ├── businesses.py         the scope switcher; management-only guard
    │   ├── credentials.py        each manager's own key per business
    │   ├── changes.py            change feed + peer refresh
    │   ├── actions.py            what a manager can do — their permissions, nothing less
    │   └── ai_tools.py           what the assistant can do — a closed catalogue
    ├── command_center/doctype/
    │   ├── connected_business/
    │   ├── command_center_site_credential/
    │   └── command_center_change_event/
    └── www/command_center.html   placeholder until the SPA is built
```

## Two doors

A recurring mistake in tools like this is to restrict the product when the requirement was
to restrict the automation. They are separate questions and they get separate answers.

| | `actions.py` | `ai_tools.py` |
|---|---|---|
| Who calls it | a manager, by clicking | the assistant |
| What it allows | whatever their ERPNext permissions allow | a closed catalogue, four tools |
| Invoices, payments, journals, master data | available, if they have the rights | absent |
| How the limit is enforced | ERPNext, on the owning site | the name is not in the dictionary |

Gigmann's requirements AI-B1…AI-B8 name eight classes of action the assistant must not
take unattended. Those restrictions live on the assistant's side, where they were asked
for. A CEO who can approve a purchase order in ERPNext can approve it from here — a
platform that prevents that is not safe, it is broken.

`actions.py` also never reaches past ERPNext: no raw SQL, no `ignore_permissions`, no
`ignore_validate`, no direct `db.set_value` on a business document. Everything goes
through the front door, which is what keeps the figures trustworthy and the history whole.

## Status

Step 2 of the build order: skeleton, change feed, connector layer. Not yet built —
analytical facts, KPI engine, alert engine, the assistant, and the interface.
