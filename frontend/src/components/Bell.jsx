import React, { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import Icon from "./Icon.jsx";

/**
 * The bell: how many alerts are open, and a short list of them.
 *
 * Absent until the alert engine existed, deliberately -- a bell with nothing behind it
 * is a promise the product does not keep. It reads the same list as Home's "Needs your
 * attention" (api/alerts.open_alerts), so the count and the cards cannot disagree, and
 * reads it again when an alert is acted on and every five minutes.
 */
const WORDS = { crit: "Critical", high: "High", med: "Medium", info: "For information" };

export default function Bell({ scope, onGo }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);

  useEffect(() => {
    let alive = true;
    const load = () => api.alerts(scope).then((d) => alive && setData(d)).catch(() => {});
    load();
    const t = setInterval(load, 5 * 60000);
    window.addEventListener("cc-alerts-changed", load);
    return () => {
      alive = false;
      clearInterval(t);
      window.removeEventListener("cc-alerts-changed", load);
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
  const label = alerts.length ? `${alerts.length} open alert${alerts.length === 1 ? "" : "s"}` : "No open alerts";

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

  return (
    <div className="bellw" ref={wrap}>
      <button className={`ib bell${open ? " on" : ""}`} title={label} aria-label={label}
        aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Icon name="bell" />
        {alerts.length ? <span className={`bell-n${fresh ? " fresh" : ""}`}>{alerts.length > 99 ? "99+" : alerts.length}</span> : null}
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
