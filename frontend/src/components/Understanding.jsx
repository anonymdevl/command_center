import React, { useEffect, useRef } from "react";
import Records from "./Records.jsx";
import { exact, count } from "../format.js";
import { chartModel } from "../legacy/charts.js";
import { createViz } from "../legacy/viz.js";
import "../styles/insight.css";

/**
 * "Understanding This Figure" (api/insight.py), drawn as the drawer's Insight and Trend
 * tabs (Records.jsx owns the frame: header, hero, tabs, records).
 *
 * The records alone present the data; this says what the figure is and how it is worked
 * out, what it should look like, what is driving it now (with the reconciliation bridge
 * for receivables and payables), what to do about it in ERPNext, how to stop it
 * recurring, and the related figures -- every number computed on the server, nothing
 * written here. Explain This asks the analyst for a short management explanation of
 * the same numbers; the section stands on its own without it.
 */

/** The drawer a figure opens: its explanation, then its records (or its ERPNext list). */
export function FigureDrawer({ figure, scope, openDrawer }) {
  return (
    <Records scope={scope} kpi={figure.key} figure={figure} fact={figure.drill?.fact || null}
             filters={figure.drill?.filters} title={figure.label} subset={figure.subset_of}
             explainedBy={figure.explained_by} href={figure.drill?.href || null}
             openDrawer={openDrawer} />
  );
}
FigureDrawer.ownsHeader = true;

/** Whether the figure has a series worth a Trend tab of its own. */
export function hasTrend(s) {
  const pts = (s?.trend?.points || []).filter((p) => p.value !== null && p.value !== undefined);
  return pts.length >= 2;
}

/** The status chip's tone, from api/insight's status. */
export const STATUS_TONE = { attention: "dw-c-crit", watch: "dw-c-high", on_target: "dw-c-ok" };

/* ------------------------------------------------------------------------- */
/**
 * The Insight tab of a figure: key numbers, the bridge, what to do and how to prevent
 * it, then the working -- checks, what is driving it, related figures, what it is.
 * `extra` is what the records add (what covers it, where it is concentrated); `tiles`
 * stand in when the explanation has no key numbers of its own.
 */
export function InsightBody({ s, scope, openDrawer, extra = null, tiles = null, href = null }) {
  const cur = s.currency || "";
  const d = s.diagnosis;
  const chips = (d?.chips || []).slice(0, 4).map((c) => ({
    label: c.label, value: fmt(c.value, c.unit, cur), tone: TONE[c.state],
  }));
  const rest = (d?.sentences || []).filter((t) => t !== s.headline);
  const res = s.resolution || {};
  const todo = res.steps?.length ? res.steps : null;
  const improve = !todo && res.improve?.length ? res.improve : null;
  return (
    <>
      {s.guide ? (
        <Sec title="Nothing Recorded Yet"><Guide g={s.guide} /></Sec>
      ) : null}

      {chips.length ? <Sec><Tiles tiles={chips} /></Sec> : tiles?.length ? <Sec><Tiles tiles={tiles} /></Sec> : null}

      {d?.bridge ? (
        <Sec title={`From ${title(String(d.bridge.steps[0]?.label || "the invoices").replace(/^On /, ""))} To The Ledger`}>
          <BridgeBars b={d.bridge} cur={cur} />
        </Sec>
      ) : null}

      {todo || improve || s.prevention?.length ? (
        <div className="dw-sec dw-two">
          {todo || improve ? (
            <div>
              <h5 className="dw-lab">{todo ? "What To Do" : "How To Improve It"}</h5>
              {todo ? <ol className="dw-steps">{todo.map((t) => <li key={t}>{t}</li>)}</ol> : null}
              {improve ? (
                <ul className="dw-steps dw-plain">
                  {improve.map((x) => (
                    <li key={x.text}>{x.text}{x.href ? <> <Ext href={x.href} label={x.label} /></> : null}</li>
                  ))}
                </ul>
              ) : null}
              {res.owner || res.order ? (
                <div className="dw-chips">
                  {res.owner ? <span className="dw-chip">Owner: {res.owner}</span> : null}
                </div>
              ) : null}
              {res.order ? <p className="dw-note">{res.order}</p> : null}
              {res.guide?.href ? (
                <a className="dw-btn dw-cta" href={res.guide.href} target="_blank" rel="noreferrer">
                  {res.guide.label || "Open in ERPNext"} ↗
                </a>
              ) : null}
            </div>
          ) : <div />}
          {s.prevention?.length ? (
            <div>
              <h5 className="dw-lab">Prevent It</h5>
              <ul className="dw-prev">
                {s.prevention.map((p) => (
                  <li key={p.text} className={p.state === "ok" ? "on" : p.state === "warn" ? "off" : undefined}>
                    <span className="dw-tick" aria-label={p.state === "ok" ? "In place" : "Not confirmed"}>
                      {p.state === "ok" ? "✓" : ""}
                    </span>
                    <span>{p.text} {p.href ? <Ext href={p.href} label={p.label} /> : null}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      {s.expected?.text || s.expected?.checks?.length ? (
        <Sec title="What It Should Look Like">
          {s.expected.text ? <p className="dw-p">{s.expected.text}</p> : null}
          {s.expected.checks?.length ? (
            <ul className="ins-checks">
              {s.expected.checks.map((c) => (
                <li key={c.label} className={`ins-c ins-${c.state}`}>
                  <span className="ins-dot" aria-hidden="true" />
                  <div>
                    <b>{c.label}</b>
                    <span className="ins-state">{STATE[c.state]}</span>
                    <p>{c.text}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </Sec>
      ) : null}

      {d && (rest.length || d.contributors || d.unmatched || d.ageing || d.tables?.length) ? (
        <Sec title="What Is Driving It">
          {rest.map((t) => <p key={t} className="dw-p">{t}</p>)}
          {d.contributors ? (
            <Contributors c={d.contributors} cur={cur} scope={scope} openDrawer={openDrawer} />
          ) : null}
          {d.unmatched ? <Unmatched u={d.unmatched} cur={cur} /> : null}
          {d.ageing && d.focus === "ageing" ? <Ageing a={d.ageing} cur={cur} /> : null}
          {d.credit && d.focus === "credit" && d.credit !== d.contributors ? (
            <Contributors c={d.credit} cur={cur} scope={scope} openDrawer={openDrawer} />
          ) : null}
          {(d.tables || []).map((t) => (
            <Table key={t.title} t={t} cur={cur} scope={scope} openDrawer={openDrawer} />
          ))}
        </Sec>
      ) : null}

      {extra}

      {s.related?.length || s.open_items?.length || s.link || href ? (
        <Sec title="Related">
          {s.related?.length ? (
            <div className="ins-rel">
              {s.related.map((r) => (
                <button type="button" key={r.key} className="ins-relb"
                        onClick={() => openDrawer?.(<FigureDrawer figure={r} scope={scope} openDrawer={openDrawer} />)}>
                  <span>{r.label}</span>
                  <b>{fmt(r.value, r.unit, r.currency || cur)}</b>
                </button>
              ))}
            </div>
          ) : null}
          {s.open_items?.length ? (
            <ul className="ins-open">
              {s.open_items.map((o) => (
                <li key={`${o.kind}-${o.title}`}>
                  <span className="ins-kind">{o.kind}</span>
                  <b>{o.title}</b>
                  {o.why ? <p>{o.why}</p> : null}
                  {o.next ? <p className="ins-mut">First: {o.next}</p> : null}
                </li>
              ))}
            </ul>
          ) : null}
          {s.link || href ? (
            <div className="dw-chips">
              {s.link ? (
                <button type="button" className="dw-btn" onClick={() => {
                  window.closeDrawer?.();
                  window.go?.(s.link.view);
                }}>{s.link.label}</button>
              ) : null}
              {href ? (
                <a className="dw-btn" href={href} target="_blank" rel="noreferrer">
                  Open The Records In ERPNext ↗
                </a>
              ) : null}
            </div>
          ) : null}
        </Sec>
      ) : null}

      <Sec title="What It Is">
        <p className="dw-p">{s.what.text}</p>
        {s.what.how ? <p className="dw-note">{s.what.how}</p> : null}
        {s.as_of?.date ? <p className="dw-note">As at {s.as_of.date}, {s.as_of.basis}.</p> : null}
      </Sec>
    </>
  );
}

/** The Trend tab: the series, and how the latest compares. */
export function TrendBody({ s }) {
  return (
    <Sec title={s.trend.title}>
      <Trend t={s.trend} cur={s.currency || ""} />
    </Sec>
  );
}

/** The analyst's explanation, at the top of the Insight tab once asked for. */
export function AiNote({ ai }) {
  if (!ai.text && !ai.error && !ai.busy) return null;
  return (
    <div className={`dw-sec dw-ai${ai.error ? " dw-ai-err" : ""}`} role="status">
      <h5 className="dw-lab">The Analyst's Explanation</h5>
      {ai.busy ? <p className="dw-note">Writing a short explanation of these figures…</p> : null}
      {ai.error ? <p className="dw-p">{ai.error}</p> : null}
      {ai.text ? <AiText text={ai.text} /> : null}
      {ai.text ? (
        <p className="dw-note">Written by the analyst from the figures in this drawer only; every number in it was checked against them.</p>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------------- */
const STATE = { ok: "As expected", warn: "Needs attention", bad: "Off target", info: "For information" };
const KIND = { process: "Process", timing: "Timing", position: "Position", unexplained: "Unexplained" };
const TONE = { bad: "crit", warn: "high", ok: "ok" };
const title = (t) => t.replace(/(^|\s)(\S)/g, (m, sp, c) => sp + c.toUpperCase());

export function Sec({ title, children }) {
  return (
    <section className="dw-sec">
      {title ? <h5 className="dw-lab">{title}</h5> : null}
      {children}
    </section>
  );
}

/** Up to four key numbers. */
export function Tiles({ tiles }) {
  return (
    <div className="dw-tiles">
      {tiles.slice(0, 4).map((t) => (
        <div key={t.label} className={`dw-tile${t.tone ? ` dw-t-${t.tone}` : ""}`}>
          <span className="dw-tile-l">{t.label}</span>
          <b title={t.value}>{t.value}</b>
          {t.note ? <span className="dw-tile-n" title={t.note}>{t.note}</span> : null}
        </div>
      ))}
    </div>
  );
}

function Ext({ href, label }) {
  return <a className="dlink" href={href} target="_blank" rel="noreferrer">{label || "Open in ERPNext"} ↗</a>;
}

function Guide({ g }) {
  return (
    <div className="guide guide-compact">
      <p className="guide-t">{g.text}</p>
      {g.steps?.length ? <ol className="guide-s">{g.steps.map((t) => <li key={t}>{t}</li>)}</ol> : null}
      {g.href ? <a className="btn guide-a" href={g.href} target="_blank" rel="noreferrer">{g.label || "Open in ERPNext"}</a> : null}
    </div>
  );
}

export function fmt(v, unit, cur = "") {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "string" && Number.isNaN(Number(v))) return v;
  const n = Number(v);
  if (unit === "currency") return `${cur} ${exact(n)}`.trim();
  if (unit === "percent") return `${n.toFixed(1)}%`;
  if (unit === "days") return `${count(Math.round(n))} days`;
  if (unit === "date" || unit === "time") return String(v);
  return Number.isInteger(n) ? count(n) : exact(n);
}

function Chips({ chips, cur }) {
  return (
    <div className="ins-chips">
      {chips.map((c) => (
        <div key={c.label} className={`ins-chip${c.state ? ` ins-${c.state}` : ""}`}>
          <span>{c.label}</span>
          <b>{fmt(c.value, c.unit, cur)}</b>
        </div>
      ))}
    </div>
  );
}

/** A chart drawn by the platform's one chart module, from a chart block. */
function Chart({ spec, title }) {
  const ref = useRef(null);
  useEffect(() => {
    const host = ref.current;
    const m = host ? chartModel(spec) : null;
    if (!m) return undefined;
    const viz = createViz(m, { key: title ? `insight:${title}` : null, title, compact: true });
    host.replaceChildren(viz.node);
    return () => {
      viz.dispose?.();
      host.replaceChildren();
    };
  }, [JSON.stringify(spec), title]);
  return <div ref={ref} className="ins-chart" />;
}

/**
 * The bridge as horizontal bars, each step against the largest, then the step-by-step
 * table (kind, how many) a click away. The arithmetic is the server's.
 */
function BridgeBars({ b, cur }) {
  const drawn = b.steps.filter((x) => x.kind === "total" || Math.abs(x.value) >= 0.005);
  const most = Math.max(...drawn.map((x) => Math.abs(x.value)), 0) || 1;
  return (
    <>
      <div className="dw-bars">
        {drawn.map((x, i) => {
          const tone = i === 0 ? "start" : x.kind === "total" ? "end" : x.kind;
          return (
            <div key={x.id} className={`dw-bar${x.kind === "total" ? " dw-bar-tot" : ""}`}>
              <span className="dw-bar-l" title={x.note ? `${x.label} (${x.note})` : x.label}>{x.label}</span>
              <span className="dw-bar-t" aria-hidden="true">
                <i className={`dw-b-${tone}`} style={{ width: `${Math.max(1, (100 * Math.abs(x.value)) / most)}%` }} />
              </span>
              <span className="dw-bar-v">{x.value < 0 ? `−${exact(-x.value)}` : exact(x.value)}</span>
            </div>
          );
        })}
      </div>
      <p className={`dw-note ${b.reconciles ? "dw-ok" : "dw-bad"}`}>
        {b.reconciles
          ? `Reconciles to the cent; ${cur} ${exact(b.unexplained)} is not explained by the records.`
          : `Does not reconcile: ${cur} ${exact(b.residual)} is left by the arithmetic.`}
      </p>
      <details className="dw-more">
        <summary>Step By Step</summary>
        <div className="ins-scroll">
          <table className="dt ins-t">
            <thead>
              <tr><th>Step</th><th>Kind</th><th style={{ textAlign: "right" }}>How Many</th>
                <th style={{ textAlign: "right" }}>{cur}</th></tr>
            </thead>
            <tbody>
              {b.steps.map((x) => (
                <tr key={x.id} className={x.kind === "total" ? "ins-total" : undefined}>
                  <td>{x.label}{x.note ? <div className="ins-mut">{x.note}</div> : null}</td>
                  <td>{KIND[x.kind] ? <span className={`ins-tag ins-k-${x.kind}`}>{KIND[x.kind]}</span> : null}</td>
                  <td className="num">{x.count ? `${count(x.count)} ${x.count_word || ""}` : ""}</td>
                  <td className="num">{exact(x.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}

const BY = {
  gap: ["The largest differences", "Difference"],
  unmatched: ["Most money not matched", "Not matched"],
  d90_plus: ["Most over 90 days", "Over 90 days"],
  in_credit: ["Most in credit", "In credit"],
};

function Contributors({ c, cur, scope, openDrawer }) {
  const [title, col] = BY[c.by] || BY.gap;
  return (
    <div className="ins-block">
      <h6>{title} <span className="ins-mut">· {c.rows.length} of {count(c.parties)}, {c.top_share}% of {cur} {exact(c.total)}</span></h6>
      <div className="ins-scroll">
        <table className="dt ins-t">
          <thead>
            <tr><th>Name</th><th style={{ textAlign: "right" }}>{col}</th>
              <th style={{ textAlign: "right" }}>Share</th>
              <th style={{ textAlign: "right" }}>Open invoices</th>
              <th style={{ textAlign: "right" }}>By the ledger</th><th>Act</th></tr>
          </thead>
          <tbody>
            {c.rows.map((r) => (
              <tr key={r.party} className="clickable" title={`Open ${r.party}'s open invoices`}
                  onClick={() => openDrawer?.(
                    <Records scope={scope} fact={r.open.fact} filters={r.open.filters}
                             title={r.open.title} openDrawer={openDrawer} />)}>
                <td className="dw-name"><span className="dw-clip" title={r.party}>{r.party}</span></td>
                <td className="num">{exact(r.value)}</td>
                <td className="num">{r.share == null ? "—" : `${r.share}%`}</td>
                <td className="num">{exact(r.open_invoices)}</td>
                <td className="num">{exact(r.ledger_balance)}</td>
                <td className="ins-acts" onClick={(e) => e.stopPropagation()}>
                  {(r.links || []).map((l) => <Ext key={l.label} href={l.href} label={l.label} />)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Unmatched({ u, cur }) {
  if (u.error) return <p className="ins-mut">{u.error}</p>;
  if (!u.count) return null;
  return (
    <div className="ins-block">
      <h6>Payments not matched, by age</h6>
      <Chips cur={cur} chips={[
        { label: `Recent, ${u.timing_days} days or less (timing)`, value: u.recent.total, unit: "currency" },
        { label: `Older (process)`, value: u.old.total, unit: "currency", state: u.old.total ? "bad" : "ok" },
        { label: "Payments", value: u.count, unit: "count" },
      ]} />
      <div className="ins-scroll">
        <table className="dt ins-t">
          <thead>
            <tr><th>Oldest first</th><th>Name</th><th>Date</th>
              <th style={{ textAlign: "right" }}>Days</th><th style={{ textAlign: "right" }}>{cur}</th></tr>
          </thead>
          <tbody>
            {u.oldest.map((i) => (
              <tr key={i.name}>
                <td><a className="dlink" href={i.href} target="_blank" rel="noreferrer">{i.name} ↗</a></td>
                <td className="dw-name"><span className="dw-clip" title={i.party}>{i.party}</span></td>
                <td className="dw-date">{i.date}</td>
                <td className="num">{i.days == null ? "—" : count(i.days)}</td>
                <td className="num">{exact(i.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Ageing({ a, cur }) {
  const spec = {
    type: "bar", title: "Owed, by age after matching", unit: cur,
    labels: a.buckets.map((b) => b.label), series: [{ name: cur, values: a.buckets.map((b) => b.value) }],
  };
  return (
    <div className="ins-block">
      <h6>By age, after payments not yet matched are set against the oldest</h6>
      <Chart spec={spec} title="Owed, by age after matching" />
      {a.invoices_over_90 ? (
        <p className="ins-mut">Aged as the invoices stand, {cur} {exact(a.invoices_over_90)} of {cur} {exact(a.invoices_total)} looks over 90 days.</p>
      ) : null}
    </div>
  );
}

function Table({ t, cur, scope, openDrawer }) {
  return (
    <div className="ins-block">
      <h6>{t.title}</h6>
      <div className="ins-scroll">
        <table className="dt ins-t">
          <thead>
            <tr>
              {t.columns.map(([label, unit]) => (
                <th key={label} style={unit !== "text" ? { textAlign: "right" } : undefined}>
                  {unit === "currency" ? `${label} ${cur}`.trim() : label}
                </th>
              ))}
              {t.rows.some((r) => r.links?.length) ? <th>Act</th> : null}
            </tr>
          </thead>
          <tbody>
            {t.rows.map((r, i) => (
              <tr key={`${r.cells[0]}-${i}`} className={r.open ? "clickable" : undefined}
                  onClick={r.open ? () => openDrawer?.(
                    <Records scope={scope} fact={r.open.fact} filters={r.open.filters}
                             title={r.open.title} openDrawer={openDrawer} />) : undefined}>
                {r.cells.map((v, j) => {
                  const unit = t.columns[j]?.[1];
                  return unit === "text"
                    ? <td key={j} className="dw-name"><span className="dw-clip" title={String(v)}>{String(v)}</span></td>
                    : <td key={j} className="num">{unit === "currency" ? exact(v) : fmt(v, unit, cur)}</td>;
                })}
                {r.links?.length ? (
                  <td className="ins-acts" onClick={(e) => e.stopPropagation()}>
                    {r.links.map((l) => <Ext key={l.label} href={l.href} label={l.label} />)}
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Trend({ t, cur }) {
  const pts = (t.points || []).filter((p) => p.value !== null && p.value !== undefined);
  const unit = t.unit === "currency" ? cur : t.unit === "percent" ? "%" : "";
  return (
    <>
      {pts.length >= 2 ? (
        <Chart title={t.title} spec={{
          type: t.mode === "raised" ? "bar" : "line", title: t.title, unit,
          labels: pts.map((p) => p.label), series: [{ name: t.title, values: pts.map((p) => Number(p.value)) }],
        }} />
      ) : null}
      {t.compare?.length ? (
        <Chips cur={cur} chips={[
          ...t.compare.map((c) => ({ label: c.label, value: c.value, unit: t.unit })),
          ...(t.typical ? [{ label: "Usual range", value: `${fmt(t.typical.low, t.unit, cur)} – ${fmt(t.typical.high, t.unit, cur)}` }] : []),
        ]} />
      ) : null}
      {t.text ? <p className="ins-mut">{t.text}</p> : null}
    </>
  );
}

function AiText({ text }) {
  const lines = String(text || "").split("\n").map((l) => l.trim()).filter(Boolean);
  const intro = lines.filter((l) => !/^[-•*]\s+/.test(l));
  const bullets = lines.filter((l) => /^[-•*]\s+/.test(l)).map((l) => l.replace(/^[-•*]\s+/, ""));
  return (
    <>
      {intro.map((l) => <p key={l} className="dw-p">{l.replace(/\*\*/g, "")}</p>)}
      {bullets.length ? <ul className="dw-steps dw-plain">{bullets.map((l) => <li key={l}>{l.replace(/\*\*/g, "")}</li>)}</ul> : null}
    </>
  );
}
