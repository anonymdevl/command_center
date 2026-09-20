import React from "react";

/** Waiting. Deliberately quiet: a spinner that shouts makes a fast load feel slow. */
export function Loading({ what = "Reading the figures" }) {
  return (
    <div className="step">
      <span className="spin" />
      {what}…
    </div>
  );
}

/**
 * Something failed.
 *
 * Says what did not load and offers to try again. It never shows a traceback:
 * the person reading this is a manager, and an exception tells them nothing they
 * can act on.
 */
export function Failed({ error, onRetry, what = "these figures" }) {
  return (
    <div className="warn">
      <b>Could not load {what}.</b> {error?.message || "The server did not answer."}
      {onRetry ? (
        <div className="acts" style={{ marginTop: 10 }}>
          <button className="btn" onClick={onRetry}>
            Try again
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** Nothing there -- which is a fact about the business, not an error. */
export function Empty({ children }) {
  return <div className="thin">{children}</div>;
}
