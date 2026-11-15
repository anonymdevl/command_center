import React, { useState } from "react";
import SettingsPeople from "./SettingsPeople.jsx";
import SettingsBusinesses from "./SettingsBusinesses.jsx";
import { SettingsChanges, SettingsClaude, SettingsCredentials } from "./SettingsKeys.jsx";
import "../styles/settings.css";

/**
 * Settings: people, connected businesses, the Claude key and personal ERPNext keys.
 *
 * Not a designed screen, so not in views.json: the platform administrator's own page,
 * replacing the Django administration for everyday work (/admin keeps working). Shown
 * only to administrators (App.jsx, Sidebar.jsx); the server refuses everyone else on
 * every call (insights/core/platform_settings.py), whatever this screen does. Built
 * from the screens' own panels, tables, tabs, tags, buttons and dialogs.
 */
const TABS = [
  ["people", "People", SettingsPeople],
  ["businesses", "Businesses", SettingsBusinesses],
  ["claude", "Claude", SettingsClaude],
  ["keys", "Personal ERPNext Keys", SettingsCredentials],
  ["changes", "Changes", SettingsChanges],
];

export function isAdministrator(boot) {
  return (boot?.user?.roles || []).includes("System Manager");
}

export default function Settings() {
  const [tab, setTab] = useState("people");
  const Section = (TABS.find((t) => t[0] === tab) || TABS[0])[2];
  return (
    <div className="settings">
      <div className="topbar">
        <div>
          <h3>Settings</h3>
          <div className="when">
            Who can sign in, the businesses the platform reads, and the keys it uses. Only platform
            administrators see this screen; every change is recorded under Changes.
          </div>
        </div>
      </div>
      <div className="tabbar st-tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            className={`tab${tab === key ? " on" : ""}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <Section />
    </div>
  );
}
