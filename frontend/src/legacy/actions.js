/**
 * Making the designed screens' action buttons do something.
 *
 * The alert cards, findings and approvals were designed with buttons -- Assign, a "⋯"
 * menu of Request evidence / Approve / Defer / Escalate / Dismiss, Raise it, Approve /
 * Reject -- and none of them had a handler: the "⋯" called a moreMenu() that only the
 * first HTML prototype defined. On a client demo, a button that does nothing reads as
 * a product that does nothing.
 *
 * Each now does something real or says plainly why it cannot:
 *
 *   Assign, Request evidence, Escalate, Raise it, Give it an owner, Pass to someone
 *   else, Ask for more  ->  the action dialog: a real ERPNext To-Do, as the manager
 *   Ask AI about this   ->  the question bar, already asked
 *   Open the records    ->  the drawer the alert's own source chip opens
 *   Approve, Reject, Accept it, Send it back on the sample requests  ->  says they are
 *       samples; deciding real ERPNext approvals here is the approvals inbox, not yet
 *       built
 *   Load older on the audit trail  ->  ERPNext's own change log
 *   Approve, Defer, Dismiss in an alert's menu  ->  removed: they need the alert engine
 *       to remember a decision, and a button that pretends to is worse than none.
 */

const TO_DIALOG = {
  "assign": "assign", "request evidence": "evidence", "escalate": "escalate",
  "raise it": "finding", "raise as a finding": "finding", "give it an owner": "assign",
  "pass to someone else": "assign", "ask for more": "evidence",
};
const SAMPLE_DECISIONS = new Set(["approve", "reject", "accept it", "send it back", "cancel it"]);
const SAMPLE_NOTE = "This is a sample from the design, so there is nothing in ERPNext to decide yet. "
  + "Deciding your real ERPNext approvals from here is the approvals inbox, which is not built yet.";

export function wireActions(root) {
  if (!root) return;
  root.querySelectorAll(".alert").forEach(wireAlert);
  // Buttons outside the alert cards: findings rows, panels.
  root.querySelectorAll("button").forEach((b) => {
    if (b.dataset.ccWired || b.getAttribute("onclick") || b.closest(".tabbar, .alert[data-cc-wired]")) return;
    const fn = handlerFor(label(b), contextFor(b), b, null);
    if (fn) attach(b, fn);
  });
}

/**
 * An alert keeps its own buttons, in its own order -- "Assign" on a cash alert, "Raise
 * as a finding" on a risk, "Approve" on a request -- and each gets the handler its label
 * means. The dead "⋯" is replaced by a working menu of the same items, plus the records
 * behind the alert; "Ask AI about this" sits after the main button.
 */
function wireAlert(card) {
  if (card.dataset.ccWired) return;
  card.dataset.ccWired = "1";
  const ctx = {
    title: text(card, ".awhat"),
    detail: [text(card, ".awhy"), text(card, ".asw")].filter(Boolean).join("\n"),
    owner: ownerOf(card),
  };
  const source = card.querySelector(".chip.src[onclick]");

  card.querySelectorAll(".acts").forEach((acts) => {
    acts.querySelectorAll(":scope > button").forEach((b) => {
      if (b.getAttribute("onclick")) return;
      const fn = handlerFor(label(b), ctx, b, source);
      if (fn) attach(b, fn);
      else b.remove();
    });

    const items = [];
    const more = acts.querySelector(".more");
    more?.querySelectorAll(".moremenu button").forEach((b) => {
      // "Approve" in an alert's menu is not a request waiting on anyone.
      // The menu item is replaced, so a notice anchors on the live action row.
      const fn = label(b) === "approve" ? null : handlerFor(label(b), ctx, acts, source);
      if (fn) items.push([b.textContent.trim(), fn, b.classList.contains("dgr")]);
    });
    more?.remove();

    const primary = acts.querySelector(":scope > button");
    if (acts === card.querySelector(".acts") && ctx.title) {
      const ai = button("Ask AI about this", "btn", () => askAbout(ctx.title));
      primary ? primary.after(ai) : acts.prepend(ai);
      if (source) items.push(["Open the records", () => source.click(), false]);
    }
    if (items.length) acts.append(menu(items));
  });
}

function handlerFor(name, ctx, anchor, source) {
  if (TO_DIALOG[name]) return () => openDialog(TO_DIALOG[name], ctx);
  if (SAMPLE_DECISIONS.has(name)) return () => notice(anchor, SAMPLE_NOTE);
  if (name === "open the pack") return source ? () => source.click() : null;
  if (name === "load older") return () => window.open("/app/version", "_blank", "noopener");
  // Defer, Dismiss and anything else unlisted: removed from an alert (only an alert
  // engine could remember them), left alone elsewhere.
  return null;
}

/* ------------------------------------------------------------------ helpers */
function openDialog(kind, ctx) {
  window.dispatchEvent(new CustomEvent("cc-action", { detail: { kind, ...ctx } }));
}

function askAbout(title) {
  window.dispatchEvent(new CustomEvent("cc-ask", {
    detail: { question: `${title}. What is behind this, and what should we do about it?` },
  }));
}

function contextFor(b) {
  const row = b.closest("tr");
  if (row) {
    const cells = Array.from(row.querySelectorAll("td")).map((td) => (td.textContent || "").trim())
      .filter((t) => t && t.length < 300 && !/^(raise it|open|give it an owner)$/i.test(t));
    return { title: cells[0] || "From the Command Center", detail: cells.slice(1).join(" · ") };
  }
  const card = b.closest(".alert, .panel, .kpi, .bk") || b.parentElement;
  const head = card?.querySelector(".awhat, .ph b, h4, b");
  return { title: (head?.textContent || "From the Command Center").trim(),
           detail: text(card, ".awhy") };
}

function ownerOf(card) {
  const chip = Array.from(card.querySelectorAll(".chip")).find((c) => /^owner\b/i.test(c.textContent.trim()));
  return chip ? chip.textContent.trim().replace(/^owner\s*/i, "") : "";
}

function text(root, sel) {
  return (root?.querySelector(sel)?.textContent || "").trim().replace(/^→\s*/, "");
}

function label(b) {
  return (b.textContent || "").trim().toLowerCase();
}

function attach(b, fn) {
  b.dataset.ccWired = "1";
  b.type = "button";
  b.onclick = (e) => {
    e.stopPropagation();
    fn();
  };
}

function button(name, cls, onClick) {
  const b = document.createElement("button");
  b.className = cls;
  b.textContent = name;
  attach(b, onClick);
  return b;
}

/** A small menu: opens on click, closes on the next click anywhere or Escape. */
export function menu(items) {
  const wrap = document.createElement("span");
  wrap.className = "amenu";
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "amenu-b";
  trigger.setAttribute("aria-label", "More actions");
  trigger.setAttribute("aria-haspopup", "menu");
  trigger.textContent = "⋯";
  const list = document.createElement("div");
  list.className = "amenu-l";
  list.setAttribute("role", "menu");
  items.forEach(([name, fn, danger]) => {
    const it = document.createElement("button");
    it.type = "button";
    it.setAttribute("role", "menuitem");
    if (danger) it.className = "dgr";
    it.textContent = name;
    it.onclick = (e) => {
      e.stopPropagation();
      close();
      fn();
    };
    list.append(it);
  });
  const close = () => {
    wrap.classList.remove("on");
    trigger.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", close);
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (e) => e.key === "Escape" && close();
  trigger.onclick = (e) => {
    e.stopPropagation();
    if (wrap.classList.contains("on")) return close();
    wrap.classList.add("on");
    // Open upwards when there is no room below (the last alert on a screen).
    const r = trigger.getBoundingClientRect();
    wrap.classList.toggle("flip", window.innerHeight - r.bottom < 220);
    trigger.setAttribute("aria-expanded", "true");
    setTimeout(() => {
      document.addEventListener("click", close);
      document.addEventListener("keydown", onKey);
    });
  };
  wrap.append(trigger, list);
  return wrap;
}

/** A short explanation next to a button that cannot do what it says yet. */
function notice(anchor, message) {
  const host = anchor.closest(".alert, .panel") || anchor.parentElement;
  host.querySelector(":scope > .act-notice")?.remove();
  const n = document.createElement("div");
  n.className = "act-notice";
  n.setAttribute("role", "status");
  n.textContent = message;
  host.append(n);
  setTimeout(() => n.remove(), 9000);
}
