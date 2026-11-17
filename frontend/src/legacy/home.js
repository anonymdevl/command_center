/**
 * Home, in the approved mockup's layout, on real figures -- and the Business Health
 * score tiles, which share the gauge's three questions.
 *
 *   Hero tiles          TILE_KPIS.command (hydrate.js)
 *   Morning brief       the alert engine's top three (api/alerts.py)
 *   Largest amounts     api/home.debtors -- All, Overdue, Over 90 days
 *   Counts              cases_open, tasks_overdue
 *   Business health     control_score: the plain average of the six Business Health
 *                       questions that can be scored (kpi score_* and live_governance
 *                       score_*), as a percentage. "How it is scored" lists each with
 *                       its note, so 47% is never a number nobody can explain.
 *   Top customers       api/home.top_customers -- share of the last twelve full months
 *
 * Built as DOM, never HTML from the server. Each part fills its own slot and leaves the
 * rest alone, so one failed read is one empty panel with a reason, not a broken screen.
 */

import { api } from "../api/client.js";
import { count, exact, money, shortDate } from "../format.js";
import { GUIDE_STATES, guideBox, guideWords, hasGuide } from "./guide.js";
import { WAITING } from "./reach.js";
import { fold, reveal } from "./fold.js";

const SCORES = [
  ["score_deliver", "Delivering what we sold", "Can we deliver what we sold?"],
  ["score_paid", "Getting Paid", "Are we getting paid?"],
  ["score_paperwork", "Paperwork finished", "Is the paperwork finished?"],
  ["score_approvals", "The right people approving", "Were the right people asked?"],
  ["score_records", "Clean records", "Are our records clean?"],
  ["score_access", "Separate duties", "Who can see what?"],
];
/** Business Health's question tile label -> its figure. */
export const HEALTH_QUESTIONS = Object.fromEntries(SCORES.map(([k, , q]) => [q, k]));
const WORDS = { crit: "Critical", high: "High", med: "Medium", info: "For information" };

export function renderHome(root, { figures, alerts, scope, onOpen }) {
  if (!root?.querySelector("#mbrief")) return;
  if (alerts) brief(root, alerts);
  if (figures) {
    setText(root, "#cnt-cases", figures.cases_open ? count(figures.cases_open.value) : "—");
    setText(root, "#cnt-late", figures.tasks_overdue ? count(figures.tasks_overdue.value) : "—");
    gauge(root, figures);
  }
  debts(root, scope, onOpen);
  customers(root, scope, onOpen);
}

/** Business Health, as a check-up report: the verdict (Control Health, the change on last
 *  week, one plain sentence), then the six questions as ruled findings, worst first --
 *  each with what it was counted from in ERPNext, its last eight weeks and a status.
 *  The figures are the same as Home's gauge; the weeks are the stored daily snapshots
 *  (api/health.history; the last one in each ISO week). A question not scored yet says
 *  why on its row -- a guide to set it up or to give access, "waiting for ERPNext", or
 *  "could not be read" -- never a sample score. A row opens its guide, and only that. */
export function renderHealthTiles(root, figures, { openDrawer, scope } = {}) {
  if (!root || !figures) return 0;
  if (hist.scope !== scope) Object.assign(hist, { scope, data: null, failed: false, figures: null });
  const live = drawHealth(root, figures, openDrawer);
  // Each read of the figures has just stored today's snapshot (api/kpi.get), so the
  // weeks are asked for after it, once per read.
  if (hist.figures !== figures) {
    hist.figures = figures;
    const seq = ++hist.seq;
    api.healthHistory(scope)
      .then((d) => {
        if (seq !== hist.seq) return;
        Object.assign(hist, { data: d, failed: false });
        if (document.body.contains(root)) drawHealth(root, figures, openDrawer);
      })
      .catch(() => {
        if (seq !== hist.seq) return;
        Object.assign(hist, { data: null, failed: true });
        if (document.body.contains(root)) drawHealth(root, figures, openDrawer);
      });
  }
  return live;
}

const hist = { scope: undefined, data: null, failed: false, figures: null, seq: 0 };
const ORDER = Object.fromEntries(SCORES.map(([k], i) => [k, i]));
const WORDS_N = ["no", "one", "two", "three", "four", "five", "six"];

/** Act / Watch / Healthy: the tiles' tones (toneOf), High and Critical both being Act. */
function band(score) {
  if (score >= 80) return { key: "ok", word: "Healthy", flag: "f-ok" };
  if (score >= 60) return { key: "med", word: "Watch", flag: "f-med" };
  return { key: "crit", word: "Act", flag: "f-crit" };
}

/** What a question's figure says: scored, or why not (the states the tiles had). */
function standing(f) {
  if (f && f.value !== null && f.value !== undefined) {
    const score = Math.round(Number(f.value));
    return { scored: true, score, band: band(score) };
  }
  const state = f?.data_status?.state;
  const why = GUIDE_STATES.has(state) ? guideWords(state).foot
    : state === "unreachable" ? WAITING.line
      : state === "failed" || !f ? "Could not be read just now" : "Nothing to score yet";
  if (state === "no_access") return { scored: false, access: true, pill: "No Access", flag: "f-high", why };
  // Read, and there was nothing to score (e.g. nothing owed): not waiting on anything.
  if (why === "Nothing to score yet") {
    return { scored: false, access: false, idle: true, pill: "Nothing to Score", flag: "f-dim", why };
  }
  return { scored: false, access: false, pill: "Waiting", flag: "f-dim", why };
}

function pct(v) {
  return `${Math.round(Number(v))}%`;
}

function cap(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

function drawHealth(root, figures, openDrawer) {
  const data = hist.data;
  const series = data?.weeks || [];
  // What "on last week" is measured from: the server's reading nearest seven days before the
  // latest, over the questions scored both times (health.week_on_week), with that week's
  // question scores from the series for the sentence -- never simply the previous square.
  const lw = data?.last_week || null;
  const lastWeek = lw ? { ...(series.find((w) => w.week === lw.week) || {}), ...lw } : null;
  const rows = SCORES.map(([key, , q]) => ({ key, q, f: figures[key], s: standing(figures[key]) }));
  verdict(root, figures, rows, lastWeek, data);
  let live = 0;
  const list = root.querySelector("#hh-rows");
  const nodes = {};
  root.querySelectorAll(".hh-row[data-q]").forEach((row) => {
    nodes[row.dataset.q] = row;
  });
  rows.forEach((r) => {
    const row = nodes[r.key];
    if (!row) return;
    if (r.s.scored) live += 1;
    finding(row, r, series, openDrawer);
  });
  // Worst first: the lowest scores, then those needing access, then those waiting.
  const rank = (r) => (r.s.scored ? r.s.score : r.s.access ? 1000 : 2000) * 10 + ORDER[r.key];
  if (list) [...rows].sort((a, b) => rank(a) - rank(b)).forEach((r) => nodes[r.key] && list.append(nodes[r.key]));
  const legend = root.querySelector("#hh-legend");
  if (legend) {
    legend.textContent = hist.failed
      ? "The weekly history could not be read just now; this week's square is the reading above."
      : !data?.kept && data
        ? "The weekly history is kept for each business; choose one business to see its weeks."
        : "Each square is one week, the last reading that week, oldest on the left; an outlined "
          + "square is a week with nothing stored yet.";
  }
  return live;
}

/** The ring, the change on last week, the sentence and the count of questions answered. */
function verdict(root, figures, rows, lastWeek, data) {
  const total = figures.control_score;
  const has = total && total.value !== null && total.value !== undefined;
  const score = has ? Math.round(Number(total.value)) : null;
  ring(root.querySelector("#hh-ring"), score);
  const head = root.querySelector("#hh-score");
  if (head) {
    head.textContent = "";
    if (has) head.append(el("span", null, String(score)), el("small", null, "%"));
    else head.textContent = "—";
  }
  const delta = root.querySelector("#hh-delta");
  const before = lastWeek?.control_score;
  if (delta) {
    if (has && before !== null && before !== undefined) {
      const d = data?.delta !== null && data?.delta !== undefined
        ? Math.round(Number(data.delta)) : score - Math.round(Number(before));
      delta.hidden = false;
      delta.className = `hh-delta ${d > 0 ? "up" : d < 0 ? "dn" : "eq"}`;
      delta.textContent = d > 0 ? `▲ ${d} on last week` : d < 0 ? `▼ ${-d} on last week` : "No change on last week";
      const over = data?.delta_questions;
      delta.title = `Overall Business Health was ${pct(before)} on ${shortDate(lastWeek.day)}`
        + (over && over.questions < over.of ? `, compared over the ${over.questions} of ${over.of} questions scored both times.` : ".");
    } else {
      delta.hidden = true;
      delta.textContent = "";
    }
  }
  const trend = root.querySelector("#hh-trend");
  if (trend) {
    const note = (total?.note || "").replace(/^out of 100:\s*/i, "").trim();
    trend.textContent = note ? `Overall Business Health is ${note}.`.replace(/\.\.$/, ".") : " ";
  }
  const tally = root.querySelector("#hh-count");
  if (tally) {
    tally.textContent = "";
    const answered = rows.filter((r) => r.s.scored).length;
    const access = rows.filter((r) => !r.s.scored && r.s.access).length;
    const idle = rows.filter((r) => !r.s.scored && r.s.idle).length;
    const waiting = rows.length - answered - access - idle;
    const part = (n, rest) => {
      const p = el("span");
      p.append(el("b", null, String(n)), document.createTextNode(` ${rest}`));
      tally.append(p);
    };
    part(answered, `of ${rows.length} answered`);
    if (waiting) part(waiting, "waiting");
    if (idle) part(idle, "nothing to score");
    if (access) part(access, access === 1 ? "needs access" : "need access");
  }
  say(root, rows, lastWeek, !!data);
}

/** "One thing is going badly, and it is getting worse: ..." -- the questions scoring
 *  under 60, worst first, and whether each is lower than the score stored last week. */
function say(root, rows, lastWeek, historyRead) {
  const box = root.querySelector("#hh-say");
  if (!box) return;
  const scored = rows.filter((r) => r.s.scored);
  box.textContent = "";
  if (!scored.length) {
    box.textContent = "Not enough is recorded yet to score any of the six questions.";
    return;
  }
  const bad = scored.filter((r) => Number(r.f.value) < 60).sort((a, b) => a.f.value - b.f.value);
  const words = ["Nothing is", "One thing is", "Two things are", "Three things are", "Four things are",
    "Five things are", "Six things are"];
  if (!bad.length) {
    box.textContent = `${words[0]} going badly among the ${scored.length} questions scored.`;
    return;
  }
  const one = bad.length === 1;
  let trend = "";
  let since = "";
  if (historyRead) {
    const prev = lastWeek?.questions || {};
    const known = bad.filter((r) => prev[r.key]?.value !== null && prev[r.key]?.value !== undefined);
    const worse = known.filter((r) => r.s.score < Math.round(Number(prev[r.key].value)));
    if (!known.length) {
      since = ` No earlier week is stored yet to say whether ${one ? "it is" : "they are"} getting worse.`;
    } else if (!worse.length) {
      trend = one ? ", and it is not getting worse" : ", and none is lower than last week";
    } else if (worse.length === bad.length) {
      trend = one ? ", and it is getting worse" : `, and ${bad.length === 2 ? "both" : "all of them"} are getting worse`;
    } else {
      trend = `, and ${WORDS_N[worse.length]} of them ${worse.length === 1 ? "is" : "are"} getting worse`;
    }
  }
  box.append(document.createTextNode(`${words[bad.length]} going badly${trend}: `));
  bad.forEach((r, i) => {
    box.append(el("b", null, r.q), document.createTextNode(
      ` — ${r.s.score}% ${r.f.note || ""}`.trimEnd() + (i < bad.length - 1 ? ". " : ".")));
  });
  if (since) box.append(el("span", "hh-since", since));
}

/** One ruled finding: status square, the question, what it found and what it was
 *  counted from, its eight weeks, the score now and its status. */
function finding(row, r, series, openDrawer) {
  const { f, s, q } = r;
  row.dataset.live = "1";
  row.dataset.state = s.scored ? s.band.key : s.access ? "access" : "wait";
  row.querySelector(".hh-sq").className = `hh-sq ${s.scored ? `b-${s.band.key}` : "b-none"}`;
  const n = row.querySelector(".hh-n");
  const src = row.querySelector(".hh-src");
  const now = row.querySelector(".hh-now");
  const pill = row.querySelector(".hh-status");
  if (s.scored) {
    n.textContent = f.note ? `${s.score}% ${f.note}` : `${s.score}%`;
    src.textContent = cap(f.counted_from || "");
    now.textContent = "";
    now.append(el("span", null, String(s.score)), el("small", null, "%"));
    pill.className = `flag ${s.band.flag} hh-status`;
    pill.textContent = s.band.word;
    row.title = "One stated ratio: " + (f.note ? `${s.score}% ${f.note}.` : `${s.score}%.`);
  } else {
    n.textContent = f?.note || (f ? "nothing to score yet" : "could not be read just now");
    src.textContent = [s.why, cap(f?.counted_from || "")].filter(Boolean).join(" · ");
    now.textContent = "—";
    pill.className = `flag ${s.flag} hh-status`;
    pill.textContent = s.pill;
    row.removeAttribute("title");
  }
  strip(row.querySelector(".hh-strip"), r, series);
  // A question opens nothing unless it has a guide to show: no click, no hover.
  row.classList.remove("clickable");
  row.onclick = null;
  row.onkeydown = null;
  row.removeAttribute("role");
  row.removeAttribute("tabindex");
  if (!s.scored && hasGuide(f) && openDrawer) {
    const open = () => openDrawer({ node: guideDrawer(q, f.data_status.guide) });
    row.classList.add("clickable");
    row.setAttribute("role", "button");
    row.setAttribute("tabindex", "0");
    row.onclick = open;
    row.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open();
      }
    };
  }
}

/** Eight squares, oldest first, each tinted by that week's band; this week's is the
 *  reading on screen. A week with nothing stored is an outlined, empty square. */
function strip(box, r, series) {
  if (!box) return;
  const squares = [...box.querySelectorAll(".hh-wk")];
  const n = squares.length;
  const weeks = series.length === n ? series : Array.from({ length: n }, (_, i) => series[i - (n - series.length)] || null);
  let stored = 0;
  squares.forEach((sq, i) => {
    const wk = weeks[i];
    const mine = i === n - 1;
    let v = wk?.questions?.[r.key]?.value;
    if (mine && r.s.scored) v = r.s.score;
    const when = wk?.start ? `Week of ${shortDate(wk.start)}` : mine ? "This week" : "An earlier week";
    if (v === null || v === undefined) {
      sq.className = "hh-wk";
      sq.title = wk?.day ? `${when}: not scored` : `${when}: nothing stored`;
      return;
    }
    stored += 1;
    const b = band(Math.round(Number(v)));
    sq.className = `hh-wk b-${b.key}${mine ? " now" : ""}`;
    sq.title = `${when}: ${pct(v)} · ${b.word}`;
  });
  box.setAttribute("aria-label", stored
    ? `Last eight weeks: ${stored} with a score, ${n - stored} with nothing stored`
    : "Last eight weeks: nothing stored yet");
}

function guideDrawer(title, guide) {
  const wrap = el("div", "guide-drawer");
  wrap.append(el("h3", null, title));
  wrap.append(guideBox(guide));
  return wrap;
}

/* ------------------------------------------------------------------ morning brief */
function brief(root, data) {
  const list = (data.alerts || []).slice(0, 3);
  const h = root.querySelector("#mb-h");
  const chips = root.querySelector("#mb-chips");
  if (!h || !chips) return;
  const words = ["Nothing", "One thing", "Two things", "Three things"];
  h.textContent = list.length
    ? `${words[list.length]} need${list.length === 1 ? "s" : ""} your attention today`
    : "Nothing material needs your attention today";
  chips.textContent = "";
  list.forEach((a) => {
    const c = el("button", `mb-chip ${a.severity}`);
    c.type = "button";
    c.title = `${WORDS[a.severity] || ""}: ${a.title}`;
    c.append(el("b", null, figureText(a)), document.createTextNode(` ${(a.label || a.rule).toLowerCase()}`));
    c.onclick = () => reveal(`alert-${a.name}`, "alert-flash");
    chips.append(c);
  });
}

function figureText(a) {
  if (a.figure === null || a.figure === undefined) return "";
  if (a.figure_unit === "currency") {
    const m = money(a.figure, a.currency || "");
    return `${m.currency} ${m.figure}${m.suffix}`.trim();
  }
  return count(Math.round(a.figure));
}

/* ------------------------------------------------------------------ largest amounts owed */
/**
 * Which band (All, Overdue, Over 90 days) the list shows is kept on the panel itself, not
 * in this module (17 Nov 2026): a module-level choice outlived the screen, so on the way
 * back to Home the designed "All" tab was highlighted over the overdue rows. A new panel
 * starts from the tab its markup marks on; each read is numbered per panel and only the
 * latest is drawn, as is the business it was read for.
 */
const debtSeq = new WeakMap();

function debts(root, scope, onOpen) {
  const panel = root.querySelector("#debt");
  if (!panel) return;
  if (!panel.dataset.wired) {
    panel.dataset.wired = "1";
    panel.dataset.mode = panel.querySelector(".segc button.on")?.dataset.mode || "all";
    panel.querySelectorAll(".segc button").forEach((b) => {
      b.onclick = () => {
        panel.dataset.mode = b.dataset.mode;
        showMode(panel);
        loadDebts(panel, panel.dataset.scope, onOpen);
      };
    });
    showMode(panel);
  }
  const mode = panel.dataset.mode;
  if (panel.dataset.scope === scope && (panel.dataset.loaded === mode || panel.dataset.asking === mode)) return;
  panel.dataset.scope = scope;
  loadDebts(panel, scope, onOpen);
}

/** The highlighted tab is the band the rows are for. */
function showMode(panel) {
  panel.querySelectorAll(".segc button").forEach((x) => {
    const on = x.dataset.mode === panel.dataset.mode;
    x.classList.toggle("on", on);
    x.setAttribute("aria-selected", on ? "true" : "false");
  });
}

function loadDebts(panel, scope, onOpen) {
  const seq = (debtSeq.get(panel) || 0) + 1;
  debtSeq.set(panel, seq);
  const rows = panel.querySelector("#debt-rows");
  const mode = panel.dataset.mode || "all";
  panel.dataset.asking = mode;
  delete panel.dataset.loaded;
  // The rows on show are for the band before: while this one is read, none are.
  rows.textContent = "";
  rows.append(el("div", "home-wait", "Reading Accounts Receivable…"));
  const latest = () => debtSeq.get(panel) === seq && panel.dataset.scope === scope
    && document.body.contains(panel);
  api.homeDebtors({ business_code: scope, mode })
    .then((d) => {
      if (!latest()) return;
      delete panel.dataset.asking;
      panel.dataset.loaded = mode;
      // By the ledger: how many customers owe, not how many invoices are open.
      setText(panel, "#debt-n", `${count(d.customers)} customer${d.customers === 1 ? "" : "s"}`);
      rows.textContent = "";
      if (!d.rows.length) {
        rows.append(el("div", "home-wait", mode === "all" ? "No customer has a Customer Ledger Balance." : "Nothing in this band."));
        return;
      }
      d.rows.forEach((r) => rows.append(debtRow(r, d.currency, onOpen)));
      if (d.customers > d.rows.length) {
        rows.append(el("div", "debt-more", `The largest ${d.rows.length} of ${count(d.customers)} customers, `
          + `${money(d.owed, d.currency || "").currency} ${exact(d.owed, { decimals: 0 })} in all`));
      }
    })
    .catch((e) => {
      if (!latest()) return;
      delete panel.dataset.asking;
      rows.textContent = "";
      rows.append(el("div", "home-wait", `The receivables could not be read: ${e?.message || "no reply"}`));
    });
}

/* One row (legacy/fold.js): the customer, the Customer Ledger Balance and how long it
   has waited. Invoice Outstanding, the open invoices and the last payment open under it,
   as the button that opens the customer's Customer Ledger Balance. */
function debtRow(r, currency, onOpen) {
  const row = el("div", "debt-row");
  const who = el("span", "debt-who");
  who.append(el("span", "av2", initials(r.customer)));
  const name = el("span", "debt-name");
  name.append(el("b", null, r.customer));
  who.append(name);
  const days = el("span", `dpill ${r.days > 90 ? "crit" : r.days > 30 ? "high" : "ok"}`,
    r.days > 0 ? `${count(r.days)} days` : "not yet due");
  // What the ledger says is really owed. On the row its label is the column heading; on
  // the narrowest screens, where the heading is not shown, it is in the expansion
  // (shell.py, FOLDED ROWS).
  const owed = () => {
    const o = el("span", "debt-a");
    const fig = el("b");
    if (currency) fig.append(el("span", "cx", currency), document.createTextNode(" "));
    fig.append(document.createTextNode(exact(r.owed, { decimals: 0 })));
    o.append(fig, el("small", null, `Customer Ledger Balance${currency ? `, ${currency}` : ""}`));
    return o;
  };

  const open = el("button", "debt-open");
  open.type = "button";
  open.dataset.ccWired = "1";
  open.title = `Open ${r.customer}'s Customer Ledger Balance`;
  const inv = el("span", "debt-a");
  // What the open invoices say, beside what the ledger says is owed.
  inv.append(el("b", null, exact(r.on_invoices ?? r.invoiced, { decimals: 0 })), el("small", null, "Invoice Outstanding"));
  const narrow = owed();
  narrow.classList.add("fold-fig-x");
  open.append(inv, narrow,
    el("span", "debt-inv", `${count(r.invoices)} open invoice${r.invoices === 1 ? "" : "s"}`
      + (r.last_paid ? ` · last paid ${shortDate(r.last_paid)}` : " · no payment on record")),
    el("span", "debt-arrow", "→"));
  open.onclick = () => onOpen?.({ label: `${r.customer}: Customer Ledger Balance`, drill: r.drill });
  return fold(row, { key: `debt:${r.customer}`, head: [who, owed(), days], body: [open] });
}

/* ------------------------------------------------------------------ top customers */
/** Read once per panel and business; each read numbered per panel, and only the latest --
 *  for the business still shown -- is drawn, as the receivables list does (17 Nov 2026:
 *  a slower earlier read could land last and draw the previous business's customers). */
const custSeq = new WeakMap();

function customers(root, scope, onOpen) {
  const panel = root.querySelector("#topc");
  if (!panel) return;
  if (panel.dataset.scope === scope && (panel.dataset.loaded || panel.dataset.asking)) return;
  panel.dataset.scope = scope;
  panel.dataset.asking = "1";
  delete panel.dataset.loaded;
  const seq = (custSeq.get(panel) || 0) + 1;
  custSeq.set(panel, seq);
  const latest = () => custSeq.get(panel) === seq && panel.dataset.scope === scope
    && document.body.contains(panel);
  api.topCustomers({ business_code: scope })
    .then((d) => {
      if (!latest()) return;
      delete panel.dataset.asking;
      panel.dataset.loaded = "1";
      const list = panel.querySelector("#topc-l");
      const bar = panel.querySelector("#topc-bar");
      list.textContent = "";
      bar.textContent = "";
      if (d.period?.label) setText(panel, "#topc-sub", `Share of sales, ${d.period.label}`);
      if (!d.rows.length) {
        list.append(el("li", "home-wait", "No invoiced sales in the last twelve months of data."));
        return;
      }
      d.rows.forEach((r, i) => {
        const seg = el("i", `c${i}`);
        seg.style.width = `${r.share}%`;
        seg.title = `${r.customer}: ${r.share}%`;
        bar.append(seg);
        const li = el("li");
        const b = el("button", "topc-row");
        b.type = "button";
        b.append(el("span", "av2", initials(r.customer)), el("span", `topc-dot c${i}`),
          el("span", "topc-name", r.customer), el("span", "topc-pct", `${r.share.toFixed(0)}%`));
        b.title = `${r.customer}: ${d.currency || ""} ${exact(r.sold, { decimals: 0 })}`;
        b.onclick = () => onOpen?.({ label: `${r.customer}: sales, ${d.period.label}`, drill: r.drill });
        li.append(b);
        list.append(li);
      });
    })
    .catch((e) => {
      if (!latest()) return;
      delete panel.dataset.asking;
      const list = panel.querySelector("#topc-l");
      list.textContent = "";
      list.append(el("li", "home-wait", `The sales could not be read: ${e?.message || "no reply"}`));
    });
}

/* ------------------------------------------------------------------ gauge */
function gauge(root, figures) {
  const box = root.querySelector("#gauge-v");
  if (!box) return;
  const parts = SCORES.map(([k, label]) => ({ key: k, label, f: figures[k] }))
    .filter((p) => p.f && p.f.value !== null && p.f.value !== undefined);
  const total = figures.control_score;
  box.textContent = "";
  if (!parts.length || !total || total.value === null || total.value === undefined) {
    box.append(el("div", "home-wait", total?.data_status?.state === "unreachable"
      ? `${WAITING.line} before scoring.` : "Not enough data to score yet."));
    return;
  }
  const score = Math.round(Number(total.value));
  const worst = parts.reduce((a, b) => (Number(a.f.value) <= Number(b.f.value) ? a : b));
  const tone = toneOf(score);
  box.append(dial(score, tone.color));
  const mid = el("div", "gauge-mid");
  mid.append(el("b", null, String(score)), el("small", null, "%"));
  box.append(mid);
  box.append(el("div", "gauge-say", `${tone.say} — ${worst.label.toLowerCase()} is the drag`));

  const how = root.querySelector("#gauge-how");
  const list = root.querySelector("#gauge-parts");
  if (list) {
    list.textContent = "";
    parts.forEach((p) => {
      const li = el("li");
      li.append(el("b", null, `${Math.round(p.f.value)}%`), el("span", null, `${p.label}: ${Math.round(p.f.value)}% ${p.f.note || ""}`));
      list.append(li);
    });
    const missing = SCORES.length - parts.length;
    list.append(el("li", "gauge-note", `The plain average of these ${parts.length}.`
      + (missing ? ` ${missing} of the six questions cannot be scored yet; Business Health says why.` : "")));
  }
  if (how && !how.dataset.wired) {
    how.dataset.wired = "1";
    how.onclick = () => {
      const open = list.hidden;
      list.hidden = !open;
      how.setAttribute("aria-expanded", String(open));
      how.textContent = open ? "Hide How It Is Scored" : "How It Is Scored";
    };
  }
}

/** Business Health's ring: Control Health as a share of a full circle. Drawn once, then
 *  only its arc changes; with no score it is the empty track. */
function ring(box, score) {
  if (!box) return;
  const NS = "http://www.w3.org/2000/svg";
  const R = 52;
  const len = 2 * Math.PI * R;
  let svg = box.querySelector("svg");
  if (!svg) {
    svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 120 120");
    svg.setAttribute("aria-hidden", "true");
    [["hh-track", 0], ["hh-arc", 1]].forEach(([cls]) => {
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("class", cls);
      c.setAttribute("cx", "60");
      c.setAttribute("cy", "60");
      c.setAttribute("r", String(R));
      c.setAttribute("fill", "none");
      c.setAttribute("stroke-width", "7");
      if (cls === "hh-arc") {
        c.setAttribute("stroke-linecap", "round");
        c.setAttribute("transform", "rotate(-90 60 60)");
      }
      svg.append(c);
    });
    box.prepend(svg);
  }
  const arc = svg.querySelector(".hh-arc");
  const on = score === null ? 0 : Math.max(0, Math.min(100, score)) / 100 * len;
  arc.setAttribute("stroke-dasharray", `${on.toFixed(1)} ${len.toFixed(1)}`);
  arc.style.display = on > 0 ? "" : "none";
  box.setAttribute("role", "img");
  box.setAttribute("aria-label", score === null ? "Overall Business Health: not scored yet" : `Overall Business Health ${score}%`);
}

function dial(score, color) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 220 140");
  svg.setAttribute("class", "dial");
  svg.setAttribute("aria-hidden", "true");
  const ticks = 44;
  for (let i = 0; i < ticks; i++) {
    const a = Math.PI * (1.1 - (1.2 * i) / (ticks - 1));
    const on = i / (ticks - 1) <= score / 100;
    const line = document.createElementNS(NS, "line");
    line.setAttribute("x1", String(110 + Math.cos(a) * 78));
    line.setAttribute("y1", String(118 - Math.sin(a) * 78));
    line.setAttribute("x2", String(110 + Math.cos(a) * 98));
    line.setAttribute("y2", String(118 - Math.sin(a) * 98));
    line.setAttribute("stroke", on ? `var(--${color})` : "var(--line2)");
    line.setAttribute("stroke-width", "4");
    line.setAttribute("stroke-linecap", "round");
    svg.append(line);
  }
  return svg;
}

function toneOf(score) {
  if (score >= 80) return { color: "ok", flag: "f-ok", word: "Healthy", say: "Healthy" };
  if (score >= 60) return { color: "med", flag: "f-med", word: "Watch", say: "Steady" };
  if (score >= 40) return { color: "high", flag: "f-high", word: "High", say: "Under strain" };
  return { color: "crit", flag: "f-crit", word: "Critical", say: "In trouble" };
}

/* ------------------------------------------------------------------ helpers */
function initials(name) {
  return (name || "?").replace(/[^A-Za-z0-9 ]/g, " ").trim().split(/\s+/).slice(0, 2)
    .map((w) => w[0]).join("").toUpperCase() || "?";
}

function setText(root, sel, text) {
  const n = root.querySelector(sel);
  if (n) n.textContent = text;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
