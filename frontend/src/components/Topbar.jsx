import React, { useEffect, useState } from "react";
import { boot } from "../api/boot.js";
import { shortDate } from "../format.js";
import Appearance from "./Appearance.jsx";

export default function Topbar({ scope, onScope }) {
  const real = (boot.scopes || []).filter((s) => s.code !== "__all__");
  // "All businesses" is a scope only once there is more than one business.
  const options = real.length > 1 ? boot.scopes : real;
  const byCode = Object.fromEntries((boot.businesses || []).map((b) => [b.business_code, b]));

  return (
    <div className="topnav">
      <div className="brand">
        <div className="logo">IC</div>
        <div>
          <b>Intelligent Command Center</b>
          <span>Executive platform</span>
        </div>
      </div>

      <span className="lbl">Business</span>
      <select className="sel" value={scope} onChange={(e) => onScope(e.target.value)}>
        {options.map((s) => {
          const b = byCode[s.code];
          const bits = [s.label];
          if (b?.currency) bits.push(b.currency);
          if (b && !b.can_read) bits.push("unreachable");
          else if (b && !b.can_act) bits.push("read only here");
          return (
            <option key={s.code} value={s.code} disabled={b ? !b.can_read : false}>
              {bits.join(" · ")}
            </option>
          );
        })}
      </select>

      <span className="spacer" />
      <Appearance />
      <Connection />
      <AsOf />
      <Who />
    </div>
  );
}

function Connection() {
  return (
    <span className="live">
      <span className="dot" />
      ERPNext connected <small>{boot.site}</small>
    </span>
  );
}

/**
 * What the figures describe, which is not necessarily today.
 *
 * Shown in the topbar rather than buried, because every ageing number on every
 * screen is measured against this date. Reading it as "today" on a restored
 * dataset is exactly how a stale snapshot becomes a false finding.
 */
function AsOf() {
  const d = boot.as_of?.date;
  if (!d) {
    return (
      <span className="asof" title="Run the load before relying on anything here">
        ● No figures loaded yet
      </span>
    );
  }
  return (
    <span
      className="asof"
      title={`The latest date the data covers. Ageing is measured against this, not today${
        boot.as_of.last_run ? ` · last read ${boot.as_of.last_run}` : ""
      }`}
    >
      ● Figures as at {shortDate(d)}
    </span>
  );
}

function Who() {
  const u = boot.user || {};
  const roles = (u.roles || []).join(" \u00b7 ") || "Management";
  return (
    <div className="who nopick" style={{ cursor: "default" }}>
      <div className="av">{u.initials}</div>
      <div className="whotxt">
        {/* .whosel carries the name's type, width and truncation. The original
            was a <select> of personas; with a real session the only person it
            can be is the one signed in, so it is no longer a control -- but it
            keeps the class, because that is what the design styles. */}
        <div className="whosel" title={u.name}>
          {u.name}
        </div>
        <span>{roles}</span>
      </div>
    </div>
  );
}
