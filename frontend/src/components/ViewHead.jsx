import React from "react";

/**
 * The line at the top of a screen: what it is, and what the figures cover.
 *
 * A component rather than markup repeated per view. Sales wrote this inline, and
 * twenty-one screens each writing their own is how the heading spacing ends up
 * different on three of them and nobody can say which is correct.
 */
export default function ViewHead({ title, note, action }) {
  return (
    <div className="topbar">
      <div>
        <h3>{title}</h3>
        {note ? <div className="when">{note}</div> : null}
      </div>
      {action ? <div className="acts">{action}</div> : null}
    </div>
  );
}
