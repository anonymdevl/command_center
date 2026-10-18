import React from "react";

/**
 * One icon set, drawn for this interface.
 *
 * Inline SVG rather than an icon library: twenty-odd glyphs do not justify a
 * dependency, and a library's defaults are recognisable at a glance -- part of what
 * made the first design read as generated. Every glyph is a 24-unit grid, 1.7 stroke,
 * round caps, so they sit together as one family.
 */
const PATHS = {
  home: <path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z" />,
  doc: (
    <>
      <path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2.5" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </>
  ),
  grid: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.8" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.8" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.8" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.8" />
    </>
  ),
  pulse: <path d="M3 12h4l3-7 4 14 3-7h4" />,
  shield: <path d="M12 3 4.5 6v6c0 4.4 3.2 8 7.5 9 4.3-1 7.5-4.6 7.5-9V6z" />,
  check: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.2 12.2 2.6 2.6 5-5.6" />
    </>
  ),
  list: (
    <>
      <path d="M10 6h10M10 12h10M10 18h10" />
      <path d="m3.5 6 1.3 1.3L7 5M3.5 12l1.3 1.3L7 11" />
      <circle cx="5" cy="18" r="1.2" />
    </>
  ),
  spark: (
    <>
      <path d="M11 3.5l1.7 4.8 4.8 1.7-4.8 1.7L11 16.5l-1.7-4.8L4.5 10l4.8-1.7z" />
      <path d="M18.5 14.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" />
    </>
  ),
  chart: <path d="M4 20V11M10 20V5M16 20v-6M21 20H3" />,
  trend: (
    <>
      <path d="M3 17l6-6 4 4 8-8" />
      <path d="M15 7h6v6" />
    </>
  ),
  cart: (
    <>
      <circle cx="9.5" cy="19.5" r="1.5" />
      <circle cx="17.5" cy="19.5" r="1.5" />
      <path d="M2.5 3.5h3l2.4 11.5h10.6L21 7.5H6.3" />
    </>
  ),
  box: (
    <>
      <path d="M20.5 7.8 12 3 3.5 7.8v8.4L12 21l8.5-4.8z" />
      <path d="M3.5 7.8 12 12.6l8.5-4.8M12 12.6V21" />
    </>
  ),
  kanban: (
    <>
      <rect x="3" y="3.5" width="18" height="17" rx="2.5" />
      <path d="M8 8v7M12 8v9M16 8v4" />
    </>
  ),
  chat: <path d="M20.5 12a8.5 8.5 0 0 1-12.4 7.5L3.5 20.5l1-4.4A8.5 8.5 0 1 1 20.5 12z" />,
  wallet: (
    <>
      <rect x="3" y="6" width="18" height="14" rx="2.5" />
      <path d="M16 13.5h2M6 6V4.5h11V6" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20a6.5 6.5 0 0 1 13 0" />
      <path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.4a6.5 6.5 0 0 1 3.5 5.6" />
    </>
  ),
  lock: (
    <>
      <rect x="4.5" y="10.5" width="15" height="10.5" rx="2.5" />
      <path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" />
    </>
  ),
  clipboard: (
    <>
      <rect x="5" y="4.5" width="14" height="16.5" rx="2.5" />
      <path d="M9 4.5V3h6v1.5M9 13l2 2 4-4.5" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.8-3.8" />
    </>
  ),
  sliders: (
    <>
      <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
      <circle cx="15" cy="7" r="2.2" />
      <circle cx="9" cy="17" r="2.2" />
    </>
  ),
  moon: <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4 6.8 6.8 0 0 0 20 14.5z" />,
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" />
    </>
  ),
  swap: <path d="M7 4 3.5 7.5 7 11M3.5 7.5h13M17 13l3.5 3.5L17 20M20.5 16.5h-13" />,
  arrow: <path d="M7 17 17 7M8.5 7H17v8.5" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  bell: <path d="M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 2h-15zM10 20.5a2.2 2.2 0 0 0 4 0" />,
};

/** Which glyph each screen uses in the sidebar, by view key. */
export const VIEW_ICON = {
  command: "home",
  brief: "doc",
  myday: "calendar",
  ops: "grid",
  health: "pulse",
  risk: "shield",
  approvals: "check",
  delegation: "list",
  ask: "spark",
  reports: "chart",
  sales: "trend",
  proc: "cart",
  inv: "box",
  eng: "kanban",
  cx: "chat",
  fin: "wallet",
  hr: "users",
  it: "lock",
  aud: "clipboard",
};

export default function Icon({ name, size = 18, className = "" }) {
  const glyph = PATHS[name];
  if (!glyph) return null;
  return (
    <svg
      className={`ic ${className}`.trim()}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {glyph}
    </svg>
  );
}
