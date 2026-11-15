/**
 * "Nothing recorded yet -- here is how to fill it", drawn the same way everywhere.
 *
 * A production screen never shows sample figures. When the business's ERPNext holds
 * nothing behind a card, a tile or a panel, the server sends a guide
 * (command_center/guides.py): a sentence, the steps to take in ERPNext, and a link to
 * the right page on the business's own site. Plain text only; every node built here.
 *
 *   guideBox(guide)            -> an element to put inside a panel
 *   guideCard(node, guide, open) -> a card or tile: "—" figure, a "Set up" flag, and the
 *                                 guide opened in the drawer when the card is clicked
 */

export function guideBox(guide, { compact = false } = {}) {
  const box = el("div", `guide${compact ? " guide-compact" : ""}`);
  box.append(el("p", "guide-t", guide?.text || "Nothing is recorded in ERPNext for this yet."));
  const steps = guide?.steps || [];
  if (steps.length) {
    const ol = el("ol", "guide-s");
    steps.forEach((s) => ol.append(el("li", null, s)));
    box.append(ol);
  }
  if (guide?.href) {
    const a = el("a", "btn guide-a", guide.label || "Open in ERPNext");
    a.href = guide.href;
    a.target = "_blank";
    a.rel = "noopener";
    box.append(a);
  }
  return box;
}

/** A card (.kpi) or tile (.bk) with nothing behind it yet. */
export function guideCard(node, guide, openDrawer) {
  if (!node || !guide) return;
  delete node.dataset.illustrative;
  node.dataset.live = "1";
  node.dataset.setup = "1";
  const val = node.querySelector(".val, .v");
  if (val) val.textContent = "—";
  const foot = node.querySelector(".delta, .foot, .s");
  if (foot) foot.textContent = "Not recorded yet · how to set it up";
  setPill(node, "set up");
  node.removeAttribute("onclick");
  node.classList.add("clickable");
  const open = () => openDrawer && openDrawer(drawerContent(node, guide));
  node.onclick = open;
  node.setAttribute("role", "button");
  node.setAttribute("tabindex", "0");
  node.onkeydown = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open();
    }
  };
}

function drawerContent(node, guide) {
  const wrap = el("div", "guide-drawer");
  const title = node.querySelector(".lab, .l")?.textContent?.trim();
  if (title) wrap.append(el("h3", null, title));
  wrap.append(guideBox(guide));
  return { node: wrap };
}

function setPill(node, text) {
  const head = node.classList.contains("bk") ? node : node.querySelector(".khead") || node;
  let pill = head.querySelector(":scope > .flag[data-prov]");
  if (!pill) {
    pill = el("span", "flag f-dim");
    pill.dataset.prov = "1";
    head.append(pill);
  }
  pill.className = "flag f-dim";
  pill.textContent = text;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
