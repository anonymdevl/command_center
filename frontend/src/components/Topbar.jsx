import React, { useEffect, useRef, useState } from "react";
import { boot } from "../api/boot.js";
import { call } from "../api/client.js";
import { getAppearance, setAppearance } from "../appearance.js";
import Appearance from "./Appearance.jsx";
import AskBar from "./AskBar.jsx";
import Bell from "./Bell.jsx";
import Icon from "./Icon.jsx";

/**
 * The question box, the theme, and who is signed in.
 *
 * The question box is the widest thing on the bar on purpose: asking the business a
 * question is the platform's main idea, so it is not tucked behind a menu item. It
 * answers in place (AskBar.jsx), through the same endpoint and conversation as the
 * Ask AI screen.
 *
 * No alerts bell. The alert engine (AL-01..AL-07) is not built, and a bell that can
 * never ring is a control that lies about what the platform does. It arrives with the
 * engine.
 */
export default function Topbar({ scope, openDrawer, onMenu, onGo }) {
  return (
    <header className="topnav">
      {/* Phones only: the sidebar is a drawer there. */}
      <button className="ib menu-b" title="Screens" aria-label="Open the list of screens" onClick={onMenu}>
        <Icon name="menu" />
      </button>
      <AskBar scope={scope} openDrawer={openDrawer} />
      <ThemeToggle />
      <div className="pill">
        <Bell scope={scope} onGo={onGo} />
        <Appearance />
        <Who />
      </div>
    </header>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState(() => getAppearance().theme);
  const set = (t) => {
    setAppearance("theme", t);
    setTheme(t);
  };
  return (
    <div className="pill seg2" role="group" aria-label="Theme">
      {[
        ["dark", "moon", "Dark"],
        ["light", "sun", "Light"],
      ].map(([t, icon, label]) => (
        <button
          key={t}
          className={`ib${theme === t ? " on" : ""}`}
          title={label}
          aria-label={label}
          aria-pressed={theme === t}
          onClick={() => set(t)}
        >
          <Icon name={icon} />
        </button>
      ))}
    </div>
  );
}

function Who() {
  const u = boot.user || {};
  // The role keeps its ERPNext name ("Insights Dashboard Manager"); people see what it means.
  const SHOWN = { "Insights Dashboard Manager": "Management" };
  const roles = [...new Set((u.roles || []).map((r) => SHOWN[r] || r))].join(" · ") || "Management";
  const [open, setOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const wrap = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => wrap.current && !wrap.current.contains(e.target) && setOpen(false);
    const esc = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  // Signing out ends the session on the server, then leaves for the sign-in page. If the
  // server cannot be reached the page still goes to sign-in: a session it cannot end is
  // one the next sign-in replaces.
  const signOut = async () => {
    setLeaving(true);
    try {
      await call("logout");
    } catch (e) {
      /* the sign-in page follows either way */
    }
    try {
      sessionStorage.clear();
    } catch (e) {
      /* private windows may refuse storage */
    }
    window.location.replace("/command-center-login");
  };

  return (
    // The person is read from the session, never chosen: with a real session the only
    // person it can be is the one signed in.
    <div className="whow" ref={wrap}>
      <button className={`who${open ? " on" : ""}`} title={`${u.name} · ${roles}`}
        aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <div className="av">{u.initials}</div>
        <div className="whotxt">
          <b>{u.name}</b>
          <span>{roles}</span>
        </div>
      </button>
      {open ? (
        <div className="whomenu" role="menu" aria-label="Your account">
          <div className="whomenu-h">
            <b>{u.name}</b>
            <span>{u.id}</span>
            <span>{roles}</span>
          </div>
          <button className="whomenu-out" role="menuitem" onClick={signOut} disabled={leaving}>
            <Icon name="logout" />
            {leaving ? "Signing Out…" : "Sign Out"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
