/**
 * "Your conversations" on the Ask AI screen: the person's earlier conversations with the
 * AI (api/conversations.py), newest first, to open again or delete.
 */
import { api } from "../api/client.js";
import { clearTurns, currentConversation, open } from "../askHistory.js";

export async function renderConversations(root, scope) {
  const box = root?.querySelector("#askconvs");
  if (!box) return;
  let list = [];
  try {
    list = (await api.convRecent(scope)) || [];
  } catch {
    box.hidden = true;
    return;
  }
  if (!document.body.contains(box)) return;
  box.textContent = "";
  box.hidden = !list.length;
  if (!list.length) return;
  const head = el("div", "askconvs-h");
  // "New conversation" is the button above the thread; this list only opens and deletes.
  head.append(el("b", null, "Your conversations"));
  box.append(head);
  const ul = el("ul", "askconvs-l");
  const now = currentConversation(scope);
  list.slice(0, 8).forEach((c) => {
    const li = el("li", c.name === now ? "on" : "");
    const b = el("button", "askconv");
    b.type = "button";
    b.append(el("span", "askconv-t", c.title || "Conversation"),
      el("span", "askconv-m", `${when(c.last_at)} · ${c.turn_count || 0} question${c.turn_count === 1 ? "" : "s"}`));
    b.onclick = async () => {
      await open(c.name, scope);
      window.drawThread?.();
      renderConversations(root, scope);
    };
    const x = el("button", "askconv-x", "×");
    x.type = "button";
    x.title = "Delete this conversation";
    x.setAttribute("aria-label", `Delete “${c.title}”`);
    x.onclick = async (e) => {
      e.stopPropagation();
      if (!window.confirm(`Delete “${c.title}”? It cannot be brought back.`)) return;
      await api.convRemove(c.name).catch(() => {});
      if (c.name === now) {
        clearTurns(scope);
        window.drawThread?.();
      }
      renderConversations(root, scope);
    };
    li.append(b, x);
    ul.append(li);
  });
  box.append(ul);
}

function when(ts) {
  const d = new Date(String(ts || "").replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return "";
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days < 1) return `today ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
  if (days < 2) return "yesterday";
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}
