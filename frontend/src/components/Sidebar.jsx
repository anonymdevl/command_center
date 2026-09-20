import React from "react";

export default function Sidebar({ nav, current, onGo }) {
  return (
    <div className="side">
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
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onGo(it.key);
                }
              }}
            >
              <span>{it.label}</span>
              {/* No badge. A badge is a tally, and nothing here computes one yet: the
                  designed numbers are demonstration values, and a number sitting in a
                  sidebar reads as fact with no card around it to caveat. It comes back
                  when the engine can count it -- "Daily brief 5" has to mean five
                  things, not five once upon a time. */}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
