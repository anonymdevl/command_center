/**
 * Everything in a screen's markup that opens something on a click opens on Enter or Space
 * too (18 Nov 2026).
 *
 * The generated screens (interface/views_*.py) put an inline onclick on a panel's heading
 * ("What Is This? →", the explainer drawer), on the tiles that go to another screen and
 * on a few links. As plain divs and spans they could not be reached with Tab at all, so
 * a keyboard user could open no explanation. Each gets a place in the Tab order and the
 * button role here. A tile that hydrate.js wires to its figure drawer has its own keys
 * (onkeydown) and is left to them, so Enter never opens two drawers.
 */

const PLAIN = "[onclick]:not(button):not(a):not(input):not(select):not(textarea)";

function press(e) {
  const node = e.currentTarget;
  if (e.target !== node || node.onkeydown) return;
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    node.click();
  }
}

/** Makes the clickable markup under root keyboard-operable. */
export function wireKeys(root) {
  if (!root) return;
  root.querySelectorAll(PLAIN).forEach((node) => {
    if (node.dataset.keys) return;
    node.dataset.keys = "1";
    if (!node.hasAttribute("tabindex")) node.tabIndex = 0;
    if (!node.hasAttribute("role")) node.setAttribute("role", "button");
    node.addEventListener("keydown", press);
  });
}
