import React from "react";
import { isLive } from "../api/boot.js";

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
              {/* A badge is a live tally. Until a screen reads the facts it has
                  nothing to count, and a number in a sidebar looks like fact. */}
              {it.badge && isLive(it.key) ? <span className="bdg">{it.badge}</span> : null}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
