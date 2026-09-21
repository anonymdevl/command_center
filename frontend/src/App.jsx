import React, { useEffect, useMemo, useState } from "react";
import { boot } from "./api/boot.js";
import { initAppearance } from "./appearance.js";
import Topbar from "./components/Topbar.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Drawer from "./components/Drawer.jsx";
import LegacyView from "./components/LegacyView.jsx";
import nav from "./legacy/nav.json";

/**
 * Views that have become components. Everything else renders its generated
 * markup through LegacyView, so the interface keeps full parity while it is
 * converted a screen at a time.
 */
/**
 * Views that have become components.
 *
 * Empty on purpose. I replaced eight designed screens with layouts of my own -- the
 * same mistake as Command, eight more times. Converting a screen means putting real
 * figures into the screen that was designed, not substituting a different screen.
 *
 * The designed views render as designed, and the figures inside them are hydrated from
 * the KPI engine by data-kpi. See LegacyView.
 */
const PORTED = {};

initAppearance();

export default function App() {
  const [view, setView] = useState("command");
  const [scope, setScope] = useState(() => {
    const real = (boot.scopes || []).filter((s) => s.code !== "__all__");
    return real.length === 1 ? real[0].code : boot.scopes?.[0]?.code || "__all__";
  });
  const [drawer, setDrawer] = useState(null);

  // Deep-link by hash so a manager can send someone a screen.
  useEffect(() => {
    const apply = () => {
      let k = (window.location.hash || "").replace(/^#/, "");
      // "Find anything" and "Ask the business" are one screen now. An old link should
      // land on it rather than on "no screen called search".
      if (k === "search") k = "ask";
      if (k) setView(k);
    };
    apply();
    window.addEventListener("hashchange", apply);
    return () => window.removeEventListener("hashchange", apply);
  }, []);

  const go = (key) => {
    setView(key);
    setDrawer(null);
    window.history.replaceState(null, "", `#${key}`);
    const main = document.getElementById("cc-main");
    if (main) main.scrollTop = 0;
  };

  const Ported = PORTED[view];
  // Every designed screen still has at least one card with no fact behind it, and the
  // cards say which they are. The old all-or-nothing "this view is live" flag stopped
  // being true the moment figures were hydrated card by card, so it is gone rather
  // than left half-right.
  const showBanner = !Ported;

  const ctx = useMemo(() => ({ scope, go, openDrawer: setDrawer }), [scope]);

  return (
    <div className="shell">
      <Topbar scope={scope} onScope={setScope} />
      <div className="body">
        <Sidebar nav={nav} current={view} onGo={go} />
        <div className="main" id="cc-main">
          {showBanner ? <IllustrativeNotice /> : null}
          {Ported ? <Ported {...ctx} /> : <LegacyView viewKey={view} {...ctx} />}
        </div>
      </div>
      <Drawer content={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}

/**
 * One line, shown while a screen still reads the demonstration extract.
 *
 * It disappears per screen as each is wired. A caveat that is sometimes wrong
 * makes the absence of a caveat worthless, so this is driven by the server's
 * list of live views rather than by anyone remembering to remove it.
 */
function IllustrativeNotice() {
  return (
    // No horizontal margin: it sits inside .main alongside the view's own
    // banners, so any inset here makes it narrower than they are.
    <div className="dnote" style={{ margin: "0 0 18px" }}>
      <span className="dn-i">●</span>
      <span>
        <b>Some figures on this screen are still illustrative.</b> Cards reading the
        loaded ERPNext data show their real value and open to the records behind it;
        cards still showing demonstration values say so on the card itself.
      </span>
    </div>
  );
}
