import React, { useEffect, useRef } from "react";
import views from "../legacy/views.json";
import extras from "../legacy/extras.json";
import { boot } from "../api/boot.js";
import { renderGreeting } from "../greeting.js";

/**
 * A view that has not been converted yet.
 *
 * Renders the generated markup so the interface keeps working screen by screen
 * while components replace it. This is a migration scaffold and nothing else --
 * every view here is one still to be written, and when views.json is empty this
 * component and the generators go with it.
 *
 * The markup is ours, generated at build time from fixed demonstration content.
 * No value here comes from the API, which is why dangerouslySetInnerHTML is
 * acceptable in this one place and nowhere else. A converted view renders through
 * React and is escaped.
 */
export default function LegacyView({ viewKey, openDrawer }) {
  const ref = useRef(null);
  const html = views[viewKey];

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
    return () => {
      delete window.openDrawer;
      delete window.explain;
      delete window.drill;
      delete window.closeDrawer;
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
    <div className="view on" ref={ref} dangerouslySetInnerHTML={{ __html: html }} />
  );
}
