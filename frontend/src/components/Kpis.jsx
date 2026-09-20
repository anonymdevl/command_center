import React from "react";
import { api } from "../api/client.js";
import { useApi } from "../useApi.js";
import Figure from "./Figure.jsx";
import Lineage from "./Lineage.jsx";
import { Loading, Failed } from "./States.jsx";
import { exact, shortDate } from "../format.js";

/**
 * A row of figures, named rather than computed.
 *
 * A screen says which KPIs it wants; the server decides what each one means, what
 * it is a subset of, how fresh it is and where its records are. Nothing here
 * adds, divides or captions anything.
 *
 * Sales used to do all of that in JavaScript -- summing buckets to get a total,
 * subtracting to get "inside 90 days", calling percent() for the share, writing
 * the footnote by hand. Each of the other twenty screens would have grown its own
 * version of the same arithmetic, and the first time two disagreed there would be
 * no way to say which was right. The receivable was already misreported once from
 * exactly this: a figure computed one way in one place.
 *
 * So: one request, one component, one definition of every number.
 */
export default function Kpis({ keys, scope, openDrawer, columns, what = "the figures" }) {
  const { data, error, loading, reload } = useApi(
    () => api.kpis({ keys, business_code: scope }),
    [scope, keys.join(",")]
  );

  if (loading) return <Loading what={`Reading ${what}`} />;
  if (error) return <Failed error={error} onRetry={reload} what={what} />;
  if (!data) return null;

  const width = columns || Math.min(keys.length, 4);

  return (
    <div className="kpis" style={{ gridTemplateColumns: `repeat(${width},1fr)` }}>
      {keys.map((key) => {
        const k = data[key];
        if (!k) return null;
        return (
          <Figure
            key={key}
            label={k.label}
            value={display(k)}
            currency={k.unit === "currency" && k.currency ? k.currency : undefined}
            suffix={k.unit === "percent" && k.value !== null ? "%" : undefined}
            note={k.note || ""}
            tone={tone(k)}
            flag={flag(k)}
            title={hover(k)}
            onClick={() => open(k, scope, openDrawer)}
          />
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------------- */

/**
 * What goes in the middle of the card.
 *
 * A ratio with no denominator returns null, and that is not zero. A margin of 0%
 * and a margin that cannot be worked out are different statements, and printing
 * the first when the server meant the second would be the interface inventing a
 * fact.
 */
function display(k) {
  if (k.value === null || k.value === undefined) return "—";
  if (k.unit === "percent") return Number(k.value).toFixed(1);
  if (k.unit === "currency" && !k.currency) return exact(k.value); // see mixed_currency
  return k.value;
}

/** Tone follows the KPI's declared direction. It never reacts to the size of the number. */
function tone(k) {
  if (k.direction === "higher_is_worse") return "dn";
  if (k.direction === "higher_is_better") return "up";
  return "flat";
}

/**
 * The corner badge, used only when the figure needs a caveat to be read correctly.
 *
 * Staleness is the one that matters on this engagement: the dataset covers up to a
 * date well before today, and a figure that does not say so reads as current.
 */
function flag(k) {
  // Tones are the design system's severity names, not invented ones. "bad" was used
  // here and is not a class the stylesheet defines, so a failed load would have been
  // styled exactly like an ordinary badge -- the one case where the difference
  // carries the whole message.
  if (k.data_status?.state === "failed") return { label: "load failed", tone: "f-crit" };
  if (k.data_status?.state === "not_loaded") return { label: "no data", tone: "f-dim" };
  if (k.data_status?.state === "stale") return { label: "as at", tone: "f-med" };
  if (k.mixed_currency) return { label: "mixed currencies", tone: "f-high" };
  return undefined;
}

/** Everything the card cannot fit, on hover. Assembled from the server's answer only. */
function hover(k) {
  const lines = [];
  if (k.as_of?.date) lines.push(`As at ${shortDate(k.as_of.date)} — ${k.as_of.basis}.`);
  if (k.subset_of) lines.push(`A subset of ${k.subset_of}.`);
  if (k.data_status?.message) lines.push(k.data_status.message);
  if (k.mixed_currency)
    lines.push(
      "The connected businesses do not all report in one currency, so this is a sum of unlike amounts."
    );
  lines.push("Opens to the records behind it.");
  return lines.join(" ");
}

/**
 * Opening a figure.
 *
 * A ratio has no records of its own -- it is two other figures divided -- so it
 * opens to its numerator instead, which does. That is stated by the server in
 * drill.kpis rather than guessed here.
 */
function open(k, scope, openDrawer) {
  if (!openDrawer) return;
  if (k.drill?.kpis) {
    openDrawer(
      <Ratio keys={k.drill.kpis} label={k.label} scope={scope} openDrawer={openDrawer} />
    );
    return;
  }
  openDrawer(
    <Lineage
      scope={scope}
      fact={k.drill.fact}
      filters={k.drill.filters}
      title={k.label}
      subset={k.subset_of}
    />
  );
}

/** What a percentage is made of: the two figures, then the records under the top one. */
function Ratio({ keys, label, scope, openDrawer }) {
  return (
    <>
      <div className="dhead">
        <div>
          <div className="dt">How it is worked out</div>
          <h4>{label}</h4>
        </div>
      </div>
      <Kpis keys={keys} scope={scope} openDrawer={openDrawer} columns={2} what="the parts" />
      <div className="drfoot">
        The percentage is the first divided by the second. Open either one to see its
        records.
      </div>
    </>
  );
}
