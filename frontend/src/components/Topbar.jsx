import React, { useEffect, useRef, useState } from "react";
import { boot } from "../api/boot.js";
import { getAppearance, setAppearance } from "../appearance.js";
import Appearance from "./Appearance.jsx";
import Icon from "./Icon.jsx";

/**
 * The question box, the theme, and who is signed in.
 *
 * The question box is the widest thing on the bar on purpose: asking the business a
 * question is the platform's main idea, so it is not tucked behind a menu item. A
 * question typed here is answered on the Ask AI screen by the same engine, so there
 * is one way questions get answered, not two that could disagree.
 *
 * No alerts bell. The alert engine (AL-01..AL-07) is not built, and a bell that can
 * never ring is a control that lies about what the platform does. It arrives with the
 * engine.
 */
export default function Topbar({ onAsk, onMenu }) {
  return (
    <header className="topnav">
      {/* Phones only: the sidebar is a drawer there. */}
      <button className="ib menu-b" title="Screens" aria-label="Open the list of screens" onClick={onMenu}>
        <Icon name="menu" />
      </button>
      <AskBox onAsk={onAsk} />
      <ThemeToggle />
      <div className="pill">
        <Appearance />
        <Who />
      </div>
    </header>
  );
}

function AskBox({ onAsk }) {
  const [q, setQ] = useState("");
  const input = useRef(null);

  // Cmd/Ctrl-K from anywhere: the shortcut every serious tool has taught people.
  useEffect(() => {
    const key = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        input.current?.focus();
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);

  const submit = (e) => {
    e.preventDefault();
    const question = q.trim();
    if (!question) {
      input.current?.focus();
      return;
    }
    onAsk(question);
  };

  return (
    <form className="ask" role="search" onSubmit={submit}>
      <Icon name="spark" className="ask-i" />
      <input
        ref={input}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Ask anything about the business — who owes us the most?"
        aria-label="Ask a question about the business"
        autoComplete="off"
      />
      <kbd className="ask-k" aria-hidden="true">
        ⌘K
      </kbd>
      <button className="ask-go" type="submit">
        <Icon name="search" size={16} />
        <span>Ask</span>
      </button>
    </form>
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
  const roles = (u.roles || []).join(" · ") || "Management";
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
