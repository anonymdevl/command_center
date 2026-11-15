import React, { useEffect, useRef, useState } from "react";
import { api, plansApi } from "../api/client.js";
import Icon from "./Icon.jsx";

/**
 * The bell: how many alerts are open, and a short list of them.
 *
 * Absent until the alert engine existed, deliberately -- a bell with nothing behind it
 * is a promise the product does not keep. It reads the same list as Home's "Needs your
 * attention" (api/alerts.open_alerts), so the count and the cards cannot disagree, and
 * reads it again when an alert is acted on and every five minutes.
 *
 * Critical recommendations (api/recommend.critical) are listed under the alerts, except
 * one about the same issue as an open alert -- the server leaves those out, so nothing
 * is shown twice. One opens the Executive Summary, where every recommendation is.
 */
const WORDS = { crit: "Critical", high: "High", med: "Medium", info: "For information" };

export default function Bell({ scope, onGo }) {
  const [data, setData] = useState(null);
  const [recs, setRecs] = useState([]);
  // Plan and licence notices (insights/core/plans.py): an allowance at 80% or used, a
  // renewal coming, the month's statements ready; and, for administrators, security
  // alerts (insights/core/security.py). One person's own, until dismissed.
  const [notes, setNotes] = useState([]);
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      api.alerts(scope).then((d) => alive && setData(d)).catch(() => {});
      api.recCritical(scope).then((d) => alive && setRecs(d?.recommendations || [])).catch(() => {});
      plansApi.notices().then((d) => alive && setNotes(Array.isArray(d) ? d : [])).catch(() => {});
    };
    load();
    const t = setInterval(load, 60000);
    window.addEventListener("cc-alerts-changed", load);
    window.addEventListener("cc-recs-changed", load);
    return () => {
      alive = false;
      clearInterval(t);
      window.removeEventListener("cc-alerts-changed", load);
      window.removeEventListener("cc-recs-changed", load);
    };
  }, [scope]);

  useEffect(() => {
    if (!open) return;
    const away = (e) => wrap.current && !wrap.current.contains(e.target) && setOpen(false);
    const esc = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const alerts = data?.alerts || [];
  const fresh = data?.new || 0;
  const total = alerts.length + recs.length + notes.length;
  const label = total
    ? `${alerts.length} open alert${alerts.length === 1 ? "" : "s"}`
      + (recs.length ? `, ${recs.length} critical recommendation${recs.length === 1 ? "" : "s"}` : "")
    : "No open alerts";

  const show = (a) => {
    setOpen(false);
    onGo?.("command");
    // Home renders its alerts after its figures; give it a moment, then bring this one up.
    setTimeout(() => {
      const card = document.getElementById(`alert-${a.name}`);
      if (!card) return;
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.classList.add("alert-flash");
      setTimeout(() => card.classList.remove("alert-flash"), 1600);
    }, 450);
  };

  const showRec = (r) => {
    setOpen(false);
    onGo?.("brief");
    setTimeout(() => {
      const card = document.getElementById(`rec-${r.name}`);
      if (!card) return;
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.classList.add("alert-flash");
      setTimeout(() => card.classList.remove("alert-flash"), 1600);
    }, 650);
  };

  return (
    <div className="bellw" ref={wrap}>
      <button className={`ib bell${open ? " on" : ""}`} title={label} aria-label={label}
        aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Icon name="bell" />
        {total ? <span className={`bell-n${fresh || recs.length || notes.length ? " fresh" : ""}`}>{total > 99 ? "99+" : total}</span> : null}
      </button>
      {open ? (
        <div className="bellpop" role="dialog" aria-label="Alerts">
          <div className="bellpop-h">
            <b>Alerts</b>
            <span>{alerts.length ? `${alerts.length} open${fresh ? ` · ${fresh} new` : ""}` : "nothing open"}</span>
          </div>
          {alerts.length ? (
            <ul className="bellpop-l">
              {alerts.slice(0, 8).map((a) => (
                <li key={a.name}>
                  <button type="button" onClick={() => show(a)}>
                    <span className={`bell-dot ${a.severity}`} aria-hidden="true" />
                    <span className="bell-t">
                      <b>{a.title}</b>
                      <span>{WORDS[a.severity] || a.severity} · {a.owner_label} · {a.elapsed}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="bellpop-e">The alert rules found nothing material in the latest data.</p>
          )}
          {recs.length ? (
            <>
              <div className="bellpop-h">
                <b>Critical recommendations</b>
                <span>{recs.length}</span>
              </div>
              <ul className="bellpop-l">
                {recs.slice(0, 5).map((r) => (
                  <li key={r.name}>
                    <button type="button" onClick={() => showRec(r)}>
                      <span className="bell-dot crit" aria-hidden="true" />
                      <span className="bell-t">
                        <b>{r.title}</b>
                        <span>{r.area_label} · {r.owner_role}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {[["Security", notes.filter((x) => x.kind === "security")],
            ["Plan and licence", notes.filter((x) => x.kind !== "security")]].map(([head, list]) => (list.length ? (
            <React.Fragment key={head}>
              <div className="bellpop-h">
                <b>{head}</b>
                <span>{list.length}</span>
              </div>
              <ul className="bellpop-l">
                {list.slice(0, 6).map((x) => (
                  <li key={x.id}>
                    <button type="button" title={x.body} onClick={() => {
                      setOpen(false);
                      if (x.link === "security") {
                        // Settings opens on its Security section (Settings.jsx reads this once).
                        try { sessionStorage.setItem("cc-settings-tab", "security"); } catch { /* private mode */ }
                      }
                      onGo?.(x.link === "settings" || x.link === "security" ? "settings" : "plan");
                    }}>
                      <span className={`bell-dot ${x.kind === "allowance_full" || x.kind === "lapsed" || x.kind === "security" ? "crit" : "high"}`} aria-hidden="true" />
                      <span className="bell-t">
                        <b>{x.title}</b>
                        <span>{x.body}</span>
                      </span>
                    </button>
                    <button type="button" className="lnk" onClick={() => {
                      plansApi.dismiss(x.id).then(() => setNotes((n) => n.filter((y) => y.id !== x.id))).catch(() => {});
                    }}>Dismiss</button>
                  </li>
                ))}
              </ul>
            </React.Fragment>
          ) : null))}
          <div className="bellpop-f">
            <button type="button" className="lnk" onClick={() => { setOpen(false); onGo?.("command"); }}>
              See them on Home
            </button>
            {data?.can_tune ? (
              <a className="lnk" href="/app/command-center-alert-rule" target="_blank" rel="noreferrer">
                Adjust the rules ↗
              </a>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
