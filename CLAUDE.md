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

The mechanism is `frontend/src/legacy/hydrate.js`: it finds each designed card or tile
by its label and swaps the figure. To make a card live, add one line to `CARD_KPIS`; for
a tile, one line to `TILE_KPIS`, which also names the unit word the tile prints inside
its number. Define the KPI. That is the whole job.

A tile's footnote is replaced by the KPI's note only if the designed footnote contains a
figure of its own. A footnote with no figure is a statement about the business — "Payroll
shown as status only, names hidden" — and is left alone. A tile whose `onclick` calls
`go()` keeps its navigation; only `explain()` placeholders are replaced.

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

**A doctype can be readable by nobody, and Frappe will not say so.** Issue on this site
has `Custom DocPerm` rows granting read to no role, and Custom DocPerms *replace* the
standard ones. `frappe.get_list` does not raise: it strips every field the acting roles
cannot read and returns rows carrying only `name` and `modified`. That is why sixty
complaints loaded blank. Ingest therefore reads as the system, via
`BusinessConnector.as_system()` — only ingest, only the local business, and preflight
enforces both. It widens nothing: facts are read back through `api/kpi` and `api/facts`,
which call `require_manager()` first.

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
the output, and `--strict` turns it off. Migrate takes a site-wide lock that a previous
migrate's queued search-index rebuild can still hold, so it retries three times thirty
seconds apart before giving up with an explanation; `--no-migrate` skips the step for a
change that touched no doctype. Deleting the lock file does not release the lock. Never
hand over a list of bench commands again: a
sequence typed by hand is a sequence that can be got wrong, and a multi-line paste loses
its first character.

**Push scripts** are disposable `.push-N.sh` at the repo root: rebuild, preflight, commit,
push, self-delete. The connected folder cannot unlink files, so **all deletions go in the
push script**. Commit messages say what was wrong and why, not just what changed.

**Look before you deploy.** `cd frontend && npm run screens`, then open
`http://localhost:8090/preview.html#<view key>`. That is the real App -- same components,
views.json and hydrator -- with `frontend/preview/mock.js` answering the API in the
browser from the verified figures above, so every visual change can be checked on all
nineteen screens without a push. It is dev-only: vite builds index.html alone, and
preflight fails if the preview's marker ever appears in the bundle.

**The design system is tokens, and preflight holds it.** Every colour, font size, weight
and corner in the stylesheet is a token from `interface/p1.py` (`--fs-*`, `--fw-*`,
`--r-*`, `--sp-*`, the palette), in both themes. Accents come from `interface/accents.py`
only -- five of them, Cobalt the default. The font is Manrope, bundled from
`@fontsource-variable/manrope`; nothing fetches a font at runtime. Preflight fails an
off-scale size or weight, a colour defined for one theme only, an accent without CSS, or a
web-font URL. The screens' own `style="..."` attributes are not yet on the scale (phase 5).
`preview.html?theme=light&accent=cobalt&audit=1` walks all nineteen screens and lists
anything wider than its box.

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
  ask/{resolve,intents,query,engine}.py   the question box: entity resolution,
                          answerable questions, frappe.qb aggregation, the planner seam
  ask/{gemini,planner_llm}.py             Gemini as the router only. Key from
                          site_config, never the repo; pinned model, not -latest
  demo/seed.py            marked, removable, non-financial
  www/command_center.py   the page controller (underscore filename — hyphens never run)
deploy.sh                 the one command the server runs
frontend/src/
  legacy/views.json       THE DESIGNED SCREENS — do not replace
  legacy/hydrate.js       label → KPI, figure substitution
  components/{LegacyView,Records,DataTable,Sidebar,Topbar,Drawer,States,Appearance}.jsx
interface/                generators that build views.json and the CSS.
                          Every file loads, via two chains: p7->p6->p5->p4->p3->p2 and
                          views_e->views_d->views_c->views_b->views_a, with the views_*
                          set exec'd last. So where a name is defined twice -- V_SALES,
                          V_ASK, V_PROC, V_INV, V_CX, V_FIN, V_HR, V_IT, V_AUD all are --
                          the views_* copy wins and the p* copy is shadowed. Editing the
                          shadowed one changes nothing on screen. Find the live owner by
                          matching the rendered <h3> against the files before editing.
scripts/preflight.py      1209 checks — must pass before any push
```

**Verified live figures** (as at 2025-08-19, the data horizon): receivable
9,177,568.91 / 806 invoices, 90+ = 6,777,142.92 (73.84%); revenue 23,422,310.10; margin
27.65% on 23,407,739.10 costed; payables 5,645,271.09 / 122; stock 3,769,970.49 / 2,375
lines; order book 9,131,894.14 / 524 open; headcount 24 active of 35 across 11
departments; 57 tasks in flight, 24 past due.

---

## The question box

Two layers. **Gemini routes; the facts answer.** The model reads the question, the handler
list and entity names found in the question, then names one handler and at most one
subject. It computes, states, rounds and phrases nothing. Every figure comes from
`ask/intents.py` reading the fact tables, and a test asserts the router and the patterns
produce a byte-identical sentence for the same question.

`MATCHERS` in `intents.py` routes the fallback and **nothing else**. An intent must never
check the question's wording itself: when they were the same thing, a question Gemini
classified correctly was still refused by the intent's own regex, which made the router
pointless. Preflight fails any intent containing a phrasing guard.

Everything about Gemini is optional. No key, no network, a slow reply, a malformed reply,
an invented handler name, or a subject that was not in the question — each falls back to
the patterns, and the answer reports which path actually decided. The screen says so too:
"the wording was read by Gemini … the figures above came from the records, not from the
model."

**The key lives in `site_config.json`, never in the repo.** Set it with
`bench --site <site> set-config command_center_gemini_key "..."`. Preflight scans every
tracked file for anything shaped like a Google API key and fails the build. The model is
pinned (`gemini-2.5-flash-lite`), not a `-latest` name, because a floating name changes a
deployed demonstration's behaviour with nobody deploying anything.

What actually leaves the site is far less than the "whatever the question needs" boundary
Michael authorised: the question as typed, the fixed handler list, and entity names found
in the question itself. No figures, no totals, no record contents, no customer list. Worth
telling Gigmann precisely that. If we later let the model phrase answers, figures would
have to go to it, and that is a separate decision.

Decisions on record: keep "Ask the business" (now "Ask AI") and drop "Find anything";
deterministic first with the model as a router; Gemini rather than Claude, on Michael's
key.

## The sidebar captions

Settled by Michael, in this order, and enforced by preflight: Home, Executive Summary,
Today, Business Overview, Business Health, Risk and Compliance, Approvals, Outstanding
Tasks, Ask AI, Reports, Sales and Payments, Buying and Suppliers, Stock & Warehouses,
Project Insights, Customer Service & Issues, Finances, HR & Payroll, Systems and Access,
Internal Audit.

They live in the NAV tuples in `interface/build.py` and nowhere else. Each screen's own
`<h3>` must say the same thing — a caption and a heading that disagree is the same fault
as a card whose label and figure disagree. **View keys are unchanged** (`command`, `brief`,
`myday`, `ops`, `health`, `risk`, `approvals`, `delegation`, `ask`, `reports`, `sales`,
`proc`, `inv`, `eng`, `cx`, `fin`, `hr`, `it`, `aud`): they carry deep links, `CARD_KPIS`
and the hydration map, so renaming them would break wiring for no gain.

A nav label is rendered by React as text, so it carries a real `&`. An `<h3>` goes through
innerHTML and carries `&amp;`. Preflight checks both.

## Still to do

Wiring first, on Michael's instruction: every card, tile, button, drawer and menu doing
something real before any new intelligence is added. Tracked as tasks 20-31, then 18-19.

**The wiring inventory, counted from the shipped views.json rather than estimated:**

| | |
|---|---|
| Designed KPI cards | 68, of which **14 are live** |
| `.bk` tiles | 34, of which **6 are live** — all six on Business Overview |
| Static drawers / explainers | 78 (48 explainers, 7 drawers, 6 drill panels) |
| Explicit `unwired` placeholders | 4 (Home 2, Internal Audit 2) |
| Buttons with no handler | 0 |

Order of work:

1. ~~**Hydrate the tiles.**~~ Done. `hydrateTiles` exists and six Business Overview
   tiles are live. The other twenty-eight are illustrative and say so on the tile, and
   none of them is waiting on a mapping: Today and Outstanding Tasks need the task and
   approval engine, Risk needs a compliance register, Business Health's are composite
   scores, and the six "Awaiting …" tiles on Sales need a pipeline fact that separates
   the stages.
2. **Relative date filters** against the data horizon — blocks every month-over-month card.
3. **Max-over-groups aggregate** — blocks "Best month", "Top supplier", "Longest wait",
   "Worst shortfall".
4. **Two more facts**: purchase orders (235 on the site) and stock movements.
5. **Fill the 54 illustrative cards**, money screens first, then operational.
6. **The 78 static drawers** — decide prose-or-live for each, and record the decision.
7. **The 4 `unwired` placeholders.**
8. **Task and approval engine** — Approvals, Today, Outstanding Tasks and Executive
   Summary have no facts behind them and never will; they need the platform's own records.
   TK-01..TK-08, AP-01..AP-07, AC-06.
9. **Reports** — nine named reports, none generating anything. RP-01..RP-10.
10. **Refresh control and load history on Business Health** — where the trust panels I
    wrongly put on Command belong.
11. **Click-through audit** of all 19 screens. Preflight checks source, not behaviour, so
    only clicking can answer "does everything work as expected".
12. **Alert engine**, five rules. AL-01..AL-07.
13. **Blueprint §8.5**, plus Gemini and the ten facts.

Then: second-site pairing.

**Where the app stands against the AI requirements** (from the RTM, 355 requirements):
all eight AI-B prohibitions hold structurally and preflight enforces them. Of the seven
AI-P permitted abilities, AI-P1 and AI-P2 are partial, AI-P3 has no trend capability at
all, and AI-P4 to AI-P7 are unbuilt — `draft_communication` and the task tools exist in
`ai_tools.py` but Ask cannot reach them. Ask AI is a leaf: it reads the KPI engine so its
figures agree with the cards, but nothing consumes its output.

**Two requirements bearing on Gemini that are not yet satisfied:** AI-01 permits any
suitable model *subject to Gigmann approval*, and SE-07 requires disclosing external
AI/model providers. Neither is on record.

Open decisions for Michael: pricing, hosting region, Gigmann's approval of Gemini
(AI-01/SE-07), approval thresholds, cross-site write-back scope.
