import React, { useState } from "react";
import { boot as bootPayload } from "../api/boot.js";
import SettingsPeople from "./SettingsPeople.jsx";
import SettingsBusinesses from "./SettingsBusinesses.jsx";
import SettingsEmail from "./SettingsEmail.jsx";
import SettingsRecommend from "./SettingsRecommend.jsx";
import SettingsBranding from "./SettingsBranding.jsx";
import SettingsCustomers from "./SettingsCustomers.jsx";
import SettingsSecurity from "./SettingsSecurity.jsx";
import { SettingsChanges, SettingsClaude, SettingsCredentials } from "./SettingsKeys.jsx";
import "../styles/settings.css";

/**
 * Settings: people, connected businesses, the Claude key, email, branding, personal
 * ERPNext keys and the recommendation rules.
 *
 * Not a designed screen, so not in views.json: the platform administrator's own page,
 * replacing the Django administration for everyday work (/admin keeps working). The
 * administrator sees every section; a manager they have given sections to (People →
 * Manage → Settings Access) sees only those. Which ones comes from the boot payload's
 * settings_sections; the server refuses everything else on every call
 * (insights/core/platform_settings.py), whatever this screen does. Built from the
 * screens' own panels, tables, tabs, tags, buttons and dialogs.
 */
const TABS = [
  ["people", "User Management", SettingsPeople],
  ["businesses", "Businesses", SettingsBusinesses],
  ["customers", "Customers", SettingsCustomers],
  ["claude", "Claude", SettingsClaude],
  ["email", "Email", SettingsEmail],
  ["branding", "Branding", SettingsBranding],
  ["keys", "ERPNext API Keys", SettingsCredentials],
  ["recommend", "Recommendations", SettingsRecommend],
  ["changes", "Changes", SettingsChanges],
  // The administrator's alone: never given to anyone (insights/core/security.py).
  ["security", "Security", SettingsSecurity],
];

/** The Settings sections this person may open (empty: no Settings for them). */
export function settingsSections(boot) {
  if (Array.isArray(boot?.settings_sections)) return boot.settings_sections;
  // A server from before delegation: administrators only, every section.
  return (boot?.user?.roles || []).includes("System Manager") ? TABS.map((t) => t[0]) : [];
}

export function canOpenSettings(boot) {
  return settingsSections(boot).length > 0;
}

/** Whether this person may open Settings at all (administrator or delegate); App.jsx
 *  gates the screen on it. */
export function isAdministrator(boot) {
  return canOpenSettings(boot);
}

export default function Settings() {
  const mine = settingsSections(bootPayload);
  const tabs = TABS.filter((t) => mine.includes(t[0]));
  const [tab, setTab] = useState(() => {
    // The bell's security alerts open Settings on Security (Bell.jsx), once.
    let want = null;
    try {
      want = sessionStorage.getItem("cc-settings-tab");
      sessionStorage.removeItem("cc-settings-tab");
    } catch { /* private mode */ }
    return tabs.some((t) => t[0] === want) ? want : tabs[0]?.[0];
  });
  const Section = (tabs.find((t) => t[0] === tab) || tabs[0])?.[2];
  // The heading alone: no sentence about who sees this screen or what is recorded
  // (17 Nov 2026, "too chatty"), least of all to a manager given a section of it.
  return (
    <div className="settings">
      <div className="topbar">
        <div>
          <h3>Settings</h3>
        </div>
      </div>
      {tabs.length > 1 ? (
        <div className="tabbar st-tabs" role="tablist">
          {tabs.map(([key, label]) => (
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
      ) : null}
      {Section ? <Section /> : null}
    </div>
  );
}
