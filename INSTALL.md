# Installing `command_center` on ERPNext v16

## Requirements

| | Needs |
| --- | --- |
| Frappe | v16.x |
| ERPNext | v16.x |
| Python | 3.10+ |
| Node | 18+ (only when the interface is built, from step 4) |

No other Python packages are pulled in. `requests` is declared in `pyproject.toml`
but ships with Frappe already, so nothing new lands in the bench's virtualenv.

## First install

```bash
cd ~/frappe-bench-16

bench get-app https://github.com/<you>/command_center.git
bench --site <site> install-app command_center
bench --site <site> migrate
bench --site <site> clear-cache
```

Then give each manager the **Command Center Manager** role. There is no general
staff role — the platform is management-only by design, and adding one is a
decision, not an oversight.

## What install does

1. Creates the `Command Center Manager` role (`install.py`).
2. Creates three doctypes: `Connected Business`, `Command Center Site Credential`,
   `Command Center Change Event`.
3. Runs `seed_local_business`, which registers this site as **connector number
   one** — the `Connected Business` flagged `is_local`, pointing at the site's
   first Company. If no Company exists yet, registration happens on first use
   instead of failing.
4. Registers a `doc_events` hook on the fourteen transactional doctypes listed in
   `hooks.py`, writing one `Command Center Change Event` per transaction.
5. Registers two scheduled jobs: peer refresh every fifteen minutes, event
   pruning daily.

Nothing existing is modified. No custom fields are added yet — those arrive with
the domain work.

## Verify it installed cleanly

```bash
bench --site <site> console
```

```python
import frappe
frappe.get_all("Connected Business", fields=["business_name", "business_code", "is_local"])
# → one row, is_local = 1

frappe.get_doc("Role", "Command Center Manager").name
# → 'Command Center Manager'
```

Then visit `/command-center`. You should get the placeholder page, not a 404.
A 404 means `website_route_rules` did not load — run `bench clear-cache` and
`bench restart`.

## Adding a second business

On **each** site, install the app, then on each register the other:

| Field | Value |
| --- | --- |
| Business Name | the other company's name |
| Business Code | a stable key, set once |
| This Site | unchecked |
| Site URL | `https://other-site.example.com` |
| API Key / Secret | a **read-only** account on that site |

The read-only account is used solely by the scheduled refresh. To *act* in the
other business, each manager links their own credentials once:

```python
frappe.call("command_center.api.credentials.link_account",
            business_code="other_business",
            api_key="...", api_secret="...")
```

Their write then arrives on the far site as them — its permissions decide what
they may do, and its change history records their name. Revoking the key on that
site revokes their access here immediately.

Check reachability at any time:

```python
frappe.call("command_center.api.businesses.test_connection",
            business_code="other_business")
```

## Uninstall

```bash
bench --site <site> uninstall-app command_center
```

Removes the three doctypes and their data. Nothing in ERPNext is touched, because
nothing in ERPNext was changed.

## Development

Develop in the repository, not against the server's filesystem. Commit, push,
then on the server:

```bash
cd ~/frappe-bench-16/apps/command_center && git pull
cd ~/frappe-bench-16 && bench --site <site> migrate && bench restart
```

A remote file-writing endpoint is a deliberate remote-code-execution hole and
must not exist in a repository that gets installed on a client's site.
