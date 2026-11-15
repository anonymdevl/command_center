/**
 * The analyst's live steps, grouped.
 *
 * A big question can run the same kind of lookup six times in a row -- six ERPNext
 * reports, five breakdowns -- and six near-identical lines push the rest of the working
 * off the screen. So a run of steps of one kind is one line with a count ("Running an
 * ERPNext report ×6"), and "Show all" lists each step's own line under it.
 *
 * A step from the server is {text, kind, group} (api/ask.py _record); an older one, or a
 * message from the model client ("Gemini is slow, trying another"), is a plain string
 * with no kind and is never grouped. Built with textContent only: nothing here is HTML.
 *
 * groupSteps is pure, so scripts/test_steps.mjs can check it without a browser.
 */

export function stepOf(s) {
  if (s && typeof s === "object") {
    return { text: String(s.text ?? ""), kind: s.kind || null, group: s.group || null };
  }
  return { text: String(s ?? ""), kind: null, group: null };
}

/** Consecutive steps of one kind become one row: {label, count, details, kind}. */
export function groupSteps(steps) {
  const rows = [];
  for (const raw of steps || []) {
    const s = stepOf(raw);
    if (!s.text) continue;
    const last = rows[rows.length - 1];
    if (last && s.kind && last.kind === s.kind) {
      last.count += 1;
      last.details.push(s.text);
    } else {
      rows.push({ kind: s.kind, group: s.group, count: 1, details: [s.text] });
    }
  }
  return rows.map((r) => ({
    ...r,
    label: r.count > 1 ? (r.group || r.details[0]) : r.details[0],
  }));
}

/** Whether "Show all" would show anything the grouped rows do not. */
export function hasHidden(rows) {
  return rows.some((r) => r.count > 1);
}

/**
 * The steps as a list, with a "Show all" toggle when some are grouped. `host` keeps
 * the toggle's state across redraws (the list is redrawn on every poll).
 */
export function renderSteps(steps, host) {
  const rows = groupSteps(steps);
  const all = host?.dataset?.stepsAll === "1";
  const wrap = document.createElement("div");
  wrap.className = "ap-stepwrap";
  const ol = document.createElement("ol");
  ol.className = "ap-steps";
  rows.forEach((r, i) => {
    const li = document.createElement("li");
    li.className = i === rows.length - 1 ? "now" : "done";
    li.append(document.createTextNode(r.label));
    if (r.count > 1) {
      const n = document.createElement("span");
      n.className = "ap-stepn";
      n.textContent = `×${r.count}`;
      li.append(n);
      if (all) {
        const ul = document.createElement("ul");
        ul.className = "ap-stepd";
        r.details.forEach((d) => {
          const x = document.createElement("li");
          x.textContent = d;
          ul.append(x);
        });
        li.append(ul);
      }
    }
    ol.append(li);
  });
  wrap.append(ol);
  if (hasHidden(rows) && host) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ap-stepall";
    b.textContent = all ? "Show less" : "Show all";
    b.onclick = () => {
      host.dataset.stepsAll = all ? "" : "1";
      wrap.replaceWith(renderSteps(steps, host));
    };
    wrap.append(b);
  }
  return wrap;
}
