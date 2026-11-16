/**
 * A calm line above the screen when the selected business's ERPNext has not answered
 * (api/reach.py): what is shown is from the last read, and when that was; the newest
 * figures follow as soon as it answers. Never "can't reach": the business is marked so
 * only when a read went unanswered after its retries and a quick check straight after
 * failed too (connectors/remote.py), and most often it is only slow (16 Nov 2026).
 *
 * The status recovers by itself -- the connector marks the business Active on the next
 * call that succeeds, and api/reach.status asks the site again (at most once a minute)
 * while it is marked down -- so this checks every minute while down, every two minutes
 * otherwise, and whenever a screen's answer comes back with parts not answered
 * ("cc-reach-check", LegacyView). Retry asks now; while it does, the line says the
 * figures are being updated. Says nothing at all while the business answers.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { call } from "../api/client.js";
import { UPDATING, readAt, slowWords } from "../legacy/reach.js";

export default function ReachBanner({ scope, onBack }) {
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState(false);

  // The screen hands a new onBack at every render (each figure or panel that arrives);
  // read through a ref, so the check depends on the business alone and is asked once
  // per screen, not once per render.
  const back = useRef(onBack);
  back.current = onBack;
  const check = useCallback((method = "status") => {
    return call(`command_center.api.reach.${method}`, { business_code: scope })
      .then((s) => {
        setSt((was) => {
          if (was && !was.reachable && s?.reachable) back.current?.();
          return s;
        });
        window.dispatchEvent(new CustomEvent("cc-reach", { detail: s }));
        return s;
      })
      .catch(() => null);
  }, [scope]);

  const down = !!(st && !st.reachable);
  useEffect(() => {
    let alive = true;
    check();
    const t = setInterval(() => alive && check(), (down ? 1 : 2) * 60000);
    const again = () => check();
    window.addEventListener("cc-reach-check", again);
    return () => {
      alive = false;
      clearInterval(t);
      window.removeEventListener("cc-reach-check", again);
    };
  }, [check, down]);

  if (!down) return null;
  const last = readAt(st.last_load);
  return (
    <div className="banner reach-banner" role="status" style={{ display: "flex", gap: 12, alignItems: "center", margin: "0 0 14px" }}>
      {busy ? (
        <span style={{ flex: 1 }}><b>{UPDATING}</b></span>
      ) : (
        <span style={{ flex: 1 }}>
          <b>{last ? `Showing figures from the last read at ${last}.` : "Showing the figures already read."}</b>{" "}
          {slowWords(st.name)}; the newest figures will appear as soon as it does.
        </span>
      )}
      <button type="button" className="btn" disabled={busy}
        onClick={() => {
          setBusy(true);
          check("retry").finally(() => setBusy(false));
        }}>
        {busy ? "Updating…" : "Retry"}
      </button>
    </div>
  );
}
