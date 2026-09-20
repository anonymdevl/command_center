import React from "react";
import { money, count } from "../format.js";

/**
 * The card contract.
 *
 * Settled the hard way over many rounds, and the rules are not decoration:
 *
 *   Every card is the same height, and the figure is centred in it.
 *   Every card has the hairline above its footnote -- rendered even when the
 *     footnote is empty, because a line that appears on some cards and not
 *     others reads as a distinction that is not there.
 *   Every card gets the same hover outline.
 *   Money leads with its currency.
 *   Nothing wraps. Long labels ellipsis rather than pushing the card taller.
 */
export default function Figure({
  label,
  value,
  currency,
  suffix,
  note,
  tone = "flat",
  flag,
  onClick,
  title,
}) {
  const clickable = typeof onClick === "function";
  const parts =
    currency != null ? money(value, currency) : { figure: null, suffix: "" };

  return (
    <div
      className={clickable ? "kpi clickable" : "kpi"}
      onClick={onClick}
      title={title}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick(e);
              }
            }
          : undefined
      }
    >
      <div className="khead">
        <div className="lab">{label}</div>
        {flag ? <span className={`flag ${flag.tone || ""}`}>{flag.label}</span> : null}
      </div>

      <div className="val">
        {currency != null ? (
          <>
            <span className="cx">{parts.currency}</span>
            {parts.figure}
            {parts.suffix ? <span className="mag">{parts.suffix}</span> : null}
          </>
        ) : (
          <>
            {typeof value === "number" ? count(value) : value}
            {suffix ? <span className="cur">{suffix}</span> : null}
          </>
        )}
      </div>

      {/* Always rendered. An empty slot keeps the hairline and the height. */}
      <div className={`delta ${tone}`}>{note || " "}</div>
    </div>
  );
}
