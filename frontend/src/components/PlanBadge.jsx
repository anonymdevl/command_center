import React from "react";
import { boot } from "../api/boot.js";
import "../styles/plans.css";

/**
 * Under the logo: the plan the organisation bought, whom it is licensed to and when it
 * renews (insights/core/plans.py boot()). Shown only to people on a customer; it opens
 * Plan & Usage for the customer's Account Managers and is a plain label for its Users.
 * Nothing at all for anyone else, so the sidebar is as it always was.
 */
export default function PlanBadge({ current, onGo }) {
  const p = boot.plan;
  if (!p) return null;
  const when = p.no_expiry ? "No expiry" : `Renews ${p.renews}`;
  const flag = p.state === "active" ? null : p.state;
  const body = (
    <>
      <span className="pl-badge-h">
        <b>{p.plan} Plan</b>
        {flag ? <span className={`pl-state ${flag}`}>{p.state_label}</span> : null}
      </span>
      <span className="pl-badge-t">
        Licensed to {p.licensed_to} · {when}
      </span>
    </>
  );
  if (!p.can_view) {
    return <div className="pl-badge" title={`${p.plan} Plan · Licensed to ${p.licensed_to} · ${when}`}>{body}</div>;
  }
  return (
    <button
      type="button"
      className={`pl-badge pl-badge-btn${current === "plan" ? " on" : ""}`}
      onClick={() => onGo("plan")}
      title="Plan & Usage"
      aria-current={current === "plan" ? "page" : undefined}
    >
      {body}
    </button>
  );
}

/** The licence banner over every screen, during grace and once lapsed. */
export function LicenceBanner() {
  const p = boot.plan;
  if (!p?.banner) return null;
  return (
    <div className={`pl-banner ${p.state}`} role="status">
      <b>{p.state === "lapsed" ? "Licence lapsed." : "Licence renewal due."}</b> {p.banner}
    </div>
  );
}
