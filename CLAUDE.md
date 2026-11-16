# Command Center — working agreement

Read this before touching anything. It exists because a full day was lost to the same
handful of mistakes repeating, and each rule below is written against a specific one.

## What this is

An executive intelligence platform over ERPNext, built as a single Frappe app
(`command_center`) installed on one site and able to read peers. Client: Gigmann Medical
Supplies Ltd (Ghana, GHS). Michael Appiah-Kubi's personal Upwork engagement — **not
Powersoft**. Demo site: `biomed.ultrasoft-systems.com`.

Management-only. The interface is at `/command-center`.

**Since 14 Nov 2026 it is a hosted service** (Gigmann paid; delivery 20 Nov 2026): the app
runs on its own plain-Frappe v16 site on the UTS server, and each of Gigmann's businesses'
ERPNext sites plugs in over the standard REST API with a read-only API user. Nothing is
installed on a client's ERPNext, and its version does not matter -- Gigmann's live site
(gigmann.powersoftsystem.com) is **v14**, which already differs from v16 (Issue's
`resolution_date` vs `sla_resolution_date`; v14 has no `{"SUM": ...}` field syntax).
`host.sh <site>` sets a hosted site up once; `./deploy.sh --site=<site>` thereafter. The
analyst is Claude (`ask/claude.py`), Gemini kept as the alternative.

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
For the hosted service, check the business's **own** site (Kraken connection `GMS` for
Gigmann), not Biomed: Biomed is a v16 copy and hides v14 differences.

**A doctype can be readable by nobody, and Frappe will not say so.** Issue on this site
has `Custom DocPerm` rows granting read to no role, and Custom DocPerms *replace* the
standard ones. `frappe.get_list` does not raise: it strips every field the acting roles
cannot read and returns rows carrying only `name` and `modified`. That is why sixty
complaints loaded blank. Ingest therefore reads as the system, via
`BusinessConnector.as_system()` — only ingest (api/ingest.py), and preflight enforces it.
For a business on another site, "the system" is its read-only service account and nothing
else: never a manager's own key, never a write (connectors/remote.py `_headers`). It widens nothing: facts are read back through `api/kpi` and `api/facts`,
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
The shell -- sidebar, bar, content panel, appearance menu -- is styled in
`interface/shell.py` only, appended last; preflight fails any other generator that
styles a shell class, and any screen that uses one. Card rows size against the panel
(`container: panel`), not the window. The question bar hands its question to the Ask AI
screen's `runSearch`, so there is one answering path. The alerts bell (`Bell.jsx`) reads
`api/alerts.open_alerts`, the same list as Home's "Needs your attention".
`interface/blocks.py` is the skin of the screens' blocks (cards, tiles, panels, tables,
tags, tabs, alerts, buttons, notes, drawer), appended after the generators and before
the shell: it owns appearance, the generators keep layout. Every .kpi/.bk gets the
mockup's cut corner and arrow from `signature_tiles()` in build.py, but they show only on
a `.clickable` tile (16 Nov 2026): Business Health's six questions (`bk q`) and a figure
not read have none; a tile marked `data-opens="figure"` gets its click (and arrow) when
its figure's link arrives. The screens' inline `style` sizes and weights are on the scale too, and preflight
holds them there.
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

## The hosted service (14 Nov 2026)

- **Remote ingest.** `api/ingest.load_business` is the one loader (button, daily
  `daily_long`, 15-minute `changes.refresh_peers` -> `ingest.poll_peers`, weekly
  `scheduled_full_load` for peers, which catches deletions polling cannot see).
  `RemoteConnector.get_list` pages by `limit_start` (500, `command_center_remote_page`),
  pauses between pages (250 ms, `command_center_remote_pace_ms`), retries 429/502-504 (never
  a write), and goes by POST when the query is long. One load per business at a time
  (`ingest.business_lock`). Incremental loads drop documents cancelled since the watermark
  (`Ingestor.cancellable`).
- **Change feed for peers** is modified-watermark polling; `record_event` only fires where
  the app is installed.
- **Every other read goes through the connector for a remote business**: `kpi/live.py`
  (`_Reader`), `ask/tools.py` (`_remote`), `api/work.py` (`_Remote`, under the manager's
  OWN linked key -- "waiting on you" means nothing under a shared account; without one the
  screens say how to link it). `api/businesses.default_business_code()` / `loaded_codes()`
  replace every `is_local=1` lookup.
- **Nothing writes mid-question**: the connector does not record reachability while
  `frappe.local.cc_deadline` is set, because the analyst's write guard would roll it back.
- **The host is Biomed** (Michael, 14 Nov 2026): `host.sh biomed.ultrasoft-systems.com`
  switches its "Gigmann Medical Supplies Ltd" record from local to remote
  (`install.register_business`; "This Site" is set-only-once on the form, so that is the
  one deliberate path) and reloads everything from the live site. Biomed's 2025 copy of
  Gigmann's ERPNext data is no longer read by anything.
- **Sign in with the business's ERPNext** (`api/sso.py`): the link on their ERPNext calls
  `sso.start?business=<code>`; their ERPNext (Frappe's OAuth provider, same on v14-v16)
  says who the person is; the platform then reads, with the service key
  (`ingest.erp_members`), whether they hold the access role there ("Executive Insights",
  site config `command_center_sso_role`). Holding it lets them in, and a newcomer gets a
  manager account on the spot. Adding a person = giving the role in their ERPNext; no
  bench step (Michael, 14 Nov 2026). Taking it away is refused at the next sign-in and
  undone by `sso.sync_members` every 15 minutes (manager role off, sessions ended), but
  only for accounts this sign-in let in (DefaultValue `cc_sso_business`); hand-added
  managers, System Managers and Administrator are never touched. A platform account
  disabled here stays out (the admin's pause). Fails closed if their ERPNext can't be
  asked. State is single-use, cookie-bound, 10 minutes; success lands on /command-center
  only; refusals go to the Error Log. The only guest endpoints are `sso.start` and
  `sso.callback` (preflight). `scripts/test_sso.py` in preflight.
- `api/ingest.check_access` lists what the service user can read and whether it holds any
  role that can write. `scripts/test_remote.py` tests the connector offline (in preflight).

## What is owed is the ledger (15 Nov 2026)

Gigmann never matches payments to invoices, so open invoices said customers owed GHS
10.07M where the General Ledger said GHS 341,565 net (suppliers: 15.54M vs 2.61M).
`fact_party_balance` (ingest/ledger.py, rebuilt whole when GL Entry, Payment Entry,
Journal Entry or an invoice changed) holds per customer and supplier: the ledger balance,
the open invoices, and the difference explained -- payments not matched (Payment Entry
unallocated), payments and credit notes the invoices do not show, journal entries and
credit notes not linked (Journal Entry Account references), amounts owed on no invoice,
and an `unexplained` remainder that is said, never forced -- plus the ageing after the
unmatched credits are set against the oldest open items. Not GL `against_voucher`: v14+
leave it as posted when a payment is matched later, and Gigmann's Payment Ledger Entry
disagrees with its GL by GHS 2.82M on journals. `ar_total`/`ap_total` are the positive
balances; `ar_open_invoices`/`ap_open_invoices` keep the invoice view. `api/audit.py` is
Check Figures (Settings → Businesses), line by line against the business's ERPNext.

## What covers a promise (15 Nov 2026)

"Promised, not delivered" read as stock promised and not there. `command_center/coverage.py`
works out, per open sales-order line (stock units), what covers it: goods received against
its own purchase order, stock (its warehouse, then any other sold from; oldest promise
first), purchase-order and material-request lines that name the order (linked; MR -> PO ->
receipt or Update Stock invoice -> invoice), then open purchase orders for the same item
linked to no order, raised 14 days before to 90 after the order (likely, each unit once,
oldest promise first, with the reason). States: In Stock, Received, On Order, Requested,
Partly Covered, Not Ordered, Not a Stock Item; Late to Customer, Supplier Late. Read live,
kept per business (speed.py kind "cover"). Shown as "Promised Orders — Cover" on Sales,
Stock and Buying (`api/coverage.py`, `legacy/cover.js`), as "What Covers It" in the
order_book / order_book_late drawers (`Kpi.explained_by`), the rule
`promised_not_ordered` (its params are the window), and the analyst's `order_cover`.
Gigmann (v14) links nothing: no PO or MR names a sales order, and goods are received on
supplier invoices (Update Stock), not Purchase Receipts.

## The question box

**Decision of 18 Oct 2026 (Michael), replacing "Gemini routes; the facts answer":**
Gemini is used to its full capacity for anything informational -- it reads the figures
and records a question needs, reasons over them, explains, compares, projects and
recommends -- and it may never create, edit, submit, cancel or delete anything in
ERPNext, with or without anyone's approval.

**Claude (14 Nov 2026).** `ask/llm.py` picks the provider (`command_center_ai_provider`,
else whichever key exists, Claude first). `ask/claude.py`: official `anthropic` SDK,
Sonnet 5.5 for questions, Opus 5.5 for the deeper look and the reports (`deep=True`),
adaptive thinking with effort medium/high, no forced tool_choice (400 on these models;
the final round uses tool_choice none and the SAME tool list), refusal fallbacks
"default". Key in `command_center_anthropic_key`. The fixed opening (tools, then
`agent.SYSTEM`) carries a 1-hour cache marker; the date, data horizon, business and
currency are in `agent.CONTEXT`, after it -- preflight fails a placeholder in SYSTEM. The
loop in agent.py is one loop for both providers (`_Gemini`, `_Claude` adapters); a reply is
appended unchanged (thinking blocks included) and an instruction after tool results goes
into that unsent turn. `api/ask.check_analyst` proves the cache (second call reads it) and
reports the key's rate limits and questions a minute.

**The analyst** (`ask/agent.py`) runs Gemini (`gemini-3.8-flash` by default -- Google retired
2.5 Flash for new keys on 18 Oct 2026; on a 404 `gemini.py` asks Google for the newest stable
Flash, retries once and remembers it for a day; a model named in `command_center_analyst_model`
is never second-guessed) with the read-only tools in `ask/tools.py`: query any
loaded fact (totals, breakdowns, periods, filters), list records, the KPI figures, name
lookup, trend + straight-line projection, the six original analyses, and any ERPNext
doctype through `frappe.client.get / get_list / get_count` -- Frappe's own
permission-checked reads, so the model sees only what the asking person may see (AI-00).
Credential doctypes are refused outright. Up to eight rounds of tool calls, then a forced
answer. Answers are markdown; projections are labelled "Projection" with their method,
advice "Recommendation". Every call is listed under the answer as "what it checked".

**Why it cannot write, in order of strength:** there is no write tool and the model can
reach only `tools.run`, which dispatches through the `TOOLS` registry; preflight scans
every file on the question path (`ask/`, the KPI engine, the schema) and fails on any
write call; and `agent.py` rolls back any write made while a question is answered, then
logs that it happened (errors are logged after the guard, so it cannot erase them).
`scripts/test_analyst.py` tests the loop, the scope, the budget and the guard offline,
and preflight runs it.

**The floor.** No key, `command_center_ai_mode = router`, or Gemini unreachable: the
original router + six intents answer, as before. `MATCHERS` in `intents.py` routes that
fallback and nothing else.

**The key lives in `site_config.json`, never in the repo.** Set it with
`bench --site <site> set-config command_center_gemini_key "..."`. Preflight scans every
tracked file for anything shaped like a Google API key and fails the build.

**What leaves the site now:** the question and the last four turns; the totals,
breakdowns and records the question needs; ERPNext documents the person may read. That is
what `api/ask.answerable` reports. Gigmann's AI-01 (approval of the provider) and SE-07
(disclosure of data flows to it) are **not yet on record** and are needed before
production use.

## Exports and reports

`api/export.py`: an answer to PDF (Frappe's PDF engine; question escaped, model markdown
sanitised), tables to .xlsx (one sheet each, figures as numbers), and every record
behind a figure to .xlsx (up to 20,000 via `facts._records(cap=...)`; the public
`records` endpoint still caps at 500). A screen goes to PDF through the browser's print
(`@media print` in shell.py, header added by ViewTools.jsx), so the PDF holds exactly
the rendered figures. All reads; files are streamed, no File is written.
`scripts/test_export.py` runs in preflight.

`api/reports.py`: RP-01..RP-09 as briefs to the analyst (16 rounds), run as a job on the
long queue as the asking user. Every run, manual or scheduled, is kept in `Command Center
Report Run` (state, who, the report itself; latest 10 per report per business, pruned
nightly by `insights/core/maintenance.py`), so leaving the Reports screen loses nothing:
the job carries on (in the standalone platform, a thread of the web process with a
30-second heartbeat), the screen fills each "Last run" and View Last Report from
`reports.latest` on load and follows what is still being written, and the bell (Bell.jsx,
`reports.mine`) says "Your ... is ready" to the person who ran it, with a toast if they are
on another screen. A second Run of a report being written returns that run; a run past
its 25-minute deadline fails with the reason; one whose worker died (restart) is picked
up once more by `reports.sweep` (on read, and every five minutes), then failed. A run of a
business that belongs to a customer is seen only by that customer's people and the
administrator. Reopening never meters again.

The analyst reaches the ledger, purchase orders and stock movements through
`run_report` -- 23 allowlisted standard ERPNext reports, run with the asker's
permissions -- rather than new facts.

## Conversations with the AI

Kept on the server, per person, in `Command Center Conversation` (if_owner on every
role, and owner checks in `api/conversations.py`), so they survive a refresh, a sign-out
and another device. `askHistory.js` restores the latest conversation for the business
when the app opens and saves each answered turn (and a deeper look's replacement) in
order. The Ask AI screen lists "Your conversations" to reopen or delete. Only what the
screen needs to redraw a turn is stored -- never the analyst's working -- and the
assistant itself never reads or writes these.

## The product's name

**A setting, not code** (15 Nov 2026): the owner sells the platform under his own
product name, default **Ultrasoft Insights** / "Advanced AI-Powered Business Intelligence for
ERPNext" (owner, 15 Nov 2026), set by
the administrator in Settings → Branding with the logos (light and dark backgrounds,
favicon; PNG/JPEG/WebP checked by content, 1 MB, never SVG, stored in the files folder
under content-hash names, served at `/branding/<name>`) and the vendor's footer (company,
person, email, phone, website -- free text, never hard-coded). A business may carry a
co-brand (display name and logo, "Prepared for ...") from Settings → Businesses → Manage,
and a Report Style (15 Nov 2026): Platform Branding / Client Branding / Client Letterhead
(header and footer images on every page via `export.page_options`, which writes two small
header/footer HTML files of our own to a temp folder and removes them), vendor credit
Show / Small / Hide (Hide: administrator only). PDFs use the Report Logo (`logo_report`),
not the screens' logos. The sign-in page uses the Sign-In Logo (`logo_signin`, 16 Nov
2026), else the built-in `.auth-mark` (interface/auth.py) -- never another logo; its
vendor footer is two quiet lines under the card, each item whole (`branding.public()`
`built_by`, `contacts`). `branding.document(code, own=...)` resolves it; the platform's own
documents (usage statements, incident reports) pass own=True.
`command_center/branding.py` is the one source: every page, the boot payload, every PDF
(`export.brand_header`, `export.pdf_options` -- the vendor's line and "Page X of Y" on
every page), every workbook (`export.brand_rows_head/foot`) and every email
(`branding.email_html`) asks it; a new export must too. Reports are tidied by
`api/report_text.py` (no repeated title, no emoji or chat, Title Case headings, numbered
recommendations) on the server, so the screen, PDF and email agree. It was **AI Business
Intelligence** from 18 Oct 2026 ("Command Center" read as an aviation term). Internal
names stay: the app `command_center`, the `/command-center`
address, the doctypes and error-log titles. The platform's role was renamed once, with a
migration (patches/rename_manager_role.py, 14 Nov 2026): "Command Center Manager" became
`Insights Dashboard Manager` (shown in the top bar as "Management"). Not "Dashboard
Manager": that is Frappe's own standard role, and anyone holding it would have walked in.
Never rename these without a migration plan.

## Home and the health score

A live figure or panel the business's ERPNext refuses by permission (HTTP 401/403,
`RemotePermissionDenied`, which carries `.doctype` and `.status`) is `no_access`, not
failed (16 Nov 2026): `guides.no_access` names the record type and how to give the
platform's API user read access to it (Issue / Issue Type: Support Team), drawn like
`needs_setup` (guide.js `GUIDE_STATES`). An alert's age is its oldest item's ("oldest
over 2 years", `alerts/engine.elapsed`); a rule with no `since` shows none.

Home follows the approved mockup (`gigmann-redesign/home.html`, 18 Oct 2026): three hero
tiles (TILE_KPIS.command), the morning brief (the alert engine's top three), largest
amounts owed (`api/home.debtors`, All / Overdue / Over 90 days), two counts, the business
health gauge and top customers (`api/home.top_customers`, last twelve full months), then
the six cards and the alerts. `legacy/home.js` fills it. The health figure is the plain
average of three stated ratios -- `score_paid` (owed inside 90 days / owed),
`score_deliver` (promised stock lines covered / promised), `score_paperwork` (invoices
issued / written) -- and "How it is scored" lists each with its note. The same three
draw Business Health's first three tiles. Approvals, record quality and access are not
scored until their data exists; never fill them with a number.

Business Health is a check-up report (16 Nov 2026, `mockup-health.html`): the verdict (a
ring with Control Health as a percentage, "▲/▼ N on last week", one sentence), then the six
questions as ruled findings, worst first, each with what it was counted from, an
eight-week strip, the score now and Act / Watch / Healthy / Waiting / No Access. Every
score shows as a percentage, never "/100". `command_center/health.py` owns the history:
`Command Center Health Snapshot`, one row per business per day (named
`<business>::<day>`; the latest complete read of the day wins, a read where ERPNext was away
never replaces it), written by `api/kpi.get` whenever all seven figures are read and by the
daily `health.record_all`; `api/health.history` gives the last eight ISO weeks (the last
snapshot in each; an empty week stays empty) and the delta; pruned at 400 days
(`health_snapshot_days`, insights/core/maintenance.py). "Counted from" uses the count the
figure divides by (`health.COUNTED`: the engine denominator, or a live score's fifth
element), else what it was read from, never a number made up. `insights/tests.py`
`HEALTH_INVENTORY` is the parity check: everything the screen had before must stay.

## Buttons on the designed screens

`frontend/src/legacy/actions.js` gives every designed button a handler after each render
(the "⋯" menus called a `moreMenu()` that only the first prototype defined, so Assign and
every menu item did nothing until 18 Oct 2026). Assign, Request evidence, Escalate, Raise
it, Give it an owner, Pass to someone else and Ask for more open `ActionDialog.jsx`, which
hands the work out in the business's ERPNext as the manager (`api/actions.create_task`) and
tells the person there (16 Nov 2026): about one ERPNext document (an alert whose records are
exactly one, `facts.single_document`), ERPNext's own `frappe.desk.form.assign_to.add` --
To-Do, Assigned To, comment, Assignment notification; in a project, a Task assigned the same
way; about no single document, a To-Do (`assigned_by`, no reference: a platform doctype is
not a valid link there) and a mention on it through `frappe.desk.form.utils.add_comment`
(no role may create a Notification Log). The dialog says which before sending and whether
they were notified after; a refused notification is reported, never raised. The assistant
never calls it. Approve/Reject/Accept/Send back on the sample requests say they are samples.
Defer, Dismiss and Approve inside an alert's menu are removed until an alert engine can
remember a decision. A new button label needs a handler there, or preflight fails.

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
| Designed KPI cards | 68, of which **51 are live** (18 Oct 2026; 14 read straight from ERPNext via kpi/live.py) |
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
2. ~~**Relative date filters**~~ Done: `Kpi.period` (last_full_month, last_full_months_n,
   last_days_n), measured back from the last date in the KPI's own fact and written into
   its drill filters. ~~**Max-over-groups**~~ Done: `agg="top"` with `group_by` (a
   dimension or `month:<date>`), `top_n`, `order`, `as_share`, `negate`; also `avg` and
   `max`. Notes may say `{period}` and `{group}`. Tested offline by
   `scripts/test_kpi.py` (in preflight). 23 cards wired with them on 18 Oct 2026.
4. **Two more facts**: purchase orders (235 on the site) and stock movements. Meanwhile
   `kpi/live.py` reads what the facts do not hold straight from ERPNext (users and
   roles, the Version log, purchase orders), in the engine's figure shape, drilling to
   the ERPNext list. Waits are measured to the purchase orders' own last date.
5. **Fill the 54 illustrative cards**, money screens first, then operational.
6. **The 78 static drawers** — decide prose-or-live for each, and record the decision.
7. **The 4 `unwired` placeholders.**
8. ~~**Task and approval engine**~~ Done for this site (18 Oct 2026): `api/work.py`
   reads ERPNext's own records -- documents whose workflow has a step this user may take
   (`frappe.model.workflow.get_transitions`, so roles, self-approval and conditions are
   the site's), and the To-Dos they assigned (`assigned_by`, set by create_task).
   `legacy/work.js` replaces the sample cards on Approvals, Today and Outstanding Tasks
   and hydrates their tiles (WORK_TILES). Decisions go through ActionDialog: approve /
   reject = `actions.apply_workflow_action`; accept = tag "Accepted"; send back = reopen
   with the reason as a comment (`work.review`). Not yet: "Reopened twice+" (needs To-Do
   history), connected peers' queues, Executive Summary.
9. ~~**Reports**~~ — written by the analyst on Run, PDF/Excel export (18 Oct 2026).
   ~~Schedule and email~~ Done (18 Oct 2026): `Command Center Report Schedule` (one per
   report per business; daily/weekly/monthly at an hour), set from the Reports screen
   (ScheduleDialog.jsx) or the desk. `reports.send_due` (hourly) queues what is due;
   `send_scheduled` writes it with the setter's permissions and emails the PDF
   (`export.pdf_bytes`) via frappe.sendmail. Recipients must be enabled System Users of
   the site; the board report (rp04) cannot be scheduled. Needs workers and an outgoing
   email account on the site.
10. ~~**Refresh control and load history on Business Health**~~ Done (18 Oct 2026):
    every load writes a `Command Center Load Log` row (kept 90 days; a missing table never
    fails a load); `ingest.history` and `ingest.refresh` (incremental, in the request)
    feed `legacy/loads.js`'s panel. The headline "Control health" is the same average as
    Home's gauge; the live alerts replace the designed ones there too.
11. ~~**Click-through audit**~~ Done in the preview (18 Oct 2026): a script clicked all
    276 cards, tiles, buttons, chips and links on the 19 screens. It found go(), ask2(),
    tab() and moreMenu() called inline but never installed on window (25 navigations
    dead), and ~40 cards generated with onclick="po" (a bare explainer key) instead of
    explain('po'). Both fixed and now guarded in preflight. Not yet clicked on the live
    site.
12. ~~**Alert engine**~~ Done (18 Oct 2026): `command_center/alerts/` -- seven rules over
    the KPIs (so an alert and its card agree), thresholds in `Command Center Alert Rule`
    (editable in the desk, AL-05), alerts in `Command Center Alert` with the lifecycle
    raised/acknowledged/actioned/deferred/dismissed/false positive/resolved (AL-06).
    Evaluated hourly and on read when stale (no worker needed). `legacy/alerts.js` puts
    them in Home and the Executive Summary; the bell lists them. Assign/evidence/escalate
    hand the work out as above, naming the alert in the description; defer/dismiss/not-a-problem need a reason. The
    two doctypes need `bench migrate` on deploy. Not yet: per-record alerts (one per
    invoice), Business Health's and Risk's own alerts, the other six §9 types.
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

## The standalone platform (branch `standalone`, from 14 Nov 2026)

Michael's decision: the intelligence layer is its own service, not a Frappe site and
not an app on a client's ERPNext. `insights/` is a Django project (PLATFORM.md):
- `insights/compat` answers to the name `frappe` so `command_center/` runs unchanged.
  Extend it there when the business logic needs a Frappe call it does not have yet;
  never install Frappe, never fork the business logic into a second copy.
- Models are GENERATED from the doctype JSON (`python -m insights.tools.gen_models`,
  then `manage.py makemigrations core`); never edit models_generated.py by hand.
- People are Django users (username = email); managers hold the group "Insights
  Dashboard Manager"; the administrator is a superuser (seen as "System Manager").
- Secrets: encrypted in core.Secret with `encryption_key` from insights.json.
- `manage.py test insights` (in preflight) is the end-to-end check; keep it passing.
