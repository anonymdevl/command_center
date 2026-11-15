/**
 * Running a management report from the designed Reports screen.
 *
 * The screen's Run buttons call runReport(code). The report is written on the server
 * by the analyst as a background job (api/reports.py), so this starts it, polls until
 * it is done, and renders it under the table -- built from DOM nodes, never HTML. The
 * row's "Last run" says what actually happened: writing, the time it was written, or
 * that it failed.
 */
import { api } from "../api/client.js";
import { renderMarkdown } from "./markdown.js";
import { tablesFrom } from "../exportTables.js";
import { boot, brand, clientBrand } from "../api/boot.js";
import { shortDate } from "../format.js";

const POLL_MS = 2500;
const GIVE_UP_MS = 22 * 60 * 1000;

export async function runReport(code, scope) {
  const out = document.getElementById("rpout");
  const btn = document.querySelector(`button[data-report="${code}"]`);
  const last = document.querySelector(`[data-last="${code}"]`);
  if (!out) return;
  if (btn) btn.disabled = true;
  setLast(last, "t-wt", "Writing…");

  const box = el("div", "panel rp");
  const head = el("div", "rp-head");
  const t = el("b", "", "Starting the report…");
  const sub = el("span", "rp-sub", "");
  head.append(t, sub);
  box.append(head);
  out.prepend(box);
  box.scrollIntoView({ behavior: "smooth", block: "start" });

  const started = Date.now();
  const tick = setInterval(() => {
    sub.textContent = `The analyst is gathering figures across every area · ${Math.floor(
      (Date.now() - started) / 1000)}s — reports take one to three minutes`;
  }, 1000);

  try {
    const { job_id, title } = await api.reportGenerate({ code, business_code: scope });
    t.textContent = `Writing the ${title}`;
    let state;
    do {
      await new Promise((r) => setTimeout(r, POLL_MS));
      state = await api.reportStatus(job_id);
      if (Date.now() - started > GIVE_UP_MS) throw new Error("It is taking too long; try again.");
    } while (state?.state === "running");
    if (state?.state !== "done") throw new Error(state?.error || "The report could not be written.");
    clearInterval(tick);
    render(box, state.report, scope);
    const when = new Date(state.report.generated || Date.now());
    setLast(last, "t-ok", `Written ${when.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`);
  } catch (e) {
    clearInterval(tick);
    box.textContent = "";
    const w = el("div", "warn");
    w.append(el("b", "", "The report could not be written. "), document.createTextNode(e?.message || ""));
    box.append(w);
    setLast(last, "t-od", "Failed");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function render(box, r, scope) {
  box.textContent = "";
  const head = el("div", "rp-head");
  // The same title block as the PDF: kind, title, who it is for, as at when.
  const biz = (boot.scopes || []).find((x) => x.code === scope)?.label || "All businesses";
  const forName = clientBrand(scope)?.display_name || biz;
  const title = el("div", "rp-title");
  title.append(
    el("span", "rp-kick", "Management Report"),
    el("b", "", r.title),
    el("span", "rp-for", `Prepared for ${forName} · figures as at ${shortDate(boot.as_of?.date) || "—"}`),
    el("span", "rp-sub", `Written ${new Date(r.generated || Date.now()).toLocaleString("en-GB", {
      day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · ${r.model || "the analyst"} · reads only`),
  );
  head.append(title);
  const acts = el("div", "rp-acts");
  const body = el("div", "rp-body");
  const md = renderMarkdown(r.answer);
  markRecommendations(md);
  body.append(md);
  acts.append(
    button("PDF", () => api.answerPdf({ question: r.title, answer: r.answer, checked: r.checked,
      business_code: scope, model: r.model, kind: "report" })),
    button("Excel", () => {
      const tables = tablesFrom(body);
      if (!tables.length) return Promise.reject(new Error("This report has no tables."));
      return api.tablesXlsx({ title: r.title, tables, business_code: scope });
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

function setLast(node, cls, text) {
  if (!node) return;
  node.className = `tag ${cls}`;
  node.textContent = text;
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text) n.textContent = text;
  return n;
}
