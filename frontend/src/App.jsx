import React, { useCallback, useEffect, useMemo, useState } from "react";
import { boot, brand } from "./api/boot.js";
import { initAppearance } from "./appearance.js";
import Topbar from "./components/Topbar.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Drawer from "./components/Drawer.jsx";
import LegacyView from "./components/LegacyView.jsx";
import ViewTools from "./components/ViewTools.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import ActionDialog from "./components/ActionDialog.jsx";
import ScheduleDialog from "./components/ScheduleDialog.jsx";
import Settings, { isAdministrator } from "./components/Settings.jsx";
import PlanUsage from "./components/PlanUsage.jsx";
import { LicenceBanner } from "./components/PlanBadge.jsx";
import nav from "./legacy/nav.json";
import { CORE_VIEWS } from "./legacy/core.js";
import { restore } from "./askHistory.js";
import { stack, useLayer } from "./backstack.js";

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
  // Each entry carries its own id, which keys the drawer's content (Drawer.jsx): two
  // drawers of the same kind one after the other -- Explain This on one figure, then
  // another figure; Back -- are two drawers, never the first one's state (its
  // explanation, tab, search, sort) under the second one's title.
  // Each drawer is also an entry in the browser's history (backstack.js): the browser's
  // Back closes the top one and leaves the screen as it was; the drawer's own Back, X,
  // Escape and the scrim take its entry off again, so the next Back goes to the screen
  // before. `{ replace: true }` swaps the top drawer's content in place (a profile that
  // has finished loading), so Back never returns to its "Reading…".
  const [drawerStack, setDrawerStack] = useState([]);
  const top = drawerStack.length ? drawerStack[drawerStack.length - 1] : null;
  const drawer = top ? top.content : null;
  const setDrawer = useCallback((content, { replace = false } = {}) => {
    if (content == null) {
      stack().closeKind("drawer", "first");
      return;
    }
    if (replace && stack().depth()) {
      setDrawerStack((s) => (s.length ? [...s.slice(0, -1), { ...s[s.length - 1], id: nextDrawerId(), content }] : s));
      return;
    }
    const id = nextDrawerId();
    // Closed (by Back, or by its own controls): it and every drawer above it go.
    stack().open(() => setDrawerStack((s) => {
      const at = s.findIndex((e) => e.first === id);
      return at < 0 ? s : s.slice(0, at);
    }), "drawer");
    setDrawerStack((s) => [...s, { id, first: id, content }].slice(-20));
  }, []);
  const drawerBack = useCallback(() => stack().closeKind("drawer", "last"), []);
  // Phones: the sidebar is a drawer, open only while choosing a screen; Back closes it too.
  const [navOpen, setNavOpen] = useState(false);
  useLayer(navOpen, () => setNavOpen(false), "menu");
  // Another business: a drawer open on the last one's records goes with it, as the screen
  // does (LegacyView is keyed by the business, below).
  const changeScope = useCallback((s) => {
    setScope(s);
    stack().closeKind("drawer", "first");
  }, []);

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
      // Back to the first screen, whose address may have had no #key.
      setView(k || "command");
    };
    apply();
    window.addEventListener("hashchange", apply);
    return () => window.removeEventListener("hashchange", apply);
  }, []);

  // A screen is its own history entry, so the browser's Back returns to the screen before
  // (it replaced the one entry there was, and Back left the platform). Open drawers and the
  // menu close first and take their entries with them (backstack.js).
  const go = (key) => {
    setView(key);
    stack().screen(key);
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
      <Sidebar nav={nav} current={view} onGo={go} scope={scope} onScope={changeScope} />
      {navOpen ? <div className="scrim-nav" onClick={() => setNavOpen(false)} /> : null}
      <div className="col">
        <Topbar scope={scope} openDrawer={setDrawer} onGo={go} onMenu={() => setNavOpen((o) => !o)} />
        <main className="main" id="cc-main">
          {!settings && !plan ? <ViewTools caption={captionOf(view)} scope={scope} /> : null}
          <LicenceBanner />
          {showBanner ? <IllustrativeNotice /> : null}
          {/* A screen that fails to draw says so; the shell stays (ErrorBoundary). */}
          <ErrorBoundary resetKey={`${view}|${scope}`} where={`the ${captionOf(view)} screen`}>
            {settings ? (
              isAdministrator(boot) ? <Settings /> : <LegacyView viewKey="denied" {...ctx} />
            ) : plan ? (
              boot.plan?.can_view ? <PlanUsage /> : <LegacyView viewKey="denied" {...ctx} />
            ) : Ported ? (
              <Ported {...ctx} />
            ) : (
              // Keyed by the business: switching business draws the screen afresh from its
              // design -- every card, tile, list, panel, report row and Home list back to
              // loading -- so nothing the last business filled in stays on screen, or can be
              // acted on, while the new one's answers are read (and if one of those fails,
              // its place says so rather than showing the old business's figure).
              <LegacyView key={scope} viewKey={view} {...ctx} />
            )}
          </ErrorBoundary>
        </main>
      </div>
      <Drawer content={drawer} entry={top?.id} onClose={() => setDrawer(null)}
              onBack={drawerStack.length > 1 ? drawerBack : null}
              trail={[captionOf(view), ...drawerStack.slice(0, -1).map((e) => drawerTitle(e.content))].filter(Boolean)} />
      <ActionDialog scope={scope} />
      <ScheduleDialog scope={scope} />
    </div>
  );
}

let drawerSeq = 0;
function nextDrawerId() {
  drawerSeq += 1;
  return drawerSeq;
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
