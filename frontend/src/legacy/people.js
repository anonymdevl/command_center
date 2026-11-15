/**
 * HR & Payroll's People Lookup and Leave, drawn from the business's own ERPNext.
 *
 * api/people.py answers three things: the directory (search, filters, a page at a time),
 * one person's profile (opened in the side drawer), and the leave overview (every
 * active person's balance by leave type, who is away, what is waiting, by department).
 * The designed markup holds only the cards and their headings (.ppanel, interface/
 * views_d.py); everything inside them is built here with DOM calls. Nothing from the
 * API is ever written as HTML. Pay is never read, so none is shown.
 */

import { call } from "../api/client.js";
import { guideBox } from "./guide.js";

export const PEOPLE_VIEWS = new Set(["hr"]);

const M = "command_center.api.people";

/** Draw the People Lookup and Leave cards; returns the cleanup for the effect. */
export function renderPeople(root, { scope, openDrawer } = {}) {
  if (!root) return () => {};
  const state = { alive: true, scope, openDrawer };
  const lookup = root.querySelector('[data-pp="lookup"] .pp-body');
  if (lookup) drawLookup(lookup, state);
  const leave = ["away", "pending", "balances", "bydept"]
    .map((k) => [k, root.querySelector(`[data-pp="${k}"] .pp-body`)])
    .filter(([, n]) => n);
  if (leave.length) drawLeave(Object.fromEntries(leave), state);
  return () => {
    state.alive = false;
  };
}

/* ------------------------------------------------------------------ People Lookup */
function drawLookup(body, state) {
  body.textContent = "";
  const bar = el("div", "filters");
  const q = el("input");
  q.type = "search";
  q.placeholder = "Search by name, ID, job or department";
  q.setAttribute("aria-label", "Search people");
  const dept = select("Department", [["", "All departments"]]);
  const branch = select("Branch", [["", "All branches"]]);
  const status = select("Status", [["Active", "Active"], ["", "Everyone"]]);
  const count = el("span", "tcount");
  bar.append(q, dept, branch, status, count);
  const out = el("div");
  body.append(bar, out);

  let page = 1;
  let seq = 0;
  let filled = false;
  const load = async () => {
    const mine = ++seq;
    if (!out.childNodes.length) out.append(el("div", "pp-empty", "Reading the people on the books…"));
    let res;
    try {
      res = await call(`${M}.directory`, {
        business_code: state.scope, q: q.value, department: dept.value,
        branch: branch.value, status: status.value, page,
      });
    } catch (e) {
      res = { kind: "failed", message: e?.message };
    }
    if (!state.alive || mine !== seq) return;
    out.textContent = "";
    if (res?.kind !== "directory") {
      count.textContent = "";
      out.append(stateNode(res));
      return;
    }
    if (!filled) {
      fill(dept, res.filters?.departments || []);
      fill(branch, res.filters?.branches || []);
      fill(status, (res.filters?.statuses || []).filter((s) => s !== "Active"));
      filled = true;
    }
    page = res.page;
    count.textContent = `${res.total.toLocaleString("en-GB")} of ${res.on_books.toLocaleString("en-GB")} on the books`;
    if (!res.rows.length) {
      out.append(el("div", "pp-empty", "No one matches. Try fewer words or another filter."));
      return;
    }
    out.append(peopleTable(res.rows, (p) => openProfile(p.employee, p.name, state)));
    if (res.pages > 1) {
      const pager = el("div", "pp-pager");
      const prev = button("Previous", () => { page -= 1; load(); });
      const next = button("Next", () => { page += 1; load(); });
      prev.disabled = res.page <= 1;
      next.disabled = res.page >= res.pages;
      pager.append(prev, el("span", "tcount", `Page ${res.page} of ${res.pages}`), next);
      out.append(pager);
    }
  };
  let t = null;
  q.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => { page = 1; load(); }, 250);
  });
  [dept, branch, status].forEach((s) => s.addEventListener("change", () => { page = 1; load(); }));
  load();
}

function peopleTable(rows, onOpen) {
  const wrap = el("div", "pp-scroll");
  const t = table(["Person", "Department", "Status", "Joined", "Reports To", "Login"]);
  const tb = t.querySelector("tbody");
  rows.forEach((p) => {
    const tr = el("tr", "pp-row");
    tr.tabIndex = 0;
    tr.setAttribute("role", "button");
    tr.setAttribute("aria-label", `Open ${p.name}'s profile`);
    tr.append(
      td(who(p)),
      td(two(p.department || "—", p.branch)),
      td(statusTag(p.status)),
      td(two(fmtDate(p.date_of_joining) || "—", p.tenure)),
      td(p.reports_to_name || "—"),
      td(tag(p.has_user ? "Linked" : "None", p.has_user ? "t-ok" : "t-dr")),
    );
    tr.addEventListener("click", () => onOpen(p));
    tr.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onOpen(p);
      }
    });
    tb.append(tr);
  });
  wrap.append(t);
  return wrap;
}

/* ------------------------------------------------------------------ the profile */
async function openProfile(employee, name, state) {
  const { openDrawer } = state;
  if (!openDrawer) return;
  const wait = el("div", "pp-prof");
  wait.append(head({ name: name || employee }, openDrawer),
    el("div", "pp-empty", `Reading ${name || employee}'s record…`));
  openDrawer({ node: wait });
  let res;
  try {
    res = await call(`${M}.profile`, { business_code: state.scope, employee });
  } catch (e) {
    res = { kind: "failed", message: e?.message };
  }
  if (!document.body.contains(wait)) return; // closed, or another profile opened
  openDrawer({ node: profileNode(res, state, name || employee) });
}

function profileNode(res, state, name) {
  const box = el("div", "pp-prof");
  if (res?.kind !== "profile") {
    box.append(head({ name }, state.openDrawer), stateNode(res));
    return box;
  }
  const p = res.person;
  const open = (e) => openProfile(e.employee, e.name, state);
  box.append(head(p, state.openDrawer));

  const kv = el("dl", "kv");
  const row = (k, v) => {
    if (v == null || v === "") return;
    kv.append(el("dt", null, k));
    const dd = el("dd");
    if (v instanceof Node) dd.append(v); else dd.textContent = v;
    kv.append(dd);
  };
  row("Employee ID", p.employee);
  row("Status", statusTag(p.status));
  row("Job", p.designation);
  row("Department", p.department);
  row("Branch", p.branch);
  row("Employment", p.employment_type);
  row("Joined", [fmtDate(p.date_of_joining), p.tenure].filter(Boolean).join(" · "));
  if (p.relieving_date) row("Left", fmtDate(p.relieving_date));
  row("Company email", p.email);
  row("Mobile", p.phone);
  row("ERPNext login", p.has_user ? "Linked" : "None linked");
  box.append(kv);

  // Reporting line
  section(box, "Reporting Line");
  const line = el("ul", "pp-list");
  line.append(li(res.manager ? personLink(res.manager, open) : "No manager recorded",
    res.manager ? "manager" : "Reports To is empty on the employee record"));
  (res.reports || []).forEach((r) => line.append(li(personLink(r, open),
    r.status === "Active" ? (r.designation || "direct report") : r.status)));
  if (!(res.reports || []).length) line.append(li("No direct reports", ""));
  box.append(line);

  // Leave balances
  section(box, "Leave Balances");
  const lv = res.leave || {};
  if (lv.state === "ok") {
    box.append(balanceTable(lv.types));
    const span = lv.types[0] ? `${fmtDate(lv.types[0].from_date)} to ${fmtDate(lv.types[0].to_date)}` : "";
    box.append(el("div", "pp-note", `For the leave period in force today${span ? ` (${span})` : ""}, `
      + "counted as ERPNext counts it: allocated, including any carried forward, less leave "
      + "taken. Pending is leave asked for and not yet approved."));
  } else {
    box.append(partNode(lv, "Leave could not be read."));
  }

  // Recent leave
  section(box, "Recent Leave");
  const apps = res.applications || {};
  if (apps.state === "ok" && apps.items.length) {
    const ul = el("ul", "pp-list");
    apps.items.forEach((a) => ul.append(li(
      link(`${a.leave_type} · ${num(a.days)} day${a.days === 1 ? "" : "s"}`, a.href),
      `${range(a.from_date, a.to_date)} · ${a.status}`)));
    box.append(ul);
  } else {
    box.append(partNode(apps, "No leave applied for."));
  }

  // Attendance this month
  const at = res.attendance || {};
  if (at.state !== "not_installed") {
    section(box, at.month ? `Attendance in ${at.month}` : "Attendance This Month");
    if (at.state === "ok") {
      const chips = el("div", "pp-chips");
      Object.entries(at.counts || {}).forEach(([k, v]) => {
        if (v) chips.append(chip(k, v));
      });
      if (at.late != null) chips.append(chip("Late", at.late));
      if (at.early_exit != null && at.early_exit) chips.append(chip("Left early", at.early_exit));
      box.append(chips, el("div", "pp-note", `${at.marked} day${at.marked === 1 ? "" : "s"} marked `
        + `from ${fmtDate(at.from)} to ${fmtDate(at.to)}.`));
    } else {
      box.append(partNode(at, "No attendance marked this month."));
    }
  }

  // Open To-Dos
  section(box, "Open To-Dos");
  const td_ = res.todos || {};
  if (td_.state === "no_user") {
    box.append(el("div", "pp-empty", "No ERPNext login is linked to this person, so no To-Do can be assigned to them."));
  } else if (td_.state === "ok" && td_.items.length) {
    const ul = el("ul", "pp-list");
    td_.items.forEach((t) => ul.append(li(link(t.text || t.reference || "To-Do", t.href),
      [t.reference, t.due ? `due ${fmtDate(t.due)}` : "", t.priority].filter(Boolean).join(" · "))));
    box.append(ul);
    if (td_.open > td_.items.length) {
      box.append(el("div", "pp-note", `${td_.open.toLocaleString("en-GB")} open in all; the latest ${td_.items.length} are shown.`));
    }
  } else {
    box.append(partNode(td_, "Nothing open."));
  }

  // Appraisals and training
  [["appraisals", "Appraisals", (a) => li(link(`${range(a.from, a.to)}`, a.href),
    [a.status, a.score != null ? `score ${num(a.score)}` : ""].filter(Boolean).join(" · "))],
   ["training", "Training", (a) => li(link(a.event, a.href),
     [fmtDate(a.date), a.status].filter(Boolean).join(" · "))],
   ["assets", "Assets in Their Care", (a) => li(link(a.asset, a.href),
     [a.location, a.status].filter(Boolean).join(" · "))],
  ].forEach(([key, title, draw]) => {
    const part = res[key] || {};
    if (part.state === "not_installed" || part.state === "not_recorded") return;
    section(box, title);
    if (part.state === "ok" && part.items.length) {
      const ul = el("ul", "pp-list");
      part.items.forEach((a) => ul.append(draw(a)));
      box.append(ul);
    } else {
      box.append(partNode(part, "None recorded."));
    }
  });

  // Payroll: whether it is set up, never what anyone is paid
  const pay = res.payroll || {};
  if (pay.state !== "not_installed") {
    section(box, "Payroll");
    if (pay.state === "ok") {
      const ul = el("ul", "pp-list");
      ul.append(li("Salary structure", pay.structure == null ? "not readable"
        : pay.structure ? "assigned" : "none assigned"));
      ul.append(li("Last pay slip", pay.last_slip ? `period ending ${fmtDate(pay.last_slip)}` : "none submitted"));
      box.append(ul, el("div", "pp-note", "Amounts are never read here: what anyone is paid stays in ERPNext."));
    } else {
      box.append(partNode(pay, "Payroll could not be read."));
    }
  }

  const acts = el("div", "acts");
  acts.style.marginTop = "18px";
  if (p.href) {
    const a = el("a", "btn pri", "Open in ERPNext ↗");
    a.href = p.href;
    a.target = "_blank";
    a.rel = "noopener";
    acts.append(a);
  }
  acts.append(button("Ask about their leave", () => {
    state.openDrawer?.(null);
    window.ask2?.(`How much leave does ${p.name} (${p.employee}) have left, and what have they taken this year?`);
  }));
  box.append(acts);
  return box;
}

function head(p, openDrawer) {
  const h = el("div", "dhead");
  const left = el("div", "pp-head");
  left.append(avatar(p, true));
  const txt = el("div");
  txt.append(el("div", "dt", "Employee profile"), el("h4", null, p.name || ""));
  const sub = [p.designation, p.department].filter(Boolean).join(" · ");
  if (sub) txt.append(el("div", "pp-sub", sub));
  left.append(txt);
  h.append(left, button("Close ✕", () => openDrawer?.(null)));
  return h;
}

function balanceTable(types) {
  const wrap = el("div", "pp-scroll narrow");
  const t = table(["Leave Type", ["Allocated", 1], ["Taken", 1], ["Pending", 1], ["Remaining", 1]]);
  const tb = t.querySelector("tbody");
  types.forEach((b) => {
    const tr = el("tr");
    const name = el("div", null, b.leave_type);
    if (b.carried_forward) name.append(el("div", "pp-sub", `${num(b.carried_forward)} carried forward`));
    if (b.expired) name.append(el("div", "pp-sub", `${num(b.expired)} expired`));
    const rem = el("div", null, num(b.remaining));
    const meter = el("div", "pp-meter");
    const fill = el("span");
    fill.style.width = `${b.allocated > 0 ? Math.max(0, Math.min(100, (100 * b.remaining) / b.allocated)) : 0}%`;
    meter.append(fill);
    rem.append(meter);
    tr.append(td(name), td(num(b.allocated), "num"), td(num(b.taken), "num"),
      td(b.pending ? num(b.pending) : "—", "num"), td(rem, "num"));
    tb.append(tr);
  });
  wrap.append(t);
  return wrap;
}

/* ------------------------------------------------------------------ Leave */
async function drawLeave(parts, state) {
  Object.values(parts).forEach((n) => {
    n.textContent = "";
    n.append(el("div", "pp-empty", "Reading leave…"));
  });
  let res;
  try {
    res = await call(`${M}.leave_overview`, { business_code: state.scope });
  } catch (e) {
    res = { kind: "failed", message: e?.message };
  }
  if (!state.alive) return;
  Object.values(parts).forEach((n) => { n.textContent = ""; });
  if (res?.kind !== "leave") {
    // One answer for all four cards: the guide (or the reason) once, in the first.
    const first = parts.away || parts.balances || Object.values(parts)[0];
    first.append(stateNode(res));
    Object.values(parts).forEach((n) => {
      if (n !== first) n.closest(".ppanel")?.setAttribute("hidden", "");
    });
    return;
  }
  Object.values(parts).forEach((n) => n.closest(".ppanel")?.removeAttribute("hidden"));
  const open = (a) => openProfile(a.employee, a.employee_name || a.name, state);

  if (parts.away) {
    const today = res.away_today || [];
    const week = (res.away_week || []).filter((a) => !today.some((x) => x.name === a.name));
    parts.away.append(el("div", "pp-h", `Today, ${fmtDate(res.as_of)}`));
    parts.away.append(today.length ? awayList(today, open)
      : el("div", "pp-empty", "No one is on approved leave today."));
    // On the week's last day there is no "later this week" to show.
    if (res.week?.to && res.week.to > res.as_of) {
      parts.away.append(el("div", "pp-h", `Later this week, to ${fmtDate(res.week.to)}`));
      parts.away.append(week.length ? awayList(week, open)
        : el("div", "pp-empty", "No other approved leave this week."));
    }
  }

  if (parts.pending) {
    const pend = res.pending || [];
    if (!pend.length) {
      parts.pending.append(el("div", "pp-empty", "No leave request is waiting for approval."));
    } else {
      const ul = el("ul", "pp-list");
      pend.forEach((a) => {
        const left = el("div");
        left.append(personLink({ name: a.employee_name, employee: a.employee }, open));
        left.append(el("div", "pp-sub", `${a.leave_type} · ${num(a.days)} day${a.days === 1 ? "" : "s"} · ${range(a.from_date, a.to_date)}`));
        const right = el("span");
        right.append(document.createTextNode(a.waiting_days == null ? "" : `waiting ${a.waiting_days} day${a.waiting_days === 1 ? "" : "s"}`));
        if (a.approver) right.append(el("div", "pp-sub", `with ${a.approver}`));
        if (a.href) {
          const go = el("div");
          go.append(link("Open in ERPNext ↗", a.href));
          right.append(go);
        }
        const row = el("li");
        row.append(left, right);
        ul.append(row);
      });
      parts.pending.append(ul);
    }
  }

  if (parts.balances) drawBalances(parts.balances, res, open);

  if (parts.bydept) {
    const depts = res.departments || [];
    const wrap = el("div", "pp-scroll narrow");
    const t = table(["Department", ["People", 1], ["Days Taken", 1], ["Per Person", 1], ["Took Leave", 1]]);
    const tb = t.querySelector("tbody");
    depts.forEach((d) => {
      const tr = el("tr");
      tr.append(td(d.department), td(d.people.toLocaleString("en-GB"), "num"), td(num(d.days), "num"),
        td(d.per_person == null ? "—" : num(d.per_person), "num"),
        td(`${d.with_leave} of ${d.people}`, "num"));
      tb.append(tr);
    });
    wrap.append(t);
    parts.bydept.append(wrap, el("div", "pp-note", `Approved leave taken from 1 January to ${fmtDate(res.as_of)}, `
      + "every leave type, by each active person's department. Holidays are not counted unless the leave type counts them."));
  }
}

function awayList(items, open) {
  const ul = el("ul", "pp-list");
  items.forEach((a) => {
    const left = el("div");
    left.append(personLink({ name: a.employee_name, employee: a.employee }, open));
    left.append(el("div", "pp-sub", a.leave_type));
    ul.append(li(left, `${range(a.from_date, a.to_date)} · ${num(a.days)} day${a.days === 1 ? "" : "s"}`));
  });
  return ul;
}

function drawBalances(body, res, open) {
  const types = res.types || [];
  const bar = el("div", "filters");
  const q = el("input");
  q.type = "search";
  q.placeholder = "Search a name or department";
  q.setAttribute("aria-label", "Search leave balances");
  const kind = select("Leave type", [
    ...types.map((t) => [t.name, `${t.name} (${t.people})`]), ["*", "All leave types"]]);
  const only = select("Who", [["with", "Only people with this leave"], ["all", "Everyone active"]]);
  const count = el("span", "tcount");
  bar.append(q, kind, only, count);
  const out = el("div");
  body.append(bar, out);
  const sort = { key: "name", dir: 1 };

  const value = (r) => {
    if (kind.value === "*") {
      const all = Object.values(r.balances || {});
      if (!all.length) return null;
      return ["allocated", "taken", "pending", "remaining"].reduce((o, k) => {
        o[k] = all.reduce((s, b) => s + (Number(b[k]) || 0), 0);
        return o;
      }, {});
    }
    return r.balances?.[kind.value] || null;
  };

  const draw = () => {
    const words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    let rows = (res.rows || []).map((r) => ({ r, b: value(r) }))
      .filter(({ r, b }) => (only.value === "all" || b)
        && words.every((w) => `${r.name} ${r.employee} ${r.department}`.toLowerCase().includes(w)));
    const k = sort.key;
    rows.sort((x, y) => {
      if (k === "name" || k === "department") {
        return sort.dir * String(x.r[k] || "").localeCompare(String(y.r[k] || ""));
      }
      const a = x.b ? Number(x.b[k]) : -Infinity;
      const c = y.b ? Number(y.b[k]) : -Infinity;
      return sort.dir * (a - c) || x.r.name.localeCompare(y.r.name);
    });
    count.textContent = `${rows.length.toLocaleString("en-GB")} ${rows.length === 1 ? "person" : "people"}`;
    out.textContent = "";
    if (!rows.length) {
      out.append(el("div", "pp-empty", "No one matches."));
      return;
    }
    const wrap = el("div", "pp-scroll");
    const cols = [["name", "Person"], ["department", "Department"], ["allocated", "Allocated", 1],
      ["taken", "Taken", 1], ["pending", "Pending", 1], ["remaining", "Remaining", 1]];
    const t = el("table", "dt");
    const hr = el("tr");
    cols.forEach(([key, label, isNum]) => {
      const th = el("th");
      if (isNum) th.style.textAlign = "right";
      const b = el("button", "pp-sort", label + (sort.key === key ? (sort.dir > 0 ? " ↑" : " ↓") : ""));
      b.type = "button";
      b.addEventListener("click", () => {
        sort.dir = sort.key === key ? -sort.dir : (isNum ? -1 : 1);
        sort.key = key;
        draw();
      });
      th.append(b);
      th.setAttribute("aria-sort", sort.key === key ? (sort.dir > 0 ? "ascending" : "descending") : "none");
      hr.append(th);
    });
    const thead = el("thead");
    thead.append(hr);
    const tb = el("tbody");
    rows.forEach(({ r, b }) => {
      const tr = el("tr", "pp-row");
      tr.tabIndex = 0;
      tr.setAttribute("role", "button");
      tr.setAttribute("aria-label", `Open ${r.name}'s profile`);
      tr.append(td(two(r.name, r.designation)), td(r.department || "—"));
      ["allocated", "taken", "pending", "remaining"].forEach((key) => {
        const v = b ? b[key] : null;
        const cell = td(v == null ? "—" : (key === "pending" && !v ? "—" : num(v)), "num");
        if (key === "remaining" && b && b.allocated > 0 && v <= 0) cell.style.color = "var(--high)";
        tr.append(cell);
      });
      const go = () => open({ employee: r.employee, employee_name: r.name });
      tr.addEventListener("click", go);
      tr.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          go();
        }
      });
      tb.append(tr);
    });
    t.append(thead, tb);
    wrap.append(t);
    out.append(wrap);
  };
  q.addEventListener("input", draw);
  kind.addEventListener("change", draw);
  only.addEventListener("change", draw);
  draw();
  const notes = [`As at ${fmtDate(res.as_of)}, for each person's leave period in force then. `
    + "Allocated includes leave carried forward; taken is approved leave in that period; "
    + "remaining is what is left, as ERPNext's own leave balance counts it."];
  if (res.without) {
    notes.push(`${res.without.toLocaleString("en-GB")} active ${res.without === 1 ? "person has" : "people have"} no leave allocated for that period.`);
  }
  const note = el("div", "pp-note", notes.join(" "));
  if (res.href) {
    note.append(document.createTextNode(" "));
    note.append(link("Employee Leave Balance in ERPNext ↗", res.href));
  }
  body.append(note);
}

/* ------------------------------------------------------------------ shared */
function stateNode(res) {
  if (res?.kind === "guide" && res.guide) return guideBox(res.guide);
  if (res?.kind === "unreachable") {
    const who = res.business ? `${res.business}'s` : "the business's";
    let when = "";
    if (res.last_loaded) {
      const d = new Date(String(res.last_loaded).replace(" ", "T"));
      if (!Number.isNaN(d.getTime())) {
        when = ` Last loaded ${d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}.`;
      }
    }
    return el("div", "thin", `Can't reach ${who} ERPNext right now — showing nothing new until it's back.${when}`);
  }
  if (res?.kind === "missing") return el("div", "thin", res.message || "This person is not on the books.");
  if (res?.kind === "refused") {
    return el("div", "thin", "The business's ERPNext refused this read: the platform's key there "
      + "may not have permission for HR records.");
  }
  return el("div", "thin", res?.message
    ? `This could not be read just now: ${res.message}`
    : "This could not be read from ERPNext just now. It will be tried again shortly.");
}

function partNode(part, empty) {
  if (part?.guide) return guideBox(part.guide, { compact: true });
  if (part?.state === "unreadable") return el("div", "pp-empty", "This part could not be read from ERPNext.");
  return el("div", "pp-empty", empty);
}

function section(box, title) {
  box.append(el("div", "sect", title));
}

function who(p) {
  const w = el("div", "pp-who");
  w.append(avatar(p));
  w.append(two(p.name, [p.designation, p.employee].filter(Boolean).join(" · "), true));
  return w;
}

function avatar(p, big = false) {
  const a = el("span", `pp-av${big ? " big" : ""}`);
  a.setAttribute("aria-hidden", "true");
  const initials = (p.name || "?").split(/\s+/).filter(Boolean).slice(0, 2)
    .map((w) => w[0]).join("").toUpperCase();
  a.textContent = initials;
  if (p.photo) {
    const img = el("img");
    img.alt = "";
    img.loading = "lazy";
    img.referrerPolicy = "no-referrer";
    img.addEventListener("load", () => a.replaceChildren(img));
    img.src = p.photo;
  }
  return a;
}

function personLink(p, open) {
  const s = el("span", "lnk", p.name || p.employee);
  s.setAttribute("role", "button");
  s.tabIndex = 0;
  s.addEventListener("click", () => open(p));
  s.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open(p);
    }
  });
  return s;
}

function link(text, href) {
  if (!href) return document.createTextNode(text || "");
  const a = el("a", "lnk", text || "");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}

function li(left, right) {
  const n = el("li");
  const a = el("span");
  if (left instanceof Node) a.append(left); else a.textContent = left ?? "";
  const b = el("span", null, right ?? "");
  n.append(a, b);
  return n;
}

function chip(label, n) {
  const c = el("span", "chip");
  c.append(document.createTextNode(`${label} `), el("b", null, String(n)));
  return c;
}

function two(main, sub, bold = false) {
  const d = el("div");
  d.append(bold ? el("b", null, main) : document.createTextNode(main ?? ""));
  if (sub) d.append(el("div", "pp-sub", sub));
  return d;
}

function statusTag(s) {
  return tag(s || "Active", s === "Active" ? "t-ok" : s === "Left" ? "t-dr" : "t-wt");
}

function tag(text, cls) {
  return el("span", `tag ${cls}`, text);
}

function table(heads) {
  const t = el("table", "dt");
  const tr = el("tr");
  heads.forEach((h) => {
    const [label, isNum] = Array.isArray(h) ? h : [h, 0];
    const th = el("th", null, label);
    if (isNum) th.style.textAlign = "right";
    tr.append(th);
  });
  const thead = el("thead");
  thead.append(tr);
  t.append(thead, el("tbody"));
  return t;
}

function td(content, cls) {
  const c = el("td", cls || null);
  if (content instanceof Node) c.append(content); else c.textContent = content ?? "";
  return c;
}

function select(label, options) {
  const s = el("select");
  s.setAttribute("aria-label", label);
  options.forEach(([v, t]) => {
    const o = el("option", null, t);
    o.value = v;
    s.append(o);
  });
  return s;
}

function fill(sel, values) {
  values.forEach((v) => {
    if ([...sel.options].some((o) => o.value === v)) return;
    const o = el("option", null, v);
    o.value = v;
    sel.append(o);
  });
}

function button(text, fn) {
  const b = el("button", "btn", text);
  b.type = "button";
  b.addEventListener("click", fn);
  return b;
}

function num(v) {
  const n = Number(v) || 0;
  return Number.isInteger(n) ? n.toLocaleString("en-GB")
    : n.toLocaleString("en-GB", { maximumFractionDigits: 2 });
}

function fmtDate(v) {
  if (!v) return "";
  const d = new Date(`${String(v).slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? String(v)
    : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function range(a, b) {
  if (!a) return "";
  return a === b || !b ? fmtDate(a) : `${fmtDate(a)} to ${fmtDate(b)}`;
}

function el(tag_, className, text) {
  const node = document.createElement(tag_);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
