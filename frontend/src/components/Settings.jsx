import React, { useState } from "react";
import { boot as bootPayload } from "../api/boot.js";
import SettingsPeople from "./SettingsPeople.jsx";
import SettingsBusinesses from "./SettingsBusinesses.jsx";
import SettingsEmail from "./SettingsEmail.jsx";
import SettingsRecommend from "./SettingsRecommend.jsx";
import { SettingsChanges, SettingsClaude, SettingsCredentials } from "./SettingsKeys.jsx";
import "../styles/settings.css";

/**
 * Settings: people, connected businesses, the Claude key, email, personal ERPNext keys and
 * the recommendation rules.
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
  ["people", "People", SettingsPeople],
  ["businesses", "Businesses", SettingsBusinesses],
  ["claude", "Claude", SettingsClaude],
  ["email", "Email", SettingsEmail],
  ["keys", "Personal ERPNext Keys", SettingsCredentials],
  ["recommend", "Recommendations", SettingsRecommend],
  ["changes", "Changes", SettingsChanges],
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
  const [tab, setTab] = useState(tabs[0]?.[0]);
  const Section = (tabs.find((t) => t[0] === tab) || tabs[0])?.[2];
  const everything = tabs.length === TABS.length;
  return (
    <div className="settings">
      <div className="topbar">
        <div>
          <h3>Settings</h3>
          <div className="when">
            {everything
              ? "Who can sign in, the businesses the platform reads, and the keys and email it uses. Only administrators, and managers given a section of it, see this screen; every change is recorded under Changes."
              : "The parts of Settings the platform's administrator has given you. Every change you make is recorded."}
          </div>
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
