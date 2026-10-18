import { renderBlock } from "./charts.js";

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
  return wrap;
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
