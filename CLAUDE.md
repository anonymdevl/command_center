# Command Center — working agreement

Read this before touching anything. It exists because a full day was lost to the same
handful of mistakes repeating, and each rule below is written against a specific one.

## What this is

An executive intelligence platform over ERPNext, built as a single Frappe app
(`command_center`) installed on one site and able to read peers. Client: Gigmann Medical
Supplies Ltd (Ghana, GHS). Michael Appiah-Kubi's personal Upwork engagement — **not
Powersoft**. Demo site: `biomed.ultrasoft-systems.com`.

Management-only. The interface is at `/command-center`.

---

## The five rules that would have prevented every mistake so far

### 1. The designed screens are the product. Never replace one.

`frontend/src/legacy/views.json` holds the designed screens. They were settled over many
rounds: spacing, labels, card contract, wording, panel order.

"Wire a screen" means **put real figures into the screen that exists**. It never means
writing a new component for it. I replaced Command with my own layout, was told, and then
did the same to eight more screens. All nine were deleted.

The mechanism is `frontend/src/legacy/hydrate.js`: it finds each designed card by its
label and swaps the figure. To make a card live, add one line to `CARD_KPIS` and define
the KPI. That is the whole job.

If a screen genuinely cannot be served this way, **say so and ask** — do not invent a
replacement.

### 2. Check the live site before writing code that depends on it.

There is direct read access to Biomed via the Kraken ERPNext tools. Use it **before**
writing, not after deploying.

- Before reading a field: confirm it exists. `resolution_date` does not exist on Issue in
  this ERPNext — it is `sla_resolution_date`. Frappe returned rows with only `name` and
  `modified` and raised nothing, so sixty cases loaded blank and the screen looked fine.
- Before assuming data is missing: count it. Twenty screens were held back on the
  assumption their data did not exist. The site had 1,405 sales orders, 70 tasks, 30
  projects and 35 employees all along.
- Before asserting a figure: query it. Never put a number in a message that has not come
  back from the live site.

`frappe.client.get_list` validates field names and names the bad one. Use it as the check.

### 3. Every new module gets the guards its siblings have.

Before writing a module alongside an existing one, read the existing one and carry over
its defences. `require_fields` was written precisely for the silent-field-drop failure,
then four new ingestors were written without it.

Preflight enforces the ones discovered so far. When a fault is found, add the check in the
same commit as the fix.

### 4. A check that cannot fail is worse than no check.

`check(True, "")` shipped once. A `<Figure>` regex that could never match shipped once. A
scan over deleted files nearly shipped. Each read as coverage and provided none.

**After adding any check, prove it fails**: break the thing it guards, confirm the failure,
restore. If that is impractical, do not add it.

### 5. One definition of anything.

`_currency` existed three times. The fact-to-doctype map twice. `kpi()` twice, differing
by one class. Every duplicate drifted or was about to.

Before adding a constant, helper or map, grep for it. Before deleting an export, grep for
its consumers — `isLive` was removed without that and broke the build.

---

## Honesty rules that are not negotiable

These are the product's whole value. A figure that is wrong but plausible costs more than
a missing one.

- **A label and its figure must mean the same thing.** "Purchase orders" must not show a
  count of unpaid invoices. "On the books" and "Active" must not be the same number. If no
  KPI matches the label, leave the card illustrative.
- **Every figure carries its as-of date.** The extract ends 2025-08-19. Ageing anything
  against `today()` turns a stale snapshot into a false finding about the business — that
  happened once and was reported to the client before it was caught.
- **A subset says what it is a subset of.** GHS 4,592,482 was reported as the whole
  receivable for most of a day; it was the ten largest customers, of 9,177,568.91.
- **Cannot-compute is not zero.** A ratio with no denominator returns `None`, not 0%.
- **Missing data is a finding, not a blank.** `has_cost`, `has_valuation`, `is_assigned`
  exist so absence is reportable.
- **Real and demonstration figures never sit together unmarked.** Illustrative cards say
  so on the card.
- **Seeded data is marked `[DEMO]`, removable, and never financial.** A fabricated
  receivable is indistinguishable from a real one once it is in the table.

---

## How to work

**Order of every task:** read what exists → check the live site → change the smallest
thing → `python3 scripts/preflight.py` → verify against live data via Kraken → only then
write the push script.

**Verify before asking for a deploy.** Every round trip that ends in "actually that was
wrong" costs an hour of someone else's day. The KPI engine can be exercised offline
against stubbed frappe (`/tmp/kpitest/all.py` pattern) — use it.

**Deploying is one command.** On the server: `cd ~/frappe-bench-16/apps/command_center &&
./deploy.sh`. It pulls, migrates, loads every fact, prints the load status and the
self-checks, then clears cache and restarts — in that order, which preflight enforces.
`--reseed` rebuilds the demonstration complaints (and forces a full reload, because
reseeding deletes documents and their fact rows would otherwise survive). `--full`
rebuilds every fact from scratch. Migrate runs `--skip-failing` because two ERPNext
v14/v15 patches fail on this site and are unrelated to this app; the skip is announced in
the output, and `--strict` turns it off. Never hand over a list of bench commands again: a
sequence typed by hand is a sequence that can be got wrong, and a multi-line paste loses
its first character.

**Push scripts** are disposable `.push-N.sh` at the repo root: rebuild, preflight, commit,
push, self-delete. The connected folder cannot unlink files, so **all deletions go in the
push script**. Commit messages say what was wrong and why, not just what changed.

**Say what is not done.** List the screens still illustrative and why. Do not let silence
imply completeness.

---

## Layout

```
command_center/
  facts/schema.py         fact → doctype, dimensions, measures, filter translation  (ONE definition)
  facts/presentation.py   per-fact drawer columns, sort, concentration dimension
  ingest/base.py          Ingestor, require_fields, ageing_bucket, lateness_bucket, resolve_as_of
  ingest/registry.py      every ingestor  (ONE definition)
  kpi/registry.py         Kpi dataclass, validation, dependency graph
  kpi/engine.py           evaluate_set, ratios, notes, as-of, data status
  kpi/{sales,buying,stock,operations}.py   the KPI definitions
  api/{kpi,facts,ingest,businesses,actions}.py
  demo/seed.py            marked, removable, non-financial
  www/command_center.py   the page controller (underscore filename — hyphens never run)
deploy.sh                 the one command the server runs
frontend/src/
  legacy/views.json       THE DESIGNED SCREENS — do not replace
  legacy/hydrate.js       label → KPI, figure substitution
  components/{LegacyView,Records,DataTable,Sidebar,Topbar,Drawer,States,Appearance}.jsx
interface/                generators that build views.json and the CSS
scripts/preflight.py      800 checks — must pass before any push
```

**Verified live figures** (as at 2025-08-19, the data horizon): receivable
9,177,568.91 / 806 invoices, 90+ = 6,777,142.92 (73.84%); revenue 23,422,310.10; margin
27.65% on 23,407,739.10 costed; payables 5,645,271.09 / 122; stock 3,769,970.49 / 2,375
lines; order book 9,131,894.14 / 524 open; headcount 24 active of 35 across 11
departments; 57 tasks in flight, 24 past due.

---

## Still to do

1. Fill the remaining illustrative cards — one KPI each. Two need engine work: a date
   filter relative to the data horizon (month-over-month), and a max-over-groups
   aggregate ("best month").
2. Control Health, Risk, Systems and access, Internal audit.
3. The task and approval engine — Daily brief, My day, Approvals, Work handed out need it,
   not facts.
4. Ask the business, Find anything, Reports.
5. A "Refresh figures" control in the interface, and the load history on Control Health,
   so nobody opens a terminal to see current numbers. `deploy.sh` covers the deploy; this
   is about the day-to-day refresh.
6. Alert engine and the first five rules.
7. Correct blueprint §8.5 to the stack actually built (React + Vite, own API client, no
   frappe-react-sdk / TanStack / Recharts / Playwright).
8. Second-site pairing, once one site is solid.

Open decisions for Michael: pricing, hosting region, model provider, approval thresholds,
cross-site write-back scope.
