import React, { useEffect, useRef, useState } from "react";
import views from "../legacy/views.json";
import extras from "../legacy/extras.json";
import { boot } from "../api/boot.js";
import { renderGreeting } from "../greeting.js";
import { api } from "../api/client.js";
import { useApi } from "../useApi.js";
import Records from "./Records.jsx";
import { hydrateCards, hydrateTiles, keysFor, markLoading } from "../legacy/hydrate.js";
import { renderAnswer, renderThinking, renderFailure } from "../legacy/answer.js";
import { clearTurns, historyFor, remember, replaceAnswer, restore, turnsFor } from "../askHistory.js";
import { renderConversations } from "../legacy/conversations.js";
import { fetchStarters, followDeep, runAsk, runningFor, stopDeepLook, stopRunning } from "../askFlow.js";
import { renderSteps } from "../legacy/steps.js";
import { runReport } from "../legacy/reports.js";
import { wireActions } from "../legacy/actions.js";
import { WORK_VIEWS, renderWork } from "../legacy/work.js";
import { ALERT_VIEWS, alertsFailed, renderAlerts } from "../legacy/alerts.js";
import { CORE_PANEL_VIEWS, renderCore } from "../legacy/core.js";
import ReachBanner from "./ReachBanner.jsx";
import { renderHealthTiles, renderHome } from "../legacy/home.js";
import { renderSchedules } from "../legacy/schedules.js";
import { PANEL_VIEWS, renderPanels } from "../legacy/panels.js";
import { disposeWithin } from "../legacy/viz.js";
import { renderLoads } from "../legacy/loads.js";
import { PEOPLE_VIEWS, renderPeople } from "../legacy/people.js";

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
export default function LegacyView({ viewKey, scope, go, openDrawer }) {
  const ref = useRef(null);
  const html = views[viewKey];
  const [liveCount, setLiveCount] = useState(null);

  // The runSearch handler is installed once, but the business can change under it. A
  // ref keeps it reading the current scope rather than the one captured at install.
  const scopeRef = useRef(scope);
  scopeRef.current = scope;
  // App's go() is a new function each render; the inline handlers read the latest.
  const goRef = useRef(go);
  goRef.current = go;

  const keys = keysFor(viewKey);
  const figures = useApi(
    () => (keys.length ? api.kpis({ keys, business_code: scope }) : Promise.resolve(null)),
    [viewKey, scope, keys.join(",")],
    { skip: keys.length === 0 }
  );

  // Today, Approvals and Outstanding Tasks read the real queue (api/work.py), again
  // after any decision made on them.
  // The department screens' charts and tables (api/panels.py, legacy/panels.js).
  // Business Overview's finding comes the same way (api/panels_core.py).
  const hasPanels = PANEL_VIEWS.has(viewKey) || CORE_PANEL_VIEWS.has(viewKey);
  const panels = useApi(() => api.panels(viewKey, scope), [viewKey, scope], { skip: !hasPanels });
  const isWork = WORK_VIEWS.has(viewKey);
  const work = useApi(() => api.work(scope), [viewKey, scope], { skip: !isWork });
  useEffect(() => {
    if (!isWork) return;
    const again = () => work.reload();
    window.addEventListener("cc-work-changed", again);
    return () => window.removeEventListener("cc-work-changed", again);
  }, [isWork, work.reload]);

  // Home and the Executive Summary show the alert engine's alerts (api/alerts.py).
  const hasAlerts = ALERT_VIEWS.has(viewKey);
  const alerts = useApi(() => api.alerts(scope), [viewKey, scope], { skip: !hasAlerts });
  useEffect(() => {
    if (!hasAlerts) return;
    const again = () => alerts.reload();
    window.addEventListener("cc-alerts-changed", again);
    return () => window.removeEventListener("cc-alerts-changed", again);
  }, [hasAlerts, alerts.reload]);

  // Live: while the screen is being looked at, its figures, panels, work and alerts are
  // read again every minute (the platform refreshes each business's data every two
  // minutes), and at once when the tab comes back into view. The figures on screen stay
  // in place while the new ones load, so nothing flickers.
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState !== "visible") return;
      if (keys.length) figures.reload();
      if (hasPanels) panels.reload();
      if (isWork) work.reload();
      if (hasAlerts) alerts.reload();
    };
    const t = setInterval(tick, 60000);
    const onShow = () => {
      if (document.visibilityState === "visible") tick();
    };
    document.addEventListener("visibilitychange", onShow);
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", onShow);
    };
  }, [viewKey, scope, keys.length, hasPanels, isWork, hasAlerts,
      figures.reload, panels.reload, work.reload, alerts.reload]);

  // Whether the selected business's ERPNext answers (components/ReachBanner.jsx).
  const [reachDown, setReachDown] = useState(false);
  useEffect(() => {
    const on = (e) => setReachDown(e?.detail ? !e.detail.reachable : false);
    window.addEventListener("cc-reach", on);
    return () => window.removeEventListener("cc-reach", on);
  }, []);

  // Business Health says how fresh the data is, and can refresh it.
  const isHealth = viewKey === "health";
  const loads = useApi(() => api.ingestHistory(scope), [viewKey, scope], { skip: !isHealth });
  useEffect(() => {
    if (!isHealth) return;
    renderLoads(ref.current, loads.data, {
      scope,
      onRefreshed: () => {
        loads.reload();
        figures.reload();
        window.dispatchEvent(new CustomEvent("cc-alerts-changed"));
      },
    });
  }, [isHealth, loads.data, html, scope]);

  // The Reports screen says the schedule actually set for each report.
  const isReports = viewKey === "reports";
  const sched = useApi(() => api.schedules(scope), [viewKey, scope], { skip: !isReports });
  useEffect(() => {
    if (!isReports) return;
    const again = () => sched.reload();
    window.addEventListener("cc-schedules-changed", again);
    return () => window.removeEventListener("cc-schedules-changed", again);
  }, [isReports, sched.reload]);
  useEffect(() => {
    if (isReports) renderSchedules(ref.current, sched.data);
  }, [isReports, sched.data, html]);

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
    // Navigation from the designed tiles and links ("open any one of them"). Missing until
    // the click-through of 18 Oct 2026: 25 tiles and links called a go() nobody defined.
    window.go = (key) => goRef.current?.(key);
    // "Ask why" buttons beside a row ask the question in the bar, where every answer goes.
    window.ask2 = (question) =>
      window.dispatchEvent(new CustomEvent("cc-ask", { detail: { question } }));
    // Tabs are switched by the click handler below; the generated onclick has nothing to do.
    window.tab = () => {};
    // The prototype's "⋯" menus are replaced by working ones (legacy/actions.js).
    window.moreMenu = () => {};

    // The designed Ask screen calls runSearch(value) from its own input and its own
    // suggestion buttons, and expects the answer in its own #sout2. So it is wired
    // rather than replaced: same markup, same ids, real answers.
    // The Ask AI screen is a conversation: each question is a turn -- the person's
    // question, then the analyst's answer under it -- kept in order, newest last, and
    // redrawn from askHistory.js whenever the screen opens, so a conversation started
    // in the bar carries on here.
    const answerOpts = (q) => ({
      inThread: true,
      onFollowup: (next) => window.runSearch && window.runSearch(next),
      onPdf: (res) =>
        api.answerPdf({
          question: q,
          answer: res.answer,
          checked: res.checked,
          business_code: scopeRef.current,
          model: res.model,
        }),
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

    const newTurn = (thread, q) => {
      const turn = document.createElement("div");
      turn.className = "turn";
      const qb = document.createElement("div");
      qb.className = "turn-q";
      qb.textContent = q;
      const a = document.createElement("div");
      a.className = "turn-a";
      turn.append(qb, a);
      thread.append(turn);
      return a;
    };

    const threadTools = (thread) => {
      const has = !!thread.querySelector(".turn");
      let bar = thread.previousElementSibling?.classList?.contains("thread-tools")
        ? thread.previousElementSibling : null;
      if (!has) {
        bar?.remove();
        return;
      }
      if (bar) return;
      bar = document.createElement("div");
      bar.className = "thread-tools";
      const b = document.createElement("button");
      b.className = "btn";
      b.textContent = "New conversation";
      b.onclick = () => {
        clearTurns(scopeRef.current);
        thread.textContent = "";
        bar.remove();
        renderConversations(ref.current, scopeRef.current);
        document.getElementById("askin")?.focus();
      };
      bar.append(b);
      thread.before(bar);
    };

    // A big question's deeper look: a banner at the top of its turn while it works,
    // then the fuller answer in place of the first.
    const deepen = (out, q, askId, scope) => {
      const banner = document.createElement("div");
      banner.className = "ap-deep";
      const spin = document.createElement("span");
      spin.className = "ap-spin";
      const body = document.createElement("div");
      const b = document.createElement("b");
      b.textContent = "Taking a deeper look";
      const t = document.createElement("span");
      t.textContent = "This question needs more than a quick pass. A fuller answer will replace "
        + "this one in a few minutes; the first pass is below.";
      let ol = document.createElement("div");
      body.append(b, t, ol);
      // Stop the deeper look; the first answer below stays.
      const halt = document.createElement("button");
      halt.className = "ap-act";
      halt.type = "button";
      halt.textContent = "Stop";
      banner.append(spin, body, halt);
      out.prepend(banner);
      const note = (text, why) => {
        const n = document.createElement("div");
        n.className = "ap-note";
        n.textContent = text;
        if (why) {
          const r = document.createElement("span");
          r.textContent = `Reason: ${why}`;
          n.append(r);
        }
        banner.replaceWith(n);
      };
      const unfollow = followDeep(askId, {
        onSteps: (steps) => {
          const next = renderSteps(steps, banner);
          ol.replaceWith(next);
          ol = next;
        },
        onDone: (full) => {
          replaceAnswer(scope, q, full);
          if (document.body.contains(out)) renderAnswer(out, full, answerOpts(q));
        },
        onFailed: (why) => note("The deeper look stopped before it finished, so this is the "
          + "first-pass answer.", why),
        onStuck: () => note("The deeper look could not start: the server's background workers "
          + "are not running. This is the first-pass answer."),
        onStopped: () => note("You stopped the deeper look, so this is the first-pass answer."),
      });
      halt.onclick = () => {
        stopDeepLook(askId);
        unfollow();
        note("You stopped the deeper look, so this is the first-pass answer.");
      };
    };

    window.drawThread = () => {
      const thread = document.getElementById("sout2");
      if (!thread) return;
      thread.textContent = "";
      turnsFor(scopeRef.current).forEach((t) => {
        renderAnswer(newTurn(thread, t.q), t.payload, answerOpts(t.q));
      });
      threadTools(thread);
    };

    // One question at a time per conversation: asked while one is running (here or in
    // the bar), it is not started, and the note under the box says so, with a Stop.
    const busyNote = (thread) => {
      let n = thread.parentElement?.querySelector(".ap-busy");
      if (!n) {
        n = document.createElement("div");
        n.className = "ap-note ap-busy";
        thread.before(n);
      }
      n.textContent = "One question at a time: the one still being worked out must finish or be "
        + "stopped first. ";
      const b = document.createElement("button");
      b.className = "ap-act";
      b.type = "button";
      b.textContent = "Stop it";
      b.onclick = () => stopRunning(scopeRef.current);
      n.append(b);
      const gone = () => {
        if (runningFor(scopeRef.current)) return;
        n.remove();
        window.removeEventListener("cc-ask-running", gone);
      };
      window.addEventListener("cc-ask-running", gone);
    };

    window.runSearch = async (question) => {
      const thread = document.getElementById("sout2") || document.getElementById("sout");
      if (!thread) return;
      const q = (question || "").trim();
      if (!q) return;
      const scope = scopeRef.current;
      // The same flow as the bar: the question reports each lookup, shown live.
      let out = null;
      let handle = null;
      const think = (steps) => {
        renderThinking(out, q, steps);
        const box = out.querySelector(".ap-think");
        if (!box || !handle) return;
        const b = document.createElement("button");
        b.className = "ap-act";
        b.type = "button";
        b.textContent = handle.stopped ? "Stopping…" : "Stop";
        b.disabled = handle.stopped;
        b.title = "Stop working on this question and show what it has found so far";
        b.onclick = () => {
          handle.stop();
          think(steps);
        };
        box.append(b);
      };
      handle = runAsk(scope,
        { question: q, business_code: scope, history: historyFor(scope) },
        (steps) => out && think(steps));
      if (!handle) {
        busyNote(thread);
        return;
      }
      const box = document.getElementById("askin");
      if (box) box.value = "";
      out = newTurn(thread, q);
      out.parentElement.scrollIntoView({ behavior: "smooth", block: "start" });
      think([]);
      try {
        const payload = await handle.answer;
        remember(scope, q, payload);
        renderAnswer(out, payload, answerOpts(q));
        if (payload?.deep?.ask_id) deepen(out, q, payload.deep.ask_id, scope);
      } catch (e) {
        renderFailure(out, e?.message);
      }
      threadTools(thread);
    };

    // The designed Reports screen's Run buttons call runReport(code).
    window.runReport = (code) => runReport(code, scopeRef.current);

    return () => {
      delete window.runReport;
      delete window.drawThread;
      delete window.openDrawer;
      delete window.explain;
      delete window.drill;
      delete window.closeDrawer;
      delete window.runSearch;
    };
  }, [openDrawer]);

  // The saved conversation comes back from the server after the screen draws; redraw the
  // thread and the list when it arrives, or when another conversation is opened.
  useEffect(() => {
    if (viewKey !== "ask") return;
    const again = (e) => {
      if (e?.detail?.redraw !== false) window.drawThread?.();
      renderConversations(ref.current, scopeRef.current);
    };
    window.addEventListener("cc-history-changed", again);
    restore(scope);
    renderConversations(ref.current, scope);
    return () => window.removeEventListener("cc-history-changed", again);
  }, [viewKey, scope]);

  useEffect(() => {
    if (viewKey !== "ask") return;
    window.drawThread?.();
    // The Ask AI screen's suggestions are the starter questions the bar offers
    // (api/starters.py): chosen from the person's role and today's figures, each asked
    // on a click. No suggestion asks it to change anything: one that did ("Issue a
    // credit note", to show the refusal) read as if the assistant could (18 Oct 2026).
    const sugg = document.getElementById("asksugg");
    if (sugg) {
      fetchStarters(scopeRef.current).then((all) => {
        const list = all.slice(0, 6);
        if (!list.length || !document.body.contains(sugg)) return;
        sugg.textContent = "";
        list.forEach((e) => {
          const b = document.createElement("button");
          b.className = "btn";
          b.textContent = e.q;
          b.onclick = () => window.runSearch && window.runSearch(e.q);
          sugg.append(b);
        });
      }).catch(() => {});
    }

  }, [viewKey, scope]);

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

  // Placeholders on the cards that are about to receive a live figure.
  useEffect(() => {
    markLoading(ref.current, viewKey, figures.loading && !figures.data);
  }, [viewKey, html, figures.loading, figures.data]);

  // Live figures into the designed cards and tiles. Runs after the markup is in the DOM
  // and again whenever the figures or the business change.
  useEffect(() => {
    const root = ref.current;
    if (!root || !html) return;
    const opts = {
      onOpen: (figure) =>
        figure.drill?.href
          ? window.open(figure.drill.href, "_blank", "noopener")
          : figure.drill?.fact
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
    };
    opts.openDrawer = openDrawer;
    setLiveCount(
      hydrateCards(root, viewKey, figures.data, opts) +
      hydrateTiles(root, viewKey, figures.data, opts) +
      (isWork ? renderWork(root, viewKey, work.data, opts) : 0));
    if (hasAlerts) renderAlerts(root, viewKey, alerts.data, opts);
    if (viewKey === "command") {
      renderHome(root, { figures: figures.data, alerts: alerts.data, scope, onOpen: opts.onOpen });
    }
    if (viewKey === "health") renderHealthTiles(root, figures.data, { openDrawer });
    if (hasAlerts && alerts.error) alertsFailed(root, viewKey, alerts.error);
    if (hasPanels) {
      renderPanels(root, viewKey, panels.data, { onOpen: opts.onOpen, openDrawer,
                                                 failed: !!panels.error });
    }
    // The management screens: nothing left designed, a dash and a reason where a figure
    // could not be read (legacy/core.js).
    renderCore(root, viewKey, {
      figures: figures.data, figuresDone: keys.length === 0 || !!(figures.data || figures.error),
      panels: panels.data, alerts: alerts.data, work: work.data, isWork,
      workDone: !!(work.data || work.error), reachDown,
    });
    // An alert drawn by the generator is a designed sample until something live replaces
    // it, and the screen's "still illustrative" line must keep saying so.
    root.querySelectorAll(".alert:not([data-live])").forEach((a) => {
      a.dataset.illustrative = "1";
    });
  }, [viewKey, html, figures.data, figures.error, work.data, work.error, isWork, alerts.data,
      alerts.error, hasAlerts, scope, openDrawer, hasPanels, panels.data, panels.error, reachDown]);

  // The screen's charts (legacy/viz.js) are disposed with it, not left for the sweep.
  useEffect(() => {
    const root = ref.current;
    return () => disposeWithin(root);
  }, [viewKey]);

  // HR & Payroll's People Lookup and Leave (legacy/people.js, api/people.py): drawn once
  // the markup is in place, again when the business changes.
  useEffect(() => {
    if (!PEOPLE_VIEWS.has(viewKey)) return undefined;
    return renderPeople(ref.current, { scope, openDrawer });
  }, [viewKey, html, scope, openDrawer]);

  // The designed action buttons (Assign, the "⋯" menu, Raise it...) had no handlers.
  useEffect(() => {
    wireActions(ref.current);
  }, [viewKey, html]);

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
      <ReachBanner scope={scope} onBack={() => {
        figures.reload();
        if (hasPanels) panels.reload();
        if (isWork) work.reload();
        if (hasAlerts) alerts.reload();
      }} />
      {figures.error ? (
        <div className="warn" style={{ margin: "0 0 14px" }}>
          <b>The live figures could not be read.</b> {figures.error.message} The cards
          below show a dash until they can be.
        </div>
      ) : null}
      {work.error ? (
        <div className="warn" style={{ margin: "0 0 14px" }}>
          <b>Your approvals and tasks could not be read.</b> {work.error.message} Open the
          screen again to retry.
        </div>
      ) : null}
      <div key={viewKey} className="view on" ref={ref} dangerouslySetInnerHTML={{ __html: html }} />
    </>
  );
}
