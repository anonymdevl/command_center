import React, { useEffect, useMemo, useState } from "react";
import { boot, isLive } from "./api/boot.js";
import { initAppearance } from "./appearance.js";
import Topbar from "./components/Topbar.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Drawer from "./components/Drawer.jsx";
import LegacyView from "./components/LegacyView.jsx";
import Sales from "./views/Sales.jsx";
import nav from "./legacy/nav.json";

/**
 * Views that have become components. Everything else renders its generated
 * markup through LegacyView, so the interface keeps full parity while it is
 * converted a screen at a time.
 */
const PORTED = {
  sales: Sales,
};

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
      const k = (window.location.hash || "").replace(/^#/, "");
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
  const anyLive = (boot.live || []).length > 0;
  const showBanner = !anyLive || !isLive(view);

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
    <div className="dnote" style={{ margin: "14px 26px 0" }}>
      <span className="dn-i">●</span>
      <span>
        <b>Illustrative figures.</b> The design and the workings are real; the numbers
        on this screen are still the demonstration extract. Each area is wired to the
        loaded facts in turn, and a screen drops this line the moment it reads them.
      </span>
    </div>
  );
}
