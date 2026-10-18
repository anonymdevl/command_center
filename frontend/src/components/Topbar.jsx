import React, { useState } from "react";
import { boot } from "../api/boot.js";
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
  // The role keeps its ERPNext name ("Command Center Manager"); people see what it means.
  const SHOWN = { "Command Center Manager": "Management" };
  const roles = [...new Set((u.roles || []).map((r) => SHOWN[r] || r))].join(" · ") || "Management";
  return (
    // The person is read from the ERPNext session, never chosen: with a real session
    // the only person it can be is the one signed in.
    <div className="who" title={`${u.name} · ${roles}`}>
      <div className="av">{u.initials}</div>
      <div className="whotxt">
        <b>{u.name}</b>
        <span>{roles}</span>
      </div>
    </div>
  );
}
