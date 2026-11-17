import React, { useEffect, useRef } from "react";
import { useLayer } from "../backstack.js";

/**
 * Small pieces the Settings screen's sections share: the dialog frame (the same
 * .dlg-scrim / .dlg as the schedule and action dialogs), a result message, and the
 * date-and-time format for "last sign-in" and "last load".
 */

export function Dialog({ title, sub, onClose, children, wide = false }) {
  const box = useRef(null);
  // Back closes the dialog, not the screen under it (backstack.js).
  useLayer(true, onClose, "dialog");
  useEffect(() => {
    const esc = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", esc);
    setTimeout(() => box.current?.querySelector("input,select,button")?.focus(), 30);
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);
  return (
    <div className="dlg-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        className="dlg"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={box}
        style={wide ? { width: "min(560px,100%)" } : undefined}
      >
        <h3>{title}</h3>
        {sub ? <p className="dlg-sub">{sub}</p> : null}
        {children}
      </div>
    </div>
  );
}

/** A result in words: ok (green), bad (red) or note (amber). */
export function Msg({ tone = "ok", children }) {
  if (!children) return null;
  return (
    <div className={`st-msg ${tone}`} role={tone === "bad" ? "alert" : "status"}>
      {children}
    </div>
  );
}

/** "15 Nov 2026, 10:20", or the fallback when there is no date. */
export function when(v, none = "Never") {
  if (!v) return none;
  const d = new Date(String(v).replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString("en-GB", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

/** The message of a failed call, in the server's own words. */
export function why(err, fallback = "That did not work.") {
  return err?.message || fallback;
}

/**
 * Run one call from a button: busy while it runs, then its result or its refusal.
 * `set` receives {busy, ok, bad}.
 */
export async function act(set, fn, okText) {
  set({ busy: true });
  try {
    const out = await fn();
    set({ ok: typeof okText === "function" ? okText(out) : okText });
    return out;
  } catch (e) {
    set({ bad: why(e) });
    return undefined;
  }
}
