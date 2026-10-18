import React, { useEffect, useRef, useState } from "react";
import { boot } from "../api/boot.js";
import { shortDate } from "../format.js";
import Icon, { VIEW_ICON } from "./Icon.jsx";

/**
 * Brand, the nineteen screens, and the business being looked at.
 *
 * The business card sits at the foot of the sidebar because it is the scope of
 * everything above it. It carries the as-of date for the same reason the topbar used
 * to: every ageing figure on every screen is measured against it, so it is always on
 * screen rather than one click away.
 */
export default function Sidebar({ nav, current, onGo, scope, onScope }) {
  return (
    <aside className="side">
      <div className="brand">
        <div className="logo" aria-hidden="true">
          <i />
        </div>
        <div className="brand-t">
          <b>AI Business Intelligence</b>
          <span>Executive Intelligence Platform</span>
        </div>
      </div>

      <nav className="nav" aria-label="Screens">
        {nav.groups.map((g, gi) => (
          <div className="navgrp" key={gi}>
            <div className="navsec">{g.label}</div>
            {g.items.map((it) => (
              <div
                key={it.key}
                className={`navi${it.sub ? " sub" : ""}${current === it.key ? " on" : ""}`}
                onClick={() => onGo(it.key)}
                role="button"
                tabIndex={0}
                aria-current={current === it.key ? "page" : undefined}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onGo(it.key);
                  }
                }}
              >
                <Icon name={VIEW_ICON[it.key]} />
                <span>{it.label}</span>
                {/* No badge. A badge is a tally, and nothing here computes one yet: the
                    designed numbers are demonstration values, and a number sitting in a
                    sidebar reads as fact with no card around it to caveat. It comes back
                    when the engine can count it -- "Today 5" has to mean five things,
                    not five once upon a time. */}
              </div>
            ))}
          </div>
        ))}
      </nav>

      <Business scope={scope} onScope={onScope} />
    </aside>
  );
}

function Business({ scope, onScope }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const real = (boot.scopes || []).filter((s) => s.code !== "__all__");
  // "All businesses" is a scope only once there is more than one business.
  const options = real.length > 1 ? boot.scopes : real;
  const byCode = Object.fromEntries((boot.businesses || []).map((b) => [b.business_code, b]));
  const current = options.find((s) => s.code === scope) || options[0];
  const label = current?.label || "No business connected";
  const canSwitch = options.length > 1;
  // With one business the switcher still opens: it says which business this is and how
  // another one is added, instead of a greyed-out button that reads as broken.
  const canConnect = (boot.user?.roles || []).some((r) => /system manager/i.test(r));

  useEffect(() => {
    if (!open) return;
    const away = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const esc = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("click", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("click", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <div className="biz" ref={ref}>
      <div className="biz-row">
        <div className="biz-av" aria-hidden="true">
          {initials(label)}
        </div>
        <div className="biz-t">
          <b title={label}>{label}</b>
          <AsOf />
        </div>
        <button
          className="biz-sw"
          title={canSwitch ? "Switch business" : "The business you are looking at"}
          aria-label="Switch business"
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={(e) => {
            e.stopPropagation();
            setOpen((o) => !o);
          }}
        >
          <Icon name="swap" size={16} />
        </button>
      </div>

      {open ? (
        <div className="biz-menu" role="listbox" aria-label="Businesses">
          {options.map((s) => {
            const b = byCode[s.code];
            const note = !b ? "" : !b.can_read ? "unreachable" : !b.can_act ? "read only here" : "";
            return (
              <button
                key={s.code}
                role="option"
                aria-selected={s.code === scope}
                className={`biz-opt${s.code === scope ? " on" : ""}`}
                disabled={b ? !b.can_read : false}
                onClick={() => {
                  onScope(s.code);
                  setOpen(false);
                }}
              >
                <span className="biz-av sm" aria-hidden="true">
                  {initials(s.label)}
                </span>
                <span className="biz-opt-t">
                  <b>{s.label}</b>
                  <small>{[b?.currency, note].filter(Boolean).join(" · ")}</small>
                </span>
              </button>
            );
          })}
          {!canSwitch ? (
            <div className="biz-note">
              {options.length ? "This is the only business connected so far. " : "No business is connected yet. "}
              Each Gigmann company on its own ERPNext site can be connected, and then
              chosen here, or seen together as All businesses.
              {canConnect ? (
                <a href="/app/connected-business/new" target="_blank" rel="noreferrer">Connect a business ↗</a>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * What the figures describe, which is not necessarily today.
 *
 * Every ageing number on every screen is measured against this date. Reading it as
 * "today" on a restored dataset is exactly how a stale snapshot becomes a false
 * finding, so it is never hidden.
 */
function AsOf() {
  const d = boot.as_of?.date;
  if (!d) {
    return (
      <span className="asof none" title="Run the load before relying on anything here">
        <i className="dot" /> No figures loaded yet
      </span>
    );
  }
  // The pulse means "current". Data more than two days behind today is a snapshot --
  // a restored backup, a stopped load -- and a live-looking dot over it would be the
  // same false signal as ageing against today.
  const behind = Math.floor((Date.now() - new Date(`${d}T00:00:00`).getTime()) / 86400000);
  return (
    <span
      className={`asof${behind > 2 ? " stale" : ""}`}
      title={`ERPNext connected${boot.site ? ` (${boot.site})` : ""}. The latest date the data covers -- ageing is measured against this, not today${
        boot.as_of.last_run ? ` · last read ${boot.as_of.last_run}` : ""
      }`}
    >
      <i className="dot" /> Figures as at {shortDate(d)}
    </span>
  );
}

function initials(name) {
  const words = (name || "")
    .replace(/\b(ltd|limited|plc|inc)\b\.?/gi, "")
    .split(/\s+/)
    .filter(Boolean);
  return words.slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";
}
