import React, { useCallback, useEffect, useState } from "react";
import { call } from "../api/client.js";

/**
 * A calm line above the screen when the selected business's ERPNext is not answering
 * (api/reach.py): since when, how old the loaded figures are, and a Retry that asks the
 * site again. The status recovers by itself -- the connector marks the business Active
 * on the next call that succeeds -- and this checks again every two minutes while down.
 * Says nothing at all while the business answers.
 */
export default function ReachBanner({ scope, onBack }) {
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState(false);

  const check = useCallback((method = "status") => {
    return call(`command_center.api.reach.${method}`, { business_code: scope })
      .then((s) => {
        setSt((was) => {
          if (was && !was.reachable && s?.reachable) onBack?.();
          return s;
        });
        window.dispatchEvent(new CustomEvent("cc-reach", { detail: s }));
        return s;
      })
      .catch(() => null);
  }, [scope, onBack]);

  useEffect(() => {
    let alive = true;
    check();
    const t = setInterval(() => alive && check(), 2 * 60000);
    const again = () => check();
    window.addEventListener("cc-reach-check", again);
    return () => {
      alive = false;
      clearInterval(t);
      window.removeEventListener("cc-reach-check", again);
    };
  }, [check]);

  if (!st || st.reachable) return null;
  const at = (v) => {
    if (!v) return null;
    const d = new Date(String(v).replace(" ", "T"));
    if (Number.isNaN(d.getTime())) return null;
    const today = new Date().toDateString() === d.toDateString();
    return today ? d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
      : d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  };
  const since = at(st.since);
  const last = at(st.last_load);
  return (
    <div className="banner reach-banner" role="status" style={{ display: "flex", gap: 12, alignItems: "center", margin: "0 0 14px" }}>
      <span style={{ flex: 1 }}>
        <b>Can&apos;t reach {st.name || "the business"}&apos;s ERPNext{since ? ` since ${since}` : ""}.</b>{" "}
        {last ? `Figures are from the last load at ${last}; ` : "Figures are from the last load; "}
        live parts will refresh when it&apos;s back.
      </span>
      <button type="button" className="btn" disabled={busy}
        onClick={() => {
          setBusy(true);
          check("retry").finally(() => setBusy(false));
        }}>
        {busy ? "Checking…" : "Retry"}
      </button>
    </div>
  );
}
