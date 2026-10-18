/**
 * Business Health's "The data behind these figures": when each kind of record was last
 * read from ERPNext, the load history, and a button to refresh now (api/ingest.py).
 *
 * The trust panel belongs here, not on Home: Business Health is where a manager asks
 * whether the figures can be believed, and the first part of that answer is how fresh
 * they are. "Refresh now" loads only what changed since each fact's last run, so it is
 * quick enough to wait for; afterwards the screen's figures are read again.
 */

import { api } from "../api/client.js";
import { count, shortDate } from "../format.js";

export function renderLoads(root, data, { scope, onRefreshed } = {}) {
  const panel = root?.querySelector("#loads");
  if (!panel) return;
  wire(panel, scope, onRefreshed);
  if (!data) return;
  const facts = panel.querySelector("#loads-facts");
  facts.textContent = "";
  if (!data.facts.length) {
    facts.append(el("div", "home-wait", "Nothing has been loaded yet. Press Refresh now to read ERPNext."));
  } else {
    const t = el("table", "dt");
    const head = el("tr");
    ["Records", "Covers up to", "Last read", "Rows last time", ""].forEach((h) => head.append(el("th", null, h)));
    const thead = el("thead");
    thead.append(head);
    const body = el("tbody");
    data.facts.forEach((f) => {
      const tr = el("tr");
      const state = el("span", `tag ${f.status === "OK" ? "t-ok" : f.status === "Failed" ? "t-od" : "t-dr"}`,
        f.status === "OK" ? "Loaded" : f.status === "Failed" ? "Failed" : "Never run");
      if (f.last_error) state.title = f.last_error.slice(-300);
      tr.append(el("td", null, f.what), el("td", null, f.as_of_date ? shortDate(f.as_of_date) : "—"),
        el("td", null, f.last_run ? when(f.last_run) : "never"), el("td", null, count(f.rows_loaded || 0)));
      const last = el("td");
      last.append(state);
      tr.append(last);
      body.append(tr);
    });
    t.append(thead, body);
    const wrap = el("div", "work-table");
    wrap.append(t);
    facts.append(wrap);
    const newest = data.facts.map((f) => f.last_run).filter(Boolean).sort().pop();
    if (newest) setText(panel, "#loads-sub", `Last read from ERPNext ${when(newest)}. The records cover up to `
      + `${shortDate(data.facts.map((f) => f.as_of_date).filter(Boolean).sort().pop()) || "—"}.`);
  }

  const hist = panel.querySelector("#loads-hist");
  hist.textContent = "";
  if (!data.loads.length) {
    hist.append(el("div", "home-wait", "No loads recorded yet."));
    return;
  }
  const ul = el("ul", "loads-list");
  data.loads.forEach((l) => {
    const li = el("li", l.status === "Failed" ? "bad" : "");
    li.append(el("b", null, when(l.started)), el("span", null,
      `${l.what}: ${l.status === "OK" ? `${count(l.rows_loaded)} rows` : "failed"} · ${l.mode.toLowerCase()} · `
      + `${l.trigger === "Person" ? l.run_by || "a person" : "the daily schedule"} · ${l.seconds}s`));
    if (l.error) li.title = l.error.slice(-300);
    ul.append(li);
  });
  hist.append(ul);
}

function wire(panel, scope, onRefreshed) {
  const btn = panel.querySelector("#loads-refresh");
  if (btn && !btn.dataset.ccWired) {
    btn.dataset.ccWired = "1";
    btn.onclick = async () => {
      btn.disabled = true;
      const was = btn.textContent;
      btn.textContent = "Refreshing…";
      panel.querySelector(".loads-msg")?.remove();
      try {
        const r = await api.ingestRefresh(scope);
        const rows = (r?.loaded || []).reduce((n, x) => n + (x.rows || 0), 0);
        note(panel, rows ? `Read ${count(rows)} changed records from ERPNext.` : "Nothing had changed since the last read.");
        onRefreshed?.();
      } catch (e) {
        note(panel, `The refresh did not finish: ${e?.message || "no reply"}`, true);
      } finally {
        btn.disabled = false;
        btn.textContent = was;
      }
    };
  }
  const more = panel.querySelector("#loads-more");
  if (more && !more.dataset.ccWired) {
    more.dataset.ccWired = "1";
    more.onclick = () => {
      const hist = panel.querySelector("#loads-hist");
      hist.hidden = !hist.hidden;
      more.setAttribute("aria-expanded", String(!hist.hidden));
      more.textContent = hist.hidden ? "Show the load history" : "Hide the load history";
    };
  }
}

function note(panel, text, bad = false) {
  const n = el("div", `loads-msg${bad ? " bad" : ""}`, text);
  n.setAttribute("role", "status");
  panel.querySelector(".loads-h").after(n);
}

function when(ts) {
  const d = new Date(String(ts).replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return String(ts);
  return `${d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })} ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
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
