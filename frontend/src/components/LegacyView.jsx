import React, { useEffect, useRef, useState } from "react";
import views from "../legacy/views.json";
import extras from "../legacy/extras.json";
import { boot } from "../api/boot.js";
import { renderGreeting } from "../greeting.js";
import { api } from "../api/client.js";
import { useApi } from "../useApi.js";
import Records from "./Records.jsx";
import { hydrateCards, keysFor } from "../legacy/hydrate.js";
import { renderAnswer, renderThinking, renderFailure } from "../legacy/answer.js";

/**
 * A designed screen, with live figures put into it.
 *
 * Not a scaffold any more. The designed views are the product: the spacing, the card
 * contract, the wording and the panel structure were settled over many rounds, and
 * rewriting them as components threw that away and demonstrated something other than
 * what was designed.
 *
 * So the markup renders exactly as generated, and legacy/hydrate.js then replaces the
 * figures inside the cards it has a KPI for and wires them to the real records. A card
 * with nothing behind it keeps its designed figure and says on itself that it is
 * illustrative.
 *
 * The markup is ours, generated at build time, which is why dangerouslySetInnerHTML is
 * acceptable in this one place. Nothing from the API is ever written as HTML: the
 * hydrator sets textContent and builds elements.
 */
export default function LegacyView({ viewKey, scope, openDrawer }) {
  const ref = useRef(null);
  const html = views[viewKey];
  const [liveCount, setLiveCount] = useState(null);

  // The runSearch handler is installed once, but the business can change under it. A
  // ref keeps it reading the current scope rather than the one captured at install.
  const scopeRef = useRef(scope);
  scopeRef.current = scope;

  const keys = keysFor(viewKey);
  const figures = useApi(
    () => (keys.length ? api.kpis({ keys, business_code: scope }) : Promise.resolve(null)),
    [viewKey, scope, keys.join(",")],
    { skip: keys.length === 0 }
  );

  // The generated markup calls these by name from inline onclick attributes.
  useEffect(() => {
    const show = (map) => (key) => {
      const content = map[key];
      if (content) openDrawer({ html: content });
    };
    window.openDrawer = show(extras.drawers);
    window.explain = show(extras.explainers);
    window.drill = show(extras.drill);
    window.closeDrawer = () => openDrawer(null);

    // The designed Ask screen calls runSearch(value) from its own input and its own
    // suggestion buttons, and expects the answer in its own #sout2. So it is wired
    // rather than replaced: same markup, same ids, real answers.
    window.runSearch = async (question) => {
      const out = document.getElementById("sout2") || document.getElementById("sout");
      if (!out) return;
      const q = (question || "").trim();
      if (!q) return;
      renderThinking(out, q);
      try {
        const payload = await api.ask({ question: q, business_code: scopeRef.current });
        renderAnswer(out, payload, {
          onOpen: (records, title) =>
            openDrawer(
              <Records
                scope={scopeRef.current}
                fact={records.fact}
                filters={records.filters}
                title={title?.slice(0, 80) || "The records behind it"}
                openDrawer={openDrawer}
              />
            ),
        });
      } catch (e) {
        renderFailure(out, e?.message);
      }
    };

    return () => {
      delete window.openDrawer;
      delete window.explain;
      delete window.drill;
      delete window.closeDrawer;
      delete window.runSearch;
    };
  }, [openDrawer]);

  // The generated markup has an empty #greet that the old script filled on a
  // timer. Ported here so the command screen still greets the person by name
  // until that view becomes a component.
  useEffect(() => {
    const el = ref.current?.querySelector("#greet");
    if (!el) return;
    renderGreeting(el, boot.user);
    const t = setInterval(() => renderGreeting(el, boot.user), 30000);
    return () => clearInterval(t);
  }, [viewKey]);

  // Live figures into the designed cards. Runs after the markup is in the DOM and
  // again whenever the figures or the business change.
  useEffect(() => {
    const root = ref.current;
    if (!root || !html) return;
    const live = hydrateCards(root, viewKey, figures.data, {
      onOpen: (figure) =>
        figure.drill?.fact
          ? openDrawer(
              <Records
                scope={scope}
                fact={figure.drill.fact}
                filters={figure.drill.filters}
                title={figure.label}
                subset={figure.subset_of}
                openDrawer={openDrawer}
              />
            )
          : undefined,
    });
    setLiveCount(live);
  }, [viewKey, html, figures.data, scope, openDrawer]);

  // Tabs inside the generated markup are plain DOM, so they are wired here
  // rather than reimplemented.
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const onClick = (e) => {
      const tab = e.target.closest(".tab");
      if (!tab) return;
      const bar = tab.closest(".tabbar");
      const group = bar?.dataset.g;
      if (!group) return;
      bar.querySelectorAll(".tab").forEach((b) => b.classList.remove("on"));
      tab.classList.add("on");
      const index = Array.from(bar.querySelectorAll(".tab")).indexOf(tab);
      root
        .querySelectorAll(`.tabpane[data-g="${group}"]`)
        .forEach((p) => p.classList.toggle("on", String(p.dataset.i) === String(index)));
    };
    root.addEventListener("click", onClick);
    return () => root.removeEventListener("click", onClick);
  }, [viewKey]);

  if (!html) {
    return (
      <div className="view on">
        <div className="warn">
          <b>No screen called “{viewKey}”.</b> The link that brought you here points at
          something that does not exist.
        </div>
      </div>
    );
  }

  return (
    <>
      {figures.error ? (
        <div className="warn" style={{ margin: "0 0 14px" }}>
          <b>The live figures could not be read.</b> {figures.error.message} The screen
          below is showing its designed demonstration values.
        </div>
      ) : null}
      <div className="view on" ref={ref} dangerouslySetInnerHTML={{ __html: html }} />
    </>
  );
}
