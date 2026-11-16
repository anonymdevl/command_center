import React, { useCallback, useEffect, useMemo, useState } from "react";
import { boot, brand } from "./api/boot.js";
import { initAppearance } from "./appearance.js";
import Topbar from "./components/Topbar.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Drawer from "./components/Drawer.jsx";
import LegacyView from "./components/LegacyView.jsx";
import ViewTools from "./components/ViewTools.jsx";
import ActionDialog from "./components/ActionDialog.jsx";
import ScheduleDialog from "./components/ScheduleDialog.jsx";
import Settings, { isAdministrator } from "./components/Settings.jsx";
import PlanUsage from "./components/PlanUsage.jsx";
import { LicenceBanner } from "./components/PlanBadge.jsx";
import nav from "./legacy/nav.json";
import { CORE_VIEWS } from "./legacy/core.js";
import { restore } from "./askHistory.js";

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
  // The drawer keeps a short history: following a link inside it (a record, a person,
  // the records behind a figure) opens the next one on top, and Back returns to the one
  // before. Closing it, or moving to another screen, clears the history.
  const [drawerStack, setDrawerStack] = useState([]);
  const drawer = drawerStack.length ? drawerStack[drawerStack.length - 1] : null;
  const setDrawer = useCallback((content) => {
    setDrawerStack((s) => (content == null ? [] : [...s, content].slice(-20)));
  }, []);
  const drawerBack = useCallback(() => setDrawerStack((s) => s.slice(0, -1)), []);
  // Phones: the sidebar is a drawer, open only while choosing a screen.
  const [navOpen, setNavOpen] = useState(false);

  // The person's latest conversation with the AI, back after a refresh or a sign-in, so
  // a follow-up in the bar still knows what was asked before.
  useEffect(() => {
    restore(scope);
  }, [scope]);

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
    setNavOpen(false);
    window.history.replaceState(null, "", `#${key}`);
    const main = document.getElementById("cc-main");
    if (main) main.scrollTop = 0;
  };

  // Settings is the platform administrator's own page, not a designed screen. Anyone
  // else who opens #settings sees the designed "not available to your role" panel.
  const settings = view === "settings";
  // Plan & Usage: a customer's Account Managers only (insights/core/plans.py); the server
  // refuses everyone else too.
  const plan = view === "plan";
  const Ported = PORTED[view];
  // Every designed screen still has at least one card with no fact behind it, and the
  // cards say which they are. The old all-or-nothing "this view is live" flag stopped
  // being true the moment figures were hydrated card by card, so it is gone rather
  // than left half-right.
  // The management screens hold no sample at all (legacy/core.js), so the caveat would
  // be false on them.
  const showBanner = !Ported && !settings && !plan && !CORE_VIEWS.has(view);

  const ctx = useMemo(() => ({ scope, go, openDrawer: setDrawer }), [scope, setDrawer]);

  return (
    <div className={`shell${navOpen ? " navopen" : ""}`}>
      <Sidebar nav={nav} current={view} onGo={go} scope={scope} onScope={setScope} />
      {navOpen ? <div className="scrim-nav" onClick={() => setNavOpen(false)} /> : null}
      <div className="col">
        <Topbar scope={scope} openDrawer={setDrawer} onGo={go} onMenu={() => setNavOpen((o) => !o)} />
        <main className="main" id="cc-main">
          {!settings && !plan ? <ViewTools caption={captionOf(view)} scope={scope} /> : null}
          <LicenceBanner />
          {showBanner ? <IllustrativeNotice /> : null}
          {settings ? (
            isAdministrator(boot) ? <Settings /> : <LegacyView viewKey="denied" {...ctx} />
          ) : plan ? (
            boot.plan?.can_view ? <PlanUsage /> : <LegacyView viewKey="denied" {...ctx} />
          ) : Ported ? (
            <Ported {...ctx} />
          ) : (
            <LegacyView viewKey={view} {...ctx} />
          )}
        </main>
      </div>
      <Drawer content={drawer} onClose={() => setDrawer(null)}
              onBack={drawerStack.length > 1 ? drawerBack : null}
              trail={[captionOf(view), ...drawerStack.slice(0, -1).map(drawerTitle)].filter(Boolean)} />
      <ActionDialog scope={scope} />
      <ScheduleDialog scope={scope} />
    </div>
  );
}

/** What a drawer in the stack is about, for the breadcrumb of the one above it. */
function drawerTitle(content) {
  const p = React.isValidElement(content) ? content.props || {} : {};
  return p.title || p.figure?.label || null;
}

function captionOf(key) {
  for (const g of nav.groups) {
    const it = g.items.find((i) => i.key === key);
    if (it) return it.label;
  }
  return brand.product;
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
    <div className="dnote">
      <span className="dn-i">●</span>
      <span>
        <b>Some figures on this screen are still illustrative.</b> Cards reading the
        loaded ERPNext data show their real value and open to the records behind it;
        cards still showing demonstration values say so on the card itself.
      </span>
    </div>
  );
}
