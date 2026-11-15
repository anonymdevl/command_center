import { renderBlock, chartModel } from "./charts.js";

/**
 * The analyst's answer, as formatted text -- built from DOM nodes, never from HTML.
 *
 * The answer comes from a model, so it is treated as untrusted text: nothing is ever
 * parsed as HTML, and a link is kept only if it points back into this site (the
 * ERPNext forms the tools link to). A link anywhere else is shown as plain text, so an
 * answer cannot send a director to a page nobody checked.
 *
 * Deliberately small: headings, paragraphs, bullet and numbered lists, tables, bold,
 * italics, inline code and links. That is everything the system prompt asks for.
 */

export function renderMarkdown(src, { onFollowup } = {}) {
  const root = document.createElement("div");
  root.className = "md";
  const lines = String(src || "").replace(/\r\n?/g, "\n").split("\n");
  let lead = true; // the first paragraph is the answer itself, set as the headline

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i++;
      continue;
    }

    // Fenced blocks: ```figures and ```chart are drawn (charts.js); anything else is
    // shown as code. Never parsed as HTML.
    const fence = /^\s*```\s*([\w-]*)\s*$/.exec(line);
    if (fence) {
      const lang = fence[1].toLowerCase();
      const body = [];
      i++;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) body.push(lines[i++]);
      i++; // the closing fence
      if (lang === "followups") {
        // The analyst's suggested next questions: chips that ask them. Shown only where
        // there is somewhere to ask (the bar, the Ask AI screen) -- never in a report.
        const chips = onFollowup ? followups(body.join("\n"), onFollowup) : null;
        if (chips) root.append(chips);
      } else if (lang === "figures" || lang === "chart") {
        const drawn = renderBlock(lang, body.join("\n"));
        if (drawn) root.append(drawn);
      } else {
        const pre = document.createElement("pre");
        const code = document.createElement("code");
        code.textContent = body.join("\n");
        pre.append(code);
        root.append(pre);
      }
      continue;
    }

    // Table: a header row, a |---| separator, then rows.
    if (isRow(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const head = cells(line);
      const align = cells(lines[i + 1]).map((c) =>
        /^:-+:$/.test(c) ? "c" : /-+:$/.test(c) ? "r" : "");
      i += 2;
      const rows = [];
      while (i < lines.length && isRow(lines[i])) rows.push(cells(lines[i++]));
      root.append(table(head, rows, align));
      continue;
    }

    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      lead = false;
      const el = document.createElement(h[1].length <= 2 ? "h4" : "h5");
      inline(el, h[2]);
      root.append(el);
      i++;
      continue;
    }

    if (/^\s*([-*•]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]/.test(line);
      const list = document.createElement(ordered ? "ol" : "ul");
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) {
        const li = document.createElement("li");
        const body = lines[i].replace(/^\s*([-*•]|\d+[.)])\s+/, "");
        inline(li, body);
        mark(li, body);
        list.append(li);
        i++;
      }
      root.append(list);
      continue;
    }

    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      i++;
      continue;
    }

    // A paragraph runs until a blank line or the start of another block.
    const para = [];
    while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) para.push(lines[i++]);
    const p = document.createElement("p");
    inline(p, para.join(" "));
    mark(p, para.join(" "));
    if (lead && !p.classList.length) p.classList.add("md-lead");
    lead = false;
    root.append(p);
  }
  return root;
}

function followups(source, onAsk) {
  let list;
  try {
    list = JSON.parse(source);
  } catch {
    return null;
  }
  if (!Array.isArray(list)) return null;
  const qs = list.map((q) => String(q || "").trim()).filter((q) => q && q.length < 200).slice(0, 3);
  if (!qs.length) return null;
  const box = document.createElement("div");
  box.className = "md-follow";
  const t = document.createElement("span");
  t.className = "md-follow-t";
  t.textContent = "Ask next";
  box.append(t);
  qs.forEach((q) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "md-follow-q";
    b.textContent = q;
    b.onclick = () => onAsk(q);
    box.append(b);
  });
  return box;
}

/** Recommendations and projections are labelled in the text; give them a look too. */
function mark(el, raw) {
  const t = raw.replace(/^[*_\s]+/, "").toLowerCase();
  if (t.startsWith("recommendation")) el.classList.add("md-rec");
  else if (t.startsWith("projection")) el.classList.add("md-proj");
}

function startsBlock(lines, i) {
  const l = lines[i];
  return /^\s*```/.test(l) || /^#{1,4}\s/.test(l) || /^\s*([-*•]|\d+[.)])\s+/.test(l) ||
    (isRow(l) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1]));
}

function isRow(l) {
  return /^\s*\|.*\|\s*$/.test(l);
}

function cells(l) {
  return l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

function table(head, rows, align) {
  const wrap = document.createElement("div");
  wrap.className = "md-table";
  const t = document.createElement("table");
  t.className = "dt";
  const thead = document.createElement("thead");
  const tr = document.createElement("tr");
  head.forEach((c, j) => {
    const th = document.createElement("th");
    if (align[j] === "r" || (j > 0 && looksNumeric(rows, j))) th.className = "r";
    inline(th, c);
    tr.append(th);
  });
  thead.append(tr);
  t.append(thead);
  const tbody = document.createElement("tbody");
  rows.forEach((r) => {
    const row = document.createElement("tr");
    head.forEach((_, j) => {
      const td = document.createElement("td");
      if (align[j] === "r" || (j > 0 && looksNumeric(rows, j))) td.className = "r";
      inline(td, r[j] ?? "");
      row.append(td);
    });
    tbody.append(row);
  });
  t.append(tbody);
  wrap.append(t);
  const pager = enhanceTable(t);
  if (pager) wrap.append(pager);
  return wrap;
}

/* ------------------------------------------------------- sorting and pages */
export const PAGE_ROWS = 10;

/**
 * Makes a rendered table sortable by its headings and, past ten rows, shown a page at
 * a time. Returns the pager to put under the table, or null when it fits on one page.
 *
 * Rows on other pages are hidden, never removed: the Excel export (exportTables.js)
 * reads every row of the table, in the order it is sorted, so the sheet always has all
 * of them -- not just the page that happened to be showing.
 */
export function enhanceTable(table, pageRows = PAGE_ROWS) {
  const tbody = table.tBodies[0];
  const headRow = table.tHead && table.tHead.rows[0];
  if (!tbody || !headRow) return null;
  const original = Array.from(tbody.rows);
  if (original.length < 2) return null;
  let order = original.slice();
  let page = 0;
  let all = false;
  let pager = null;
  let info = null;
  let prev = null;
  let next = null;
  let toggle = null;

  const ths = Array.from(headRow.cells);
  ths.forEach((th, j) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "md-sort";
    b.title = "Sort by this column";
    while (th.firstChild) b.append(th.firstChild);
    th.append(b);
    th.setAttribute("aria-sort", "none");
    b.onclick = () => {
      const was = th.getAttribute("aria-sort");
      const kind = columnKind(original, j);
      // Figures and dates open largest / latest first, words A to Z.
      const first = kind === "text" ? "ascending" : "descending";
      const dir = was === "none" ? first : was === "ascending" ? "descending" : "ascending";
      ths.forEach((h) => h.setAttribute("aria-sort", "none"));
      th.setAttribute("aria-sort", dir);
      order = sortRows(original, j, kind, dir);
      page = 0;
      paint();
    };
  });

  if (original.length > pageRows) {
    pager = document.createElement("div");
    pager.className = "md-pager";
    info = document.createElement("span");
    info.className = "md-pager-i";
    prev = pagerButton("Previous", () => { page -= 1; paint(); });
    next = pagerButton("Next", () => { page += 1; paint(); });
    toggle = pagerButton("Show all", () => { all = !all; page = 0; paint(); });
    pager.append(info, prev, next, toggle);
  }

  function paint() {
    const pages = Math.ceil(order.length / pageRows);
    page = Math.max(0, Math.min(page, pages - 1));
    order.forEach((tr, i) => {
      tr.hidden = !!pager && !all && (i < page * pageRows || i >= (page + 1) * pageRows);
      tbody.append(tr);
    });
    if (!pager) return;
    const from = page * pageRows + 1;
    const to = Math.min(order.length, (page + 1) * pageRows);
    info.textContent = all ? `All ${order.length} rows` : `${from}–${to} of ${order.length}`;
    prev.hidden = all;
    next.hidden = all;
    prev.disabled = page === 0;
    next.disabled = page >= pages - 1;
    toggle.textContent = all ? `Show ${pageRows} at a time` : "Show all";
  }
  paint();
  return pager;
}

function pagerButton(label, run) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "md-dl";
  b.textContent = label;
  b.onclick = run;
  return b;
}

function sortRows(rows, j, kind, dir) {
  const keyed = rows.map((tr, i) => ({ tr, i, k: sortKey(cellText(tr, j), kind) }));
  const sign = dir === "ascending" ? 1 : -1;
  keyed.sort((a, b) => {
    // Blanks ("—") go last whichever way the column is sorted.
    if (a.k === null || b.k === null) return a.k === null && b.k === null ? a.i - b.i : a.k === null ? 1 : -1;
    const c = kind === "text"
      ? a.k.localeCompare(b.k, "en-GB", { numeric: true, sensitivity: "base" })
      : a.k - b.k;
    return c ? c * sign : a.i - b.i;
  });
  return keyed.map((x) => x.tr);
}

function cellText(tr, j) {
  return (tr.cells[j]?.textContent || "").replace(/\s+/g, " ").replace(/\s*↗$/, "").trim();
}

/** "number" if every filled cell reads as a figure, "date" if as a date, else "text". */
export function columnKind(rows, j) {
  const vals = rows.map((tr) => cellText(tr, j)).filter((v) => !isBlank(v));
  if (!vals.length) return "text";
  if (vals.every((v) => Number.isFinite(sortNumber(v)))) return "number";
  if (vals.every((v) => Number.isFinite(sortDate(v)))) return "date";
  return "text";
}

function sortKey(text, kind) {
  if (isBlank(text)) return null;
  if (kind === "number") return sortNumber(text);
  if (kind === "date") return sortDate(text);
  return text;
}

function isBlank(v) {
  return !v || /^[—–-]+$/.test(v.trim());
}

/**
 * A cell as a number for sorting: "GHS 1,234.50" -> 1234.5, "12%" -> 12,
 * "(5,000)" -> -5000, "1.2M" -> 1200000, "118 days" -> 118. NaN if it is not a figure.
 */
export function sortNumber(text) {
  let t = String(text).replace(/\s+/g, " ").trim();
  if (isBlank(t)) return NaN;
  let sign = 1;
  if (/^\(.+\)$/.test(t)) {
    sign = -1;
    t = t.slice(1, -1).trim();
  }
  t = t.replace(/[−–]/g, "-").replace(/\b[A-Z]{3}\b/g, "").replace(/[$€£₵¢]/g, "").trim();
  const m = /^([-+])?\s*(\d{1,3}(?:,\d{3})+|\d+)?(\.\d+)?([kKmMbB]n?)?(?![a-zA-Z])\s*(%|[a-zA-Z][a-zA-Z .]*)?$/.exec(t);
  if (!m || (!m[2] && !m[3])) return NaN;
  const base = parseFloat(`${(m[2] || "0").replace(/,/g, "")}${m[3] || ""}`);
  const mult = { k: 1e3, m: 1e6, b: 1e9 }[(m[4] || "").charAt(0).toLowerCase()] || 1;
  return sign * (m[1] === "-" ? -1 : 1) * base * mult;
}

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

/** "2026-10-18", "18 Oct 2026", "Oct 2026" or "18 Oct" as a time for sorting; else NaN. */
export function sortDate(text) {
  const t = String(text).trim();
  let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t);
  if (m) return Date.UTC(+m[1], +m[2] - 1, +m[3]);
  m = /^(?:(\d{1,2})\s+)?([A-Za-z]{3})[a-z]*\.?,?\s*(\d{4})?$/.exec(t);
  if (m && (m[1] || m[3])) {
    const mon = MONTHS.indexOf(m[2].toLowerCase());
    if (mon >= 0) return Date.UTC(m[3] ? +m[3] : 2000, mon, m[1] ? +m[1] : 1);
  }
  return NaN;
}

/* ----------------------------------------------------------- copying an answer */
/**
 * The answer as text to paste into an email or a document: the markdown as written,
 * with the figure cards and charts said in words (their JSON would mean nothing to the
 * reader) and the suggested next questions left out.
 */
export function answerAsText(src) {
  const lines = String(src || "").replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const fence = /^\s*```\s*([\w-]*)\s*$/.exec(lines[i]);
    if (!fence) {
      out.push(lines[i]);
      continue;
    }
    const lang = fence[1].toLowerCase();
    const body = [];
    i++;
    while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) body.push(lines[i++]);
    if (lang === "followups") continue;
    if (lang === "figures" || lang === "chart") {
      const said = lang === "figures" ? figuresText(body.join("\n")) : chartText(body.join("\n"));
      if (said) out.push(said);
      continue;
    }
    out.push("```" + lang, ...body, "```");
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function figuresText(source) {
  let list;
  try {
    list = JSON.parse(source);
  } catch {
    return "";
  }
  if (!Array.isArray(list)) return "";
  return list.slice(0, 4).filter((f) => f && typeof f === "object" && f.value !== undefined)
    .map((f) => `- ${f.label ? `${f.label}: ` : ""}${f.value}${f.note ? ` (${f.note})` : ""}`).join("\n");
}

function chartText(source) {
  let spec;
  try {
    spec = JSON.parse(source);
  } catch {
    return "";
  }
  const m = chartModel(spec);
  if (!m) return "";
  const n = (v, unit) => {
    const s = Number(v).toLocaleString("en-GB", { maximumFractionDigits: 2 });
    return unit === "%" ? `${s}%` : unit ? `${unit} ${s}` : s;
  };
  if (m.type === "gauge") {
    const g = m.gauge;
    return [m.title ? `${m.title}:` : "",
      `- ${g.label || "Value"}: ${n(g.value, m.unit)}${g.target !== null ? ` (target ${n(g.target, m.unit)})` : ""}`]
      .filter(Boolean).join("\n");
  }
  if (m.type === "treemap") {
    const rows = m.tree.flatMap((t) => [`- ${t.name}: ${n(t.value, m.unit)}`,
      ...(t.children || []).map((c) => `  - ${c.name}: ${n(c.value, m.unit)}`)]);
    return [m.title ? `${m.title}:` : "", ...rows].filter(Boolean).join("\n");
  }
  const unitOf = (si) => (si === 1 && ["combo", "scatter", "bubble"].includes(m.type) ? m.unit2 || m.unit
    : si === 2 && m.type === "bubble" ? m.unit3 : m.unit);
  const series = ["bar", "donut", "hbar", "pie", "rose", "funnel", "waterfall"].includes(m.type)
    ? m.series.slice(0, 1) : m.series;
  const rows = m.labels.map((l, i) => {
    const vals = series.filter((s) => i < s.values.length);
    if (vals.length === 1) return `- ${l}: ${n(vals[0].values[i], unitOf(0))}`;
    return `- ${l}: ${vals.map((s) => `${s.name} ${n(s.values[i], unitOf(series.indexOf(s)))}`).join(", ")}`;
  });
  return [m.title ? `${m.title}:` : "", ...rows].filter(Boolean).join("\n");
}

function looksNumeric(rows, j) {
  const vals = rows.map((r) => (r[j] || "").replace(/[\s,GHS%()+−-]/g, "")).filter(Boolean);
  return vals.length > 0 && vals.every((v) => /^\d+(\.\d+)?[kKmMbB]?$/.test(v));
}

/** Bold, italics, code and links, as nodes. Everything else is text. */
function inline(el, s) {
  const re = /(\*\*([^*]+)\*\*|__([^_]+)__|\*([^*\s][^*]*)\*|_([^_\s][^_]*)_|`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\))/g;
  let last = 0;
  let m;
  while ((m = re.exec(s))) {
    if (m.index > last) el.append(document.createTextNode(s.slice(last, m.index)));
    if (m[2] || m[3]) el.append(node("b", m[2] || m[3]));
    else if (m[4] || m[5]) el.append(node("i", m[4] || m[5]));
    else if (m[6]) el.append(node("code", m[6]));
    else if (m[7]) el.append(link(m[7], m[8]));
    last = re.lastIndex;
  }
  if (last < s.length) el.append(document.createTextNode(s.slice(last)));
}

function node(tag, t) {
  const n = document.createElement(tag);
  n.textContent = t;
  return n;
}

/** A link survives only if it stays on this site. */
function link(label, href) {
  let url = null;
  try {
    url = new URL(href, window.location.origin);
  } catch {
    url = null;
  }
  if (!url || url.origin !== window.location.origin || !/^https?:$/.test(url.protocol)) {
    return document.createTextNode(label);
  }
  const a = document.createElement("a");
  a.className = "dlink";
  a.href = url.href;
  a.target = "_blank";
  a.rel = "noreferrer";
  a.textContent = `${label} ↗`;
  return a;
}
