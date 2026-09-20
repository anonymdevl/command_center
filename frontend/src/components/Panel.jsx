import React from "react";

/** A titled block. `note` is the quiet line that says what the figures cover. */
export default function Panel({ title, note, action, onTitleClick, children }) {
  return (
    <div className="panel">
      <div className={onTitleClick ? "ph clickable" : "ph"} onClick={onTitleClick}>
        <div>
          <b>{title}</b>
          {note ? <span>{note}</span> : null}
        </div>
        {action ? <span className="pmore">{action}</span> : null}
      </div>
      {children}
    </div>
  );
}
