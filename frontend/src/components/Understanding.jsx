import React, { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import { useApi } from "../useApi.js";
import Records from "./Records.jsx";
import ExportButton from "./ExportButton.jsx";
import { Loading, Failed } from "./States.jsx";
import { exact, count } from "../format.js";
import { chartModel } from "../legacy/charts.js";
import { createViz } from "../legacy/viz.js";
import "../styles/insight.css";

/**
 * "Understanding This Figure": the top of every figure's drawer (api/insight.py).
 *
 * The records alone present the data; this says what the figure is and how it is worked
 * out, what it should look like, what is driving it now (with the reconciliation bridge
 * for receivables and payables), what to do about it in ERPNext, how to stop it
 * recurring, and the related figures -- every number computed on the server, nothing
 * written here. Explain This asks the analyst for a short management explanation of
 * the same numbers; the section stands on its own without it.
 */
export default function Understanding({ figureKey, scope, openDrawer }) {
  const { data, error, loading, reload } = useApi(
    ({ signal } = {}) => api.insight({ key: figureKey, business_code: scope }, { signal }),
    [figureKey, scope]
  );
  if (loading && !data) return <Loading what="Working out what is behind this figure" />;
  if (error) return <Failed error={error} onRetry={reload} what="the explanation" />;
  if (!data) return null;
  return <Section s={data} scope={scope} openDrawer={openDrawer} />;
}

/** The drawer a figure opens: its explanation, then its records (or its ERPNext list). */
export function FigureDrawer({ figure, scope, openDrawer }) {
  if (figure?.drill?.fact) {
    return (
      <Records scope={scope} kpi={figure.key} fact={figure.drill.fact}
               filters={figure.drill.filters} title={figure.label} subset={figure.subset_of}
               explainedBy={figure.explained_by} openDrawer={openDrawer} />
    );
  }
  return (
    <>
      <div className="dhead">
        <div>
          <div className="dt">What is behind it</div>
          <h4>{figure.label}</h4>
          {figure.subset_of ? <div className="when">a subset of {figure.subset_of}</div> : null}
        </div>
        <ExportButton label="Excel" title="Download this explanation as an Excel sheet"
                      run={() => api.insightXlsx({ key: figure.key, business_code: scope })} />
      </div>
      <Understanding figureKey={figure.key} scope={scope} openDrawer={openDrawer} />
      {figure.drill?.href ? (
        <p className="ins-foot">
          <a className="btn" href={figure.drill.href} target="_blank" rel="noreferrer">
            Open the records in ERPNext ↗
          </a>
        </p>
      ) : null}
    </>
  );
}

/* ------------------------------------------------------------------------- */
function Section({ s, scope, openDrawer }) {
  const cur = s.currency || "";
  const d = s.diagnosis;
  return (
    <section className="ins" aria-label="Understanding this figure">
      <div className="ins-top">
        <span className="ins-eyebrow">Understanding this figure</span>
        <Explain figureKey={s.key} scope={scope} />
      </div>

      <Part title="What it is">
        <p>{s.what.text}</p>
        <p className="ins-mut">{s.what.how}</p>
        {s.as_of?.date ? <p className="ins-mut">As at {s.as_of.date}, {s.as_of.basis}.</p> : null}
      </Part>

      {s.guide ? (
        <Part title="Nothing recorded yet">
          <Guide g={s.guide} />
        </Part>
      ) : null}

      <Part title="What it should look like">
        <p>{s.expected.text}</p>
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
      </Part>

      {d ? (
        <Part title="What is driving it now">
          {d.chips?.length ? <Chips chips={d.chips} cur={cur} /> : null}
          {(d.sentences || []).map((t) => <p key={t}>{t}</p>)}
          {d.bridge ? <Bridge b={d.bridge} cur={cur} /> : null}
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
        </Part>
      ) : null}

      {s.trend ? (
        <Part title="Its trend">
          <Trend t={s.trend} cur={cur} />
        </Part>
      ) : null}

      {s.link ? (
        <Part title="Where it is explained">
          <button type="button" className="btn" onClick={() => {
            window.closeDrawer?.();
            window.go?.(s.link.view);
          }}>{s.link.label}</button>
        </Part>
      ) : null}

      {s.resolution && (s.resolution.steps?.length || s.resolution.improve?.length) ? (
        <Part title={s.resolution.steps?.length ? "Recommended resolution" : "How to improve it"}>
          {s.resolution.owner || s.resolution.order ? (
            <div className="ins-meta">
              {s.resolution.owner ? <span><b>Owner</b> {s.resolution.owner}</span> : null}
              {s.resolution.order ? <span><b>Order</b> {s.resolution.order}</span> : null}
            </div>
          ) : null}
          {s.resolution.steps?.length ? (
            <ol className="ins-steps">{s.resolution.steps.map((t) => <li key={t}>{t}</li>)}</ol>
          ) : null}
          {s.resolution.improve?.length ? (
            <ul className="ins-list">
              {s.resolution.improve.map((x) => (
                <li key={x.text}>{x.text}{x.href ? <> <Ext href={x.href} label={x.label} /></> : null}</li>
              ))}
            </ul>
          ) : null}
          {s.resolution.guide?.href ? (
            <a className="btn ins-cta" href={s.resolution.guide.href} target="_blank" rel="noreferrer">
              {s.resolution.guide.label || "Open in ERPNext"} ↗
            </a>
          ) : null}
        </Part>
      ) : null}

      {s.prevention?.length ? (
        <Part title="Prevention">
          <ul className="ins-prev">
            {s.prevention.map((p) => (
              <li key={p.text} className={p.state ? `ins-${p.state}` : undefined}>
                {p.state ? <span className="ins-dot" aria-hidden="true" /> : null}
                <span>{p.text} {p.href ? <Ext href={p.href} label={p.label} /> : null}</span>
              </li>
            ))}
          </ul>
        </Part>
      ) : null}

      {s.related?.length || s.open_items?.length ? (
        <Part title="Related">
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
        </Part>
      ) : null}
      <div className="ins-rule"><span>The records behind it</span></div>
    </section>
  );
}

const STATE = { ok: "As expected", warn: "Needs attention", bad: "Off target", info: "For information" };
const KIND = { process: "Process", timing: "Timing", position: "Position", unexplained: "Unexplained" };

function Part({ title, children }) {
  return (
    <div className="ins-part">
      <h5>{title}</h5>
      {children}
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

function Bridge({ b, cur }) {
  const drawn = b.steps.filter((x) => x.kind === "total" || Math.abs(x.value) >= 0.005);
  const spec = {
    type: "waterfall", title: "From the open invoices to the ledger", unit: cur,
    labels: drawn.map((x) => short(x.label)),
    series: [{ name: cur, values: drawn.map((x) => x.value) }],
    totals: drawn.map((x, i) => (x.kind === "total" ? i : -1)).filter((i) => i >= 0),
  };
  return (
    <div className="ins-block">
      <h6>The reconciliation, step by step</h6>
      <Chart spec={spec} title="From the open invoices to the ledger" />
      <div className="ins-scroll">
        <table className="dt ins-t">
          <thead>
            <tr><th>Step</th><th>Kind</th><th style={{ textAlign: "right" }}>How many</th>
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
      <p className={`ins-mut ins-recon ${b.reconciles ? "ins-ok" : "ins-bad"}`}>
        {b.reconciles
          ? `Reconciles to the cent; ${cur} ${exact(b.unexplained)} is not explained by the records.`
          : `Does not reconcile: ${cur} ${exact(b.residual)} is left by the arithmetic.`}
      </p>
    </div>
  );
}

const short = (t) => (t.length > 26 ? `${t.slice(0, 24)}…` : t);

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
                <td>{r.party}</td>
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
                <td>{i.party}</td>
                <td>{i.date}</td>
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
                  return unit === "text" ? <td key={j}>{String(v)}</td>
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

/** Explain This: the analyst, on the drawer's own numbers only. */
function Explain({ figureKey, scope }) {
  const [state, setState] = useState({ busy: false, text: null, error: null });
  const run = async () => {
    setState({ busy: true, text: null, error: null });
    try {
      const got = await api.insightExplain({ key: figureKey, business_code: scope });
      setState({ busy: false, text: got?.text || null, error: got?.error || null, model: got?.model });
    } catch (e) {
      setState({ busy: false, text: null, error: e?.message || "The explanation could not be written." });
    }
  };
  return (
    <>
      <button type="button" className="btn ins-explain" onClick={run} disabled={state.busy}
              title="Ask the analyst for a short management explanation of these figures">
        {state.busy ? "Explaining…" : "Explain This"}
      </button>
      {state.text || state.error ? (
        <div className={`ins-ai${state.error ? " ins-ai-err" : ""}`} role="status">
          {state.error ? <p>{state.error}</p> : <AiText text={state.text} />}
          {state.text ? <p className="ins-mut">Written by the analyst from the figures in this drawer only; every number in it was checked against them.</p> : null}
        </div>
      ) : null}
    </>
  );
}

function AiText({ text }) {
  const lines = String(text || "").split("\n").map((l) => l.trim()).filter(Boolean);
  const intro = lines.filter((l) => !/^[-•*]\s+/.test(l));
  const bullets = lines.filter((l) => /^[-•*]\s+/.test(l)).map((l) => l.replace(/^[-•*]\s+/, ""));
  return (
    <>
      {intro.map((l) => <p key={l}>{l.replace(/\*\*/g, "")}</p>)}
      {bullets.length ? <ul>{bullets.map((l) => <li key={l}>{l.replace(/\*\*/g, "")}</li>)}</ul> : null}
    </>
  );
}
