import React from "react";

/**
 * The platform's built-in mark: a lens over four bars and a line of four ring nodes.
 * Shown wherever no logo is uploaded (Settings -> Branding): the sidebar, the sign-in
 * page (command-center-login.html carries the same drawing), and the Settings slots'
 * previews. The favicon file (public/images/command-center.svg) is the same drawing on
 * its own tile.
 *
 * One colour, currentColor, so the tile around it (shell.py) decides light or dark.
 * The line stops short of each node instead of being masked, so the drawing carries no
 * ids and can appear any number of times on a page. insights/tests.py checks that the
 * three copies keep the same geometry.
 */
export default function LensMark({ className = "cc-lens" }) {
  return (
    <svg className={className} viewBox="40 40 460 460" aria-hidden="true" focusable="false">
      <g fill="none" stroke="currentColor">
        <circle cx="222" cy="222" r="158" strokeWidth="44" />
        <path d="M335 335L378 378" strokeWidth="34" />
        <path d="M392 392L462 462" strokeWidth="70" strokeLinecap="round" />
        <path d="M174.6 205.2L188.4 212.8M217.5 207.7L239.5 182.3M267.2 156.6L284.8 143.4" strokeWidth="10" />
        <circle cx="158" cy="196" r="13" strokeWidth="10" />
        <circle cx="205" cy="222" r="13" strokeWidth="10" />
        <circle cx="252" cy="168" r="13" strokeWidth="10" />
        <circle cx="300" cy="132" r="13" strokeWidth="10" />
      </g>
      <g fill="currentColor">
        <rect x="138" y="232" width="40" height="78" />
        <rect x="186" y="262" width="40" height="48" />
        <rect x="234" y="212" width="40" height="98" />
        <rect x="282" y="170" width="40" height="140" />
      </g>
    </svg>
  );
}
