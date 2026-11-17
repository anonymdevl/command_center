import React, { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useApi } from "../useApi.js";
import ExportButton from "./ExportButton.jsx";
import { DrawerHead, useDrawer } from "./Drawer.jsx";
import { Loading, Failed, Empty } from "./States.jsx";
import { exact, count, shortDate } from "../format.js";
import { AiNote, InsightBody, Sec, STATUS_TONE, Tiles, TrendBody, fmt, hasTrend } from "./Understanding.jsx";

/**
 * What is behind a figure, as something to decide on -- the one drawer every card,
 * tile, panel row, Home list, work row and analyst answer opens.
 *
 * This replaces the lineage drawer, which listed an invoice code, an internal row
 * id and a timestamp. That proved the figure traced back to a document -- the
 * engineering requirement -- and told a manager nothing. Opening "Invoiced revenue"
 * and finding a hundred rows of codes is worse than not offering the drawer at all,
 * because it looks like the answer and is not.
 *
 * One frame, in the order a decision needs it:
 *
 *   The header.  Where it was opened from, its title, Explain This, Excel, close --
 *                solid, so the rows never show through it.
 *   The hero.    The figure, its status, when it was read, and one sentence: what is
 *                going on and what clears most of it.
 *   Insight.     For a figure of the KPI engine, its explanation (Understanding.jsx);
 *                for any other set of records, a summary worked out here from the
 *                records themselves -- count, total, where the weight sits, the oldest.
 *   Records.     Largest first, in business columns, searchable and sortable, each
 *                opening the actual document in ERPNext.
 *   Trend.       Only when the figure has a series.
 */
const LIMIT = 500;
const TAB_KEY = "cc-drawer-tab";

export default function Records({ scope, title, fact, filters, subset, explainedBy, openDrawer,
                                  kpi = null, figure = null, href = null }) {
  const drawer = useDrawer();
  const recs = useApi(
    () => api.records({ fact, filters, business_code: scope, limit: LIMIT }),
    [scope, fact, JSON.stringify(filters)], { skip: !fact }
  );
  const ins = useApi(
    ({ signal } = {}) => api.insight({ key: kpi, business_code: scope }, { signal }),
    [kpi, scope], { skip: !kpi }
  );
  const data = recs.data;
  const s = ins.data;
  const [ai, setAi] = useState({ busy: false, text: null, error: null });
  const [tab, setTab] = useState(readTab);

  const tabs = [
    ["insight", "Insight"],
    fact ? ["records", data ? `Records · ${count(data.summary.count)}` : "Records"] : null,
    kpi && hasTrend(s) ? ["trend", "Trend"] : null,
  ].filter(Boolean);
  const current = tabs.some(([k]) => k === tab) ? tab : "insight";
  const choose = (k) => {
    setTab(k);
    saveTab(k);
  };

  // Explain This: for a figure, the analyst on the drawer's own numbers (api/insight);
  // for any other set of records, the question goes to the analyst in the bar -- the
  // same path as every "Ask AI about this" on the screens.
  const explain = async () => {
    if (!kpi) {
      drawer.onClose?.();
      window.dispatchEvent(new CustomEvent("cc-ask", { detail: {
        question: `${title}: what stands out in these records, and what should we do about it?`,
      } }));
      return;
    }
    choose("insight");
    setAi({ busy: true, text: null, error: null });
    try {
      const got = await api.insightExplain({ key: kpi, business_code: scope });
      setAi({ busy: false, text: got?.text || null, error: got?.error || null });
    } catch (e) {
      setAi({ busy: false, text: null, error: e?.message || "The explanation could not be written." });
    }
  };

  const actions = (
    <>
      <button type="button" className="dw-btn" onClick={explain} disabled={ai.busy}
              title={kpi ? "Ask the analyst for a short management explanation of these figures"
                         : "Ask the analyst what stands out in these records"}>
        {ai.busy ? "Explaining…" : "Explain This"}
      </button>
      {fact && data && data.summary.count > 0 ? (
        // Every matching record, not just the ones shown here.
        <ExportButton className="dw-btn" label="Excel"
                      title={`Download all ${count(data.summary.count)} records behind this figure as an Excel sheet`}
                      run={() => api.recordsXlsx({ fact, filters, business_code: scope, title, kpi })} />
      ) : kpi && !fact ? (
        <ExportButton className="dw-btn" label="Excel" title="Download this explanation as an Excel sheet"
                      run={() => api.insightXlsx({ key: kpi, business_code: scope })} />
      ) : null}
    </>
  );

  const fig = s?.figure || figure;
  const cur = s?.currency || data?.currency || fig?.currency || "";
  return (
    <>
      <DrawerHead title={title} actions={actions} />
      <Hero kpi={kpi} fig={fig} s={s} data={data} cur={cur} subset={subset}
            loading={(kpi ? ins.loading && !s : false) || (fact ? recs.loading && !data : false)} />
      <div className="dw-tabs" role="tablist" aria-label="What this drawer shows">
        {tabs.map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={current === k}
                  className={`dw-tab${current === k ? " on" : ""}`} onClick={() => choose(k)}>
            {label}
          </button>
        ))}
      </div>

      <div className="dw-pane" role="tabpanel">
        {current === "insight" ? (
          <>
            <AiNote ai={ai} />
            {kpi ? (
              ins.loading && !s ? <div className="dw-sec"><Loading what="Working out what is behind this figure" /></div>
              : ins.error ? <div className="dw-sec"><Failed error={ins.error} onRetry={ins.reload} what="the explanation" /></div>
              : s ? (
                <InsightBody s={s} scope={scope} openDrawer={openDrawer} href={href}
                             tiles={data ? summaryTiles(data) : null}
                             extra={<RecordsInsight data={data} scope={scope} filters={filters}
                                                    explainedBy={explainedBy} openDrawer={openDrawer} />} />
              ) : null
            ) : (
              <>
                {recs.loading && !data ? <div className="dw-sec"><Loading what="Reading the records" /></div> : null}
                {recs.error ? <div className="dw-sec"><Failed error={recs.error} onRetry={recs.reload} what="the records" /></div> : null}
                {data && data.summary.count === 0 ? <div className="dw-sec"><Empty>Nothing matches this figure.</Empty></div> : null}
                {data && data.summary.count > 0 ? (
                  <>
                    <Sec><Tiles tiles={summaryTiles(data)} /></Sec>
                    <RecordsInsight data={data} scope={scope} filters={filters}
                                    explainedBy={explainedBy} openDrawer={openDrawer} />
                  </>
                ) : null}
              </>
            )}
          </>
        ) : null}

        {current === "records" ? (
          <>
            {recs.loading && !data ? <div className="dw-sec"><Loading what="Reading the records" /></div> : null}
            {recs.error ? <div className="dw-sec"><Failed error={recs.error} onRetry={recs.reload} what="the records" /></div> : null}
            {data && data.summary.count === 0 ? <div className="dw-sec"><Empty>Nothing matches this figure.</Empty></div> : null}
            {data && data.summary.count > 0 ? <RecordsTable data={data} /> : null}
          </>
        ) : null}

        {current === "trend" && s ? <TrendBody s={s} /> : null}
      </div>
    </>
  );
}
Records.ownsHeader = true;

function readTab() {
  try {
    return window.sessionStorage.getItem(TAB_KEY) || "insight";
  } catch {
    return "insight";
  }
}

function saveTab(k) {
  try {
    window.sessionStorage.setItem(TAB_KEY, k);
  } catch {
    /* a private window: the tab is simply not remembered */
  }
}

/* ------------------------------------------------------------------------- */

/** The figure, its status, when it was read, and the one sentence. */
function Hero({ kpi, fig, s, data, cur, subset, loading }) {
  const sm = data?.summary;
  const measureCol = data ? data.columns.find((c) => c.key === sm.measure) : null;
  const isMoney = !measureCol || measureCol.type === "currency";
  let big = "—";
  let eyebrow = null;
  if (kpi && fig) {
    big = fmt(fig.value, fig.unit, fig.currency || cur);
  } else if (sm) {
    big = isMoney ? `${cur} ${exact(sm.total)}`.trim() : `${count(sm.count)} ${nouns(data, sm.count)}`;
    eyebrow = isMoney ? cap(sm.measure_word) : null;
  }
  const asOf = (kpi ? fig?.as_of : null) || sm?.as_of || null;
  const read = readAt(asOf);
  const asAt = asOf?.date && asOf.basis === "the latest date the data covers" ? `As at ${shortDate(asOf.date)}` : null;
  const status = kpi ? s?.status : null;
  const say = kpi ? s?.headline || s?.what?.text || null : data ? summarySentence(data) : null;
  return (
    <section className="dw-hero">
      <div className="dw-hero-fig">
        {eyebrow ? <div className="dw-lab">{eyebrow}</div> : null}
        <div className="dw-big" title={big}>{big}</div>
        {subset ? <div className="dw-note">A subset of {subset}</div> : null}
        <div className="dw-chips">
          {status ? <span className={`dw-chip ${STATUS_TONE[status.state] || ""}`}>{status.label}</span> : null}
          {read ? <span className="dw-chip">{read}</span> : null}
          {asAt ? <span className="dw-chip" title="The latest date the data covers">{asAt}</span> : null}
        </div>
      </div>
      <p className="dw-say">{say || (loading ? "Reading…" : null)}</p>
    </section>
  );
}

/** "Read from ERPNext at 14:32", from a figure's or a load's as-of. */
function readAt(asOf) {
  if (!asOf) return null;
  const live = /^read from ERPNext at (.+)$/.exec(asOf.basis || "");
  if (live) return `Read from ERPNext at ${live[1]}`;
  if (!asOf.last_read) return null;
  const d = new Date(String(asOf.last_read).replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return null;
  const hm = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === new Date().toDateString()
    ? `Read from ERPNext at ${hm}`
    : `Read from ERPNext on ${d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })} at ${hm}`;
}

/** Title Case for a label built from the server's words ("still to deliver"). */
const cap = (t) => (t ? String(t).replace(/(^|\s)(\S)/g, (m, sp, c) => sp + c.toUpperCase()) : t);
const nouns = (data, n) => (n === 1 ? data.noun : `${data.noun}s`);
/** Money for a sentence or a tile: GHS 10.07M, GHS 341,565 (the table keeps the cents). */
const compact = (n, cur) => {
  const v = Number(n) || 0;
  const body = Math.abs(v) >= 1e6 ? `${exact(v / 1e6)}M` : exact(v, { decimals: 0 });
  return `${cur} ${body}`.trim();
};
/** The share the largest few hold, from the server's concentration over the whole set. */
const topShare = (sm, k) =>
  sm.total ? Math.round((1000 * sm.concentration.slice(0, k).reduce((a, c) => a + (c.value || 0), 0)) / sm.total) / 10 : null;

/** Where the measure column is money. */
function moneyMeasure(data) {
  const c = data.columns.find((x) => x.key === data.summary.measure);
  return !c || c.type === "currency";
}

/** The first date column and the lateness column, if the fact has them. */
const dateCol = (data) => data.columns.find((c) => c.type === "date");
const lateCol = (data) => data.columns.find((c) => LATE.has(c.key));
const nameOf = (data, r) => {
  const dim = DIMENSION_FIELD[data.fact];
  const doc = data.columns.find((c) => c.type === "doc");
  return [dim && r[dim], doc && r[doc.key]].filter((x, i, a) => x && a.indexOf(x) === i).join(" · ") || "—";
};

/**
 * The sentence for a drawer with no explanation of its own, from the numbers: how
 * many, how much, where the weight sits, and how late the latest-running is. A part
 * read from the rows shown says so when they are not the whole set.
 */
function summarySentence(data) {
  const sm = data.summary;
  if (!sm.count) return "Nothing matches this figure.";
  const cur = data.currency || "";
  const isMoney = moneyMeasure(data);
  const out = [
    `${count(sm.count)} ${nouns(data, sm.count)}, ${isMoney ? compact(sm.total, cur) : count(sm.total)} ${sm.measure_word}.`,
  ];
  const conc = sm.concentration || [];
  if (conc.length === 1 && sm.count > 1) {
    out.push(`All of it sits with one ${sm.dimension_word}, ${conc[0].label}.`);
  } else if (conc.length > 1) {
    const k = Math.min(3, conc.length);
    const share = topShare(sm, k);
    if (share != null) {
      out.push(`The top ${k} ${sm.dimension_word}s hold ${share}% of it; the largest is ${conc[0].label}${conc[0].share != null ? ` (${conc[0].share}%)` : ""}.`);
    }
  }
  const late = lateCol(data);
  if (late) {
    const rows = data.rows.filter((r) => Number(r[late.key]) > 0);
    if (rows.length) {
      const worst = rows.reduce((a, r) => (Number(r[late.key]) > Number(a[late.key]) ? r : a));
      const of = sm.shown < sm.count ? ` of the ${count(sm.shown)} largest shown` : "";
      out.push(`${count(rows.length)}${of} ${rows.length === 1 ? "is" : "are"} past due; the most overdue, ${nameOf(data, worst)}, is ${count(worst[late.key])} days late.`);
    }
  }
  return out.join(" ");
}

/** Up to four key numbers for a set of records. */
function summaryTiles(data) {
  const sm = data.summary;
  const cur = data.currency || "";
  const tiles = [
    { label: cap(`${data.noun}s`), value: count(sm.count),
      note: sm.shown < sm.count ? `${count(sm.shown)} largest shown` : null },
    { label: cap(sm.measure_word), value: moneyMeasure(data) ? compact(sm.total, cur) : count(sm.total),
      note: moneyMeasure(data) ? `${cur} ${exact(sm.total)}`.trim() : null },
  ];
  const conc = sm.concentration || [];
  if (conc.length > 1) {
    const k = Math.min(3, conc.length);
    tiles.push({ label: `Top ${k} Hold`, value: `${topShare(sm, k)}%`, note: `of ${count(sm.count)} ${nouns(data, sm.count)}` });
  }
  const dc = dateCol(data);
  const dated = dc ? data.rows.filter((r) => r[dc.key]) : [];
  if (dated.length) {
    const oldest = dated.reduce((a, r) => (String(r[dc.key]) < String(a[dc.key]) ? r : a));
    tiles.push({ label: `Earliest ${cap(dc.label)}${sm.shown < sm.count ? " Shown" : ""}`, value: shortDate(oldest[dc.key]),
                 note: nameOf(data, oldest) });
  } else if (data.rows.length) {
    const top = data.rows[0];
    tiles.push({ label: "Largest", value: moneyMeasure(data) ? compact(top[sm.measure], cur) : count(top[sm.measure]),
                 note: nameOf(data, top) });
  }
  return tiles.slice(0, 4);
}

/** What the records add to any drawer's Insight tab: what covers it, where it sits. */
function RecordsInsight({ data, scope, filters, explainedBy, openDrawer }) {
  return (
    <>
      {explainedBy && explainedBy.startsWith("order_cover") ? (
        <CoverSplit scope={scope} lateOnly={explainedBy === "order_cover_late"} />
      ) : null}
      {data && data.summary.count > 0 ? (
        <Concentration data={data} scope={scope} filters={filters} openDrawer={openDrawer} />
      ) : null}
      {data && data.rows.length > 1 ? <Largest data={data} /> : null}
      {data && data.summary.count > 0 ? (
        <p className="dw-note dw-pad">
          Each record opens the document in ERPNext, where the full history, attachments and
          comments live — this platform reports on it rather than replacing it.
        </p>
      ) : null}
    </>
  );
}

/**
 * Where the weight sits, over the whole set (the server's concentration).
 *
 * Each row is openable, so "who are those five" is one click rather than a question
 * the manager has to take somewhere else.
 */
function Concentration({ data, scope, filters, openDrawer }) {
  const s = data.summary;
  // One name holding all of it is said in the sentence; a single bar adds nothing.
  if (s.concentration.length < 2) return null;
  const dimension = DIMENSION_FIELD[data.fact];
  const most = Math.max(...s.concentration.map((c) => Math.abs(c.value || 0)), 0) || 1;
  const isMoney = moneyMeasure(data);
  const open = dimension && openDrawer
    ? (c) => openDrawer(
        <Records scope={scope} fact={data.fact} filters={{ ...(filters || {}), [dimension]: c.label }}
                 title={c.label} openDrawer={openDrawer} />)
    : null;
  return (
    <Sec title="Where It Is Concentrated">
      <p className="dw-note dw-note-top">
        The {s.concentration.length} largest by {s.dimension_word}, over all {count(s.count)} {nouns(data, s.count)}
        {open ? "; each opens its own records" : ""}.
      </p>
      <div className="dw-bars">
        {s.concentration.map((c) => (
          <button key={c.label} type="button" className="dw-bar dw-bar-link" disabled={!open}
                  onClick={open ? () => open(c) : undefined}
                  title={open ? `Open the records of ${c.label}` : c.label}>
            <span className="dw-bar-l">{c.label}</span>
            <span className="dw-bar-t" aria-hidden="true">
              <i className="dw-b-start" style={{ width: `${Math.max(1, (100 * Math.abs(c.value || 0)) / most)}%` }} />
            </span>
            <span className="dw-bar-v">
              {isMoney ? exact(c.value) : count(c.value)}
              <small>{c.share == null ? "—" : `${c.share}%`} · {count(c.count)}</small>
            </span>
          </button>
        ))}
      </div>
    </Sec>
  );
}

/**
 * The biggest single documents, as a short list -- not bars, which made it look like a
 * second "Where It Is Concentrated" (17 Nov 2026). That section totals by customer,
 * supplier or warehouse; this one names the individual documents to open first: number,
 * whose, when, how much. Left out when it would only repeat the concentration (each of
 * those names holds exactly one record).
 */
function Largest({ data }) {
  // The amount column: the server names it; else the first money column.
  const m = data.summary.measure || data.columns.find((c) => c.type === "currency")?.key;
  if (!m) return null;
  const top = [...data.rows].sort((a, b) => (Number(b[m]) || 0) - (Number(a[m]) || 0)).slice(0, 5);
  const dim = DIMENSION_FIELD[data.fact];
  const conc = data.summary.concentration || [];
  const repeats = dim && conc.length > 1
    && top.every((r) => conc.some((c) => c.label === r[dim] && c.count === 1));
  if (repeats) return null;
  const doc = data.columns.find((c) => c.type === "doc");
  const dc = dateCol(data);
  const isMoney = moneyMeasure(data);
  return (
    <Sec title={`Biggest Single ${cap(nouns(data, 2))}`}>
      <p className="dw-note dw-note-top">
        Individual {nouns(data, 2)}, largest first{dim ? ` — not totals by ${data.summary.dimension_word}` : ""}.
      </p>
      <ol className="dw-list">
        {top.map((r, i) => {
          const name = (doc && r[doc.key]) || nameOf(data, r);
          const who = dim && r[dim] && r[dim] !== name ? r[dim] : null;
          const when = dc && r[dc.key] ? shortDate(r[dc.key]) : null;
          const body = (
            <>
              <span className="dw-list-t">
                <b>{name}</b>
                {who || when ? <small>{[who, when].filter(Boolean).join(" · ")}</small> : null}
              </span>
              <span className="dw-list-v">{isMoney ? exact(r[m]) : count(r[m])}</span>
            </>
          );
          return (
            <li key={`${r.src_name}-${i}`}>
              {r.open_url ? (
                <a className="dw-list-row" href={r.open_url} target="_blank" rel="noreferrer"
                   title={`Open ${r.src_doctype} ${r.src_name} in ERPNext`}>{body}</a>
              ) : <div className="dw-list-row">{body}</div>}
            </li>
          );
        })}
      </ol>
    </Sec>
  );
}

/**
 * What covers the promise (api/coverage.summary): how much can go from stock, is on
 * order, requested, or not ordered at all -- read line by line from ERPNext now, so the
 * total can differ a little from the figure, which comes from each order's delivered
 * percentage as last loaded. Promised Orders — Cover on Sales, Stock and Buying has the
 * lines.
 */
function CoverSplit({ scope, lateOnly }) {
  const { data, error, loading } = useApi(
    () => api.coverSummary({ business_code: scope, late_only: lateOnly }),
    [scope, lateOnly]
  );
  if (loading && !data) return <div className="dw-sec"><Loading what="Reading what covers it" /></div>;
  if (error || !data || data.kind !== "cover") {
    return (
      <Sec title="What Covers It">
        <p className="dw-note cv-split">
          {data && data.kind === "unreachable"
            ? "What covers it is not updated yet: the business's ERPNext is taking longer than usual to answer. It fills in as soon as it does."
            : "What covers it could not be read just now."}
        </p>
      </Sec>
    );
  }
  const s = data.summary;
  const cur = data.currency || "";
  const parts = (s.parts || []).filter((p) => Math.abs(p.value) >= 0.5);
  const total = parts.reduce((a, p) => a + p.value, 0) || 1;
  const most = Math.max(...parts.map((p) => Math.abs(p.value)), 0) || 1;
  return (
    <Sec title="What Covers It">
      <p className="dw-note">{count(s.lines)} lines on {count(s.orders)} orders, read from ERPNext now</p>
      <div className="dw-bars cv-split">
        {parts.map((p) => (
          <div key={p.key} className="dw-bar">
            <span className="dw-bar-l">{p.label}</span>
            <span className="dw-bar-t" aria-hidden="true">
              <i className="dw-b-start" style={{ width: `${Math.max(1, (100 * Math.abs(p.value)) / most)}%` }} />
            </span>
            <span className="dw-bar-v">{cur} {exact(p.value)}<small>{Math.round((100 * p.value) / total)}%</small></span>
          </div>
        ))}
      </div>
      <p className="dw-note">{data.note}</p>
    </Sec>
  );
}

/** Which field the concentration groups by, so clicking one can filter to it. */
const DIMENSION_FIELD = {
  fact_sales_invoice: "customer",
  fact_sales_invoice_line: "customer",
  fact_payment_allocation: "party",
  fact_purchase_invoice: "supplier",
  fact_purchase_invoice_line: "supplier",
  fact_stock_balance: "warehouse",
  fact_sales_order: "customer",
  fact_task: "assigned_to",
  fact_person: "department",
  fact_case: "customer",
  fact_party_balance: "party",
};

/** Columns that say how late something is, as of the data's own date. */
const LATE = new Set(["days_overdue", "days_late"]);

/* ------------------------------------------------------------------------- */
/**
 * The records. Columns and their order are the server's, so every drawer agrees. One
 * line per record: nothing wraps, long names are cut with the whole name on hover, the
 * header stays put inside the table's own scroll box, and money columns total.
 */
function RecordsTable({ data }) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState(null); // { key, dir: 1 | -1 }, null = largest first
  const cols = data.columns;
  const sm = data.summary;

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let out = data.rows.map((r, i) => ({ __key: `${r.src_name}-${i}`, ...r }));
    if (needle) {
      out = out.filter((r) => cols.some((c) => {
        const v = c.type === "date" ? `${r[c.key] || ""} ${shortDate(r[c.key]) || ""}` : r[c.key];
        return v != null && String(v).toLowerCase().includes(needle);
      }));
    }
    if (sort) {
      const col = cols.find((c) => c.key === sort.key);
      const numeric = col && !["text", "doc", "date"].includes(col.type);
      out = [...out].sort((a, b) => {
        const x = a[sort.key];
        const y = b[sort.key];
        if (x == null || x === "") return 1;
        if (y == null || y === "") return -1;
        const d = numeric ? Number(x) - Number(y) : String(x).localeCompare(String(y));
        return d * sort.dir;
      });
    }
    return out;
  }, [data, q, sort, cols]);

  const flip = (key) => {
    const col = cols.find((c) => c.key === key);
    const first = col && ["text", "doc", "date"].includes(col.type) ? 1 : -1;
    setSort((s) => (!s || s.key !== key ? { key, dir: first } : s.dir === first ? { key, dir: -first } : null));
  };
  const right = (c) => !["text", "doc", "date"].includes(c.type) && !LATE.has(c.key) && c.key !== "status";
  const whole = !q.trim() && sm.shown === sm.count;

  return (
    <div className="dw-sec dw-recs">
      <div className="dw-tbar">
        <input type="search" className="dw-search" value={q} onChange={(e) => setQ(e.target.value)}
               placeholder={`Search ${sm.dimension_word} or ${data.noun}`}
               aria-label="Search these records" />
        <span className="dw-note">
          {q.trim() ? `${count(rows.length)} of ${count(sm.shown)} shown match`
            : sm.shown < sm.count ? `The ${count(sm.shown)} largest of ${count(sm.count)}`
            : `All ${count(sm.count)}`}
        </span>
      </div>
      <div className="dw-tbox">
        <table className="dt dw-t">
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c.key} className={right(c) ? "num" : undefined}
                    aria-sort={sort?.key === c.key ? (sort.dir > 0 ? "ascending" : "descending") : "none"}>
                  <button type="button" className="md-sort" onClick={() => flip(c.key)}
                          title={`Sort by ${c.label.toLowerCase()}`}>{c.label}</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.__key}>
                {cols.map((c) => (
                  <td key={c.key} className={right(c) ? "num" : c.type === "text" ? "dw-name" : undefined}>
                    {cell(r, c)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {rows.length ? (
            <tfoot>
              <tr>
                {cols.map((c, i) => (
                  <td key={c.key} className={right(c) ? "num" : undefined}>
                    {c.type === "currency"
                      ? exact(rows.reduce((a, r) => a + (Number(r[c.key]) || 0), 0))
                      : i === 0
                        ? (whole ? `${count(sm.count)} ${nouns(data, sm.count)}` : `${count(rows.length)} shown`)
                        : ""}
                  </td>
                ))}
              </tr>
            </tfoot>
          ) : null}
        </table>
        {!rows.length ? <div className="thin">Nothing shown matches “{q}”.</div> : null}
      </div>
      <p className="dw-note">
        {whole
          ? "Every record behind it. "
          : sm.shown < sm.count
            ? `The ${count(sm.shown)} largest of ${count(sm.count)}; Excel has every one. `
            : ""}
        Each row opens the document in ERPNext, where the full history, attachments and
        comments live — this platform reports on it rather than replacing it.
      </p>
    </div>
  );
}

/** One cell, formatted by the type the server declared. */
function cell(row, column) {
  const v = row[column.key];

  if (column.type === "doc") {
    return row.open_url ? (
      <a
        className="dlink"
        href={row.open_url}
        target="_blank"
        rel="noreferrer"
        onClick={(e) => e.stopPropagation()}
        title={`Open ${row.src_doctype} ${row.src_name} in ERPNext`}
      >
        {v} ↗
      </a>
    ) : (
      v || "—"
    );
  }

  if (v === null || v === undefined || v === "") return "—";
  if (column.type === "currency") return exact(v);
  if (column.type === "percent") return `${Number(v).toFixed(1)}%`;
  if (column.type === "number") return count(v);
  if (column.type === "date") return shortDate(v) || "—";
  if (LATE.has(column.key)) return <Late n={Number(v)} />;
  if (column.type === "days") {
    // Zero days is not the same as no answer, and neither is a negative number.
    const n = Number(v);
    if (n < 0) return `${count(Math.abs(n))} early`;
    return count(n);
  }
  if (column.key === "status") {
    return <span className={`dw-pill ${statusTone(v)}`}>{String(v)}</span>;
  }
  return <span className="dw-clip" title={String(v)}>{String(v)}</span>;
}

/** How late, as of the data's own date: "112 Days Late", "Due In 9 Days". */
function Late({ n }) {
  if (n > 0) {
    return (
      <span className={`dw-pill ${n > 30 ? "dw-c-crit" : "dw-c-high"}`}>
        {count(n)} {n === 1 ? "Day" : "Days"} Late
      </span>
    );
  }
  if (n < 0) return <span className="dw-pill">Due In {count(-n)} {n === -1 ? "Day" : "Days"}</span>;
  return <span className="dw-pill">Due Today</span>;
}

/** A status as the business's ERPNext states it, toned only where the word is plain. */
function statusTone(v) {
  const t = String(v).toLowerCase();
  if (/overdue|late|cancel|reject|lost/.test(t)) return "dw-c-crit";
  if (/^(completed|closed|resolved|paid|delivered|active)$/.test(t)) return "dw-c-ok";
  if (/hold|pending|waiting|replied/.test(t)) return "dw-c-high";
  return "";
}
