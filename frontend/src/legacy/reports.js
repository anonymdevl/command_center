/**
 * The management reports on the designed Reports screen.
 *
 * A report is written on the server by the analyst as a background job, and every run
 * is kept there (api/reports.py, Command Center Report Run). So nothing here holds the
 * only copy of anything: leaving the screen loses nothing. On load the screen asks for
 * each report's latest run and fills its "Last run" cell ("Written 14:32 today by
 * Samuel", "Writing… (started 14:30)", "Failed 14:31"), offers View Last Report where one
 * has been written, and follows any run still being written. Following is not tied to
 * the screen: `follow()` keeps polling from any page and announces the finish with a
 * "cc-report-finished" event, which the bell (Bell.jsx) turns into its notice and a toast.
 *
 * Built from DOM nodes, never HTML.
 */
import { api } from "../api/client.js";
import { renderMarkdown } from "./markdown.js";
import { tablesFrom } from "../exportTables.js";
import { asOfFor, boot, brand, clientBrand } from "../api/boot.js";
import { shortDate } from "../format.js";

const POLL_MS = 3000;
const RETRY_MS = 15000;
// Where the bell's "Your report is ready" asks the Reports screen to open one.
export const OPEN_KEY = "cc-report-open";

/* ---------------------------------------------------------------- following a run */
const following = new Set();

/**
 * Poll a run until it is written or has failed, from whichever page is open; once per
 * run. Announces "cc-report-progress" while it is written and "cc-report-finished" at
 * the end, each with { id, state, run (the row), report?, error? }.
 */
export function follow(id) {
  if (!id || following.has(id)) return;
  following.add(id);
  (async () => {
    let state = null;
    for (;;) {
      await sleep(POLL_MS);
      try {
        state = await api.reportStatus(id);
      } catch (e) {
        // Signed out or refused: stop. A network blip: try again shortly.
        if (e?.status === 401 || e?.status === 403) break;
        await sleep(RETRY_MS);
        continue;
      }
      if (state?.state !== "running") break;
      window.dispatchEvent(new CustomEvent("cc-report-progress", { detail: { id, ...state } }));
    }
    following.delete(id);
    window.dispatchEvent(new CustomEvent("cc-report-finished", { detail: { id, ...(state || {}) } }));
  })();
}

/* ---------------------------------------------------------------- the Run button */
export async function runReport(code, scope) {
  const out = document.getElementById("rpout");
  const btn = document.querySelector(`button[data-report="${code}"]`);
  if (!out) return;
  if (btn) btn.disabled = true;
  const box = boxFor(out, code);
  box.textContent = "";
  delete box.dataset.run;
  box.append(el("div", "rp-head", "", [el("b", "", "Starting the report…")]));
  box.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const started = await api.reportGenerate({ code, business_code: scope });
    const run = started.run || { name: started.job_id, code, title: started.title, state: "running" };
    writing(box, run, started.already);
    setLast(document.querySelector(`[data-last="${code}"]`), run);
    follow(run.name);
    window.dispatchEvent(new CustomEvent("cc-reports-changed"));
  } catch (e) {
    failed(box, e?.message);
    if (btn) btn.disabled = false;
  }
}

/* ---------------------------------------------------------------- the screen */
/**
 * Fill the Reports screen from the server, follow what is being written, and show what
 * finishes while it is open. Returns the cleanup for when the screen closes.
 */
export function mountReports(root, scope) {
  if (!root) return () => {};
  let alive = true;
  const here = scope || "__all__";
  const out = root.querySelector("#rpout");
  const lastCell = (code) => root.querySelector(`[data-last="${code}"]`);

  const load = () =>
    api.reportLatest(scope).then((d) => {
      if (!alive) return;
      for (const [code, slot] of Object.entries(d?.runs || {})) fillRow(root, code, slot);
      // Anything still being written is shown being written, and followed.
      for (const slot of Object.values(d?.runs || {})) {
        const run = slot.latest;
        if (run && (run.state === "running" || run.state === "queued")) {
          if (out) writing(boxFor(out, run.code), run, false);
          follow(run.name);
        }
      }
    }).catch(() => {});

  const finished = (e) => {
    const d = e.detail || {};
    const row = d.run && typeof d.run === "object" ? d.run : null;
    if (!alive) return;
    if (row && (row.business_code || "__all__") === here) {
      const box = out?.querySelector(`.rp[data-code="${row.code}"]`);
      if (box && box.dataset.run === row.name) {
        if (d.state === "done" && d.report) {
          render(box, d.report, row);
          // Seen here, so the bell does not announce what is already on the screen.
          if (row.mine) {
            api.reportSeen(row.name)
              .then(() => window.dispatchEvent(new CustomEvent("cc-reports-changed")))
              .catch(() => {});
          }
        } else if (d.state === "failed") {
          failed(box, d.error);
        }
      }
    }
    load();
  };
  const progress = (e) => {
    const row = e.detail?.run;
    if (alive && row && typeof row === "object" && (row.business_code || "__all__") === here) {
      setLast(lastCell(row.code), row);
    }
  };
  const open = (e) => openRun(e.detail?.run, out);

  window.addEventListener("cc-report-finished", finished);
  window.addEventListener("cc-report-progress", progress);
  window.addEventListener("cc-report-open", open);
  load();
  // The bell's "Your … is ready" opens the Reports screen with that report shown.
  let asked = null;
  try {
    asked = sessionStorage.getItem(OPEN_KEY);
    sessionStorage.removeItem(OPEN_KEY);
  } catch { /* private mode */ }
  if (asked) openRun(asked, out);
  return () => {
    alive = false;
    window.removeEventListener("cc-report-finished", finished);
    window.removeEventListener("cc-report-progress", progress);
    window.removeEventListener("cc-report-open", open);
  };
}

/** A written report, opened again from the server -- nothing rewritten, nothing counted. */
export async function openRun(id, out = document.getElementById("rpout")) {
  if (!id || !out) return;
  try {
    const d = await api.reportOpen(id);
    const box = boxFor(out, d.run.code);
    render(box, d.report, d.run);
    box.scrollIntoView({ behavior: "smooth", block: "start" });
    window.dispatchEvent(new CustomEvent("cc-reports-changed"));
  } catch (e) {
    failed(boxFor(out, "open"), e?.message, "The report could not be opened. ");
  }
}

function fillRow(root, code, slot) {
  const last = root.querySelector(`[data-last="${code}"]`);
  if (!last || !slot?.latest) return;
  setLast(last, slot.latest);
  const btn = root.querySelector(`button[data-report="${code}"]`);
  const live = slot.latest.state === "running" || slot.latest.state === "queued";
  if (btn) {
    btn.disabled = live;
    btn.title = live ? "Being written; it is shown below when it is ready" : "";
  }
  const cell = last.parentElement;
  cell.querySelector(".rp-view")?.remove();
  if (slot.last_done) {
    const v = el("button", "lnk rp-view", "View Last Report");
    v.type = "button";
    v.dataset.ccWired = "1";
    v.title = `${slot.last_done.title}, written ${slot.last_done.finished_label || ""}`;
    v.onclick = (e) => {
      e.stopPropagation();
      openRun(slot.last_done.name, root.querySelector("#rpout"));
    };
    cell.append(v);
  }
}

/** The row's "Last run" tag, from a run. "Not run yet" stays until there is one. */
function setLast(node, run) {
  if (!node || !run) return;
  node.dataset.ran = "1";
  const by = run.run_by_name ? ` by ${run.mine ? "you" : run.run_by_name}` : "";
  const sched = run.kind === "scheduled";
  let cls;
  let text;
  if (run.state === "running" || run.state === "queued") {
    cls = "t-wt";
    text = `Writing… (started ${hm(run.started_label) || "just now"})`;
  } else if (run.state === "done") {
    cls = run.error ? "t-od" : "t-ok";
    text = sched
      ? (run.error ? `Written ${run.finished_label}, not sent` : `Sent ${run.finished_label}`)
      : `Written ${run.finished_label}${by}`;
  } else {
    cls = "t-od";
    text = `Failed ${hm(run.finished_label)}`;
  }
  node.className = `tag ${cls}`;
  node.textContent = text;
  node.title = run.error || (sched ? "Written on its schedule and emailed" : "");
}

/** "14:30 today" -> "14:30" where the cell is about now; other days keep their date. */
function hm(label) {
  return String(label || "").replace(/ today$/, "");
}

/* ---------------------------------------------------------------- the boxes */
function boxFor(out, code) {
  let box = out.querySelector(`.rp[data-code="${code}"]`);
  if (!box) {
    box = el("div", "panel rp");
    box.dataset.code = code;
    out.prepend(box);
  }
  return box;
}

function writing(box, run, already) {
  if (box.dataset.run === run.name && box.querySelector(".rp-wait")) return;
  box.textContent = "";
  box.dataset.run = run.name;
  const head = el("div", "rp-head rp-wait");
  const sub = el("span", "rp-sub", "");
  head.append(el("b", "", `Writing the ${run.title}`), sub);
  const lead = already
    ? `This report was already being written${run.mine ? "" : ` for ${run.run_by_name}`}, so it was not started twice. `
    : "";
  box.append(head, el("p", "rp-sub", `${lead}You can leave this screen: it carries on, and the bell will tell you when it is ready.`));
  const base = Date.now() - (run.elapsed || 0) * 1000;
  const t = setInterval(() => tick(), 1000);
  function tick() {
    if (!document.body.contains(sub)) {
      clearInterval(t);
      return;
    }
    sub.textContent = `Started ${run.started_label || "just now"}${run.mine === false ? ` by ${run.run_by_name}` : ""}`
      + ` · the analyst is gathering figures across every area · ${Math.floor((Date.now() - base) / 1000)}s`
      + " — reports take one to three minutes";
  }
  tick();
}

function failed(box, message, lead = "The report could not be written. ") {
  box.textContent = "";
  delete box.dataset.run;
  const w = el("div", "warn");
  w.append(el("b", "", lead), document.createTextNode(message || ""));
  box.append(w);
}

function render(box, r, run) {
  box.textContent = "";
  box.dataset.run = run?.name || r.run || "";
  const scope = r.business_code || run?.business_code || "__all__";
  const head = el("div", "rp-head");
  // The same title block as the PDF: kind, title, who it is for, as at when.
  const biz = (boot.scopes || []).find((x) => x.code === scope)?.label || "All businesses";
  const forName = clientBrand(scope)?.display_name || biz;
  const title = el("div", "rp-title");
  const who = run?.run_by_name ? ` by ${run.mine ? "you" : run.run_by_name}` : "";
  const written = run?.finished_label
    ? `Written ${run.finished_label}${run.kind === "scheduled" ? " on its schedule" : who}`
    : `Written ${new Date(r.generated || Date.now()).toLocaleString("en-GB", {
      day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`;
  title.append(
    el("span", "rp-kick", "Management Report"),
    el("b", "", r.title),
    el("span", "rp-for", `Prepared for ${forName} · figures as at ${shortDate(asOfFor(scope)?.date) || "—"}`),
    el("span", "rp-sub", `${written} · ${r.model || "the analyst"} · reads only`),
  );
  head.append(title);
  const acts = el("div", "rp-acts");
  const body = el("div", "rp-body");
  const md = renderMarkdown(r.answer);
  markRecommendations(md);
  body.append(md);
  // The same branded exports as when it was first written (api/export.py).
  const bizCode = scope;
  acts.append(
    button("PDF", () => api.answerPdf({ question: r.title, answer: r.answer, checked: r.checked,
      business_code: bizCode, model: r.model, kind: "report" })),
    button("Excel", () => {
      const tables = tablesFrom(body);
      if (!tables.length) return Promise.reject(new Error("This report has no tables."));
      return api.tablesXlsx({ title: r.title, tables, business_code: bizCode });
    }),
    button("Copy", () => navigator.clipboard.writeText(`${r.title}\n\n${r.answer}`)),
  );
  head.append(acts);
  box.append(head, body, el("div", "rp-foot", brand.footer || brand.product));
  if (r.checked?.length) {
    const d = el("details", "ap-checked");
    d.append(el("summary", "", `What it checked (${r.checked.length})`));
    const ul = el("ul");
    r.checked.forEach((c) => ul.append(el("li", "", c)));
    d.append(ul);
    box.append(d);
  }
}

/** The list under the Recommendations heading, numbered and set off as in the PDF. */
export function markRecommendations(root) {
  for (const h of root.querySelectorAll("h4, h5")) {
    if (!/^(recommendations?|recommended actions?|next steps|actions)\b/i.test((h.textContent || "").trim())) continue;
    const list = h.nextElementSibling;
    if (list && (list.tagName === "OL" || list.tagName === "UL")) list.classList.add("md-recs");
  }
}

function button(label, run) {
  const b = el("button", "btn", label);
  b.onclick = async () => {
    b.disabled = true;
    b.textContent = "Preparing…";
    try {
      await run();
      b.textContent = label === "Copy" ? "Copied" : "Downloaded";
    } catch (e) {
      b.textContent = "Failed";
      b.title = e?.message || "";
    }
    setTimeout(() => { b.disabled = false; b.textContent = label; }, 2200);
  };
  return b;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function el(tag, cls, text, kids) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text) n.textContent = text;
  if (kids) n.append(...kids);
  return n;
}
