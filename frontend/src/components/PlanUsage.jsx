import React, { useState } from "react";
import { boot, brand } from "../api/boot.js";
import { plansApi } from "../api/client.js";
import { useApi } from "../useApi.js";
import { Failed, Loading } from "./States.jsx";
import { Dialog, Msg, act } from "./SettingsParts.jsx";
import "../styles/settings.css";
import "../styles/plans.css";

/**
 * Plan & Usage: the plan the organisation bought, what it includes, the licence, and
 * this month's use against the allowance -- counts only, never money
 * (insights/core/plans.py my_plan). For the customer's Account Managers; the plan badge
 * in the sidebar opens it. View Plans compares every tier by what it includes, and
 * Request a Quotation asks the vendor. Not a designed screen, so not in views.json.
 */
export default function PlanUsage() {
  const [clientId, setClientId] = useState(boot.plan?.client_id);
  const { data, error, loading, reload } = useApi(() => plansApi.mine(clientId), [clientId]);
  const [comparing, setComparing] = useState(false);
  const others = boot.plan?.others || [];

  if (loading && !data) return <Loading what="Reading your plan" />;
  if (error && !data) return <Failed error={error} onRetry={reload} what="your plan" />;
  const d = data;
  return (
    <div className="settings pl-page">
      <div className="topbar">
        <div>
          <h3>Plan &amp; Usage</h3>
          <div className="when">
            {d.client}&apos;s plan with {brand.product}: what it includes, the licence, and this
            month&apos;s use. The meters reset on {d.resets_on}.
          </div>
        </div>
        {others.length ? (
          <select className="pl-pick" aria-label="Organisation" value={clientId}
            onChange={(e) => setClientId(Number(e.target.value))}>
            <option value={boot.plan.client_id}>{boot.plan.client}</option>
            {others.map((o) => <option key={o.client_id} value={o.client_id}>{o.client}</option>)}
          </select>
        ) : null}
      </div>
      <div className="st-stack">
        <YourPlan d={d} onCompare={() => setComparing((c) => !c)} comparing={comparing} />
        <Usage d={d} clientId={clientId} />
        {comparing ? <ComparePlans current={d.plan.code} clientId={clientId} /> : null}
      </div>
    </div>
  );
}

function limitWords(n) {
  if (n === null || n === undefined) return "Unlimited";
  return `${n.toLocaleString("en-GB")}`;
}

function YourPlan({ d, onCompare, comparing }) {
  const lic = d.licence;
  const tone = { active: "t-ok", due: "t-wt", grace: "t-wt", lapsed: "t-od" }[lic.state];
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>{d.plan.name} Plan</b>
          <span>{d.plan.summary}</span>
        </div>
        <button className="btn" onClick={onCompare} aria-expanded={comparing}>
          {comparing ? "Hide Plans" : "View Plans"}
        </button>
      </div>
      <div className="pl-grid">
        <dl className="st-facts">
          <dt>Licensed to</dt>
          <dd>{d.licensed_to}</dd>
          <dt>Licence</dt>
          <dd><span className={`tag ${tone}`}>{lic.label}</span></dd>
          {lic.start ? (<><dt>Started</dt><dd>{lic.start}</dd></>) : null}
          <dt>Renews</dt>
          <dd>
            {lic.no_expiry ? "No expiry date is set" : lic.renews}
            {!lic.no_expiry && lic.days_left >= 0 ? (
              <span className="st-sub">{lic.days_left === 0 ? "Today" : `${lic.days_left} days left`}</span>
            ) : null}
            {lic.state === "grace" ? <span className="st-sub">Grace period until {lic.grace_until}</span> : null}
          </dd>
          <dt>Businesses</dt>
          <dd>{d.businesses.length ? d.businesses.map((b) => b.name).join(", ") : "None assigned yet"}</dd>
          <dt>Data refresh</dt>
          <dd>{d.plan.refresh}</dd>
          <dt>Support</dt>
          <dd>{d.plan.support}</dd>
        </dl>
        <div>
          <div className="pl-label">What is included</div>
          <ul className="pl-feats">
            {d.plan.features.map((f) => <li key={f}>{f}</li>)}
          </ul>
        </div>
      </div>
      {d.banner ? <Msg tone={lic.state === "lapsed" ? "bad" : "note"}>{d.banner}</Msg> : null}
    </div>
  );
}

function Usage({ d, clientId }) {
  const [st, setSt] = useState({});
  const warn = d.meters.filter((m) => m.warn);
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>This Month&apos;s Usage</b>
          <span>{d.period_label} · resets on {d.resets_on}</span>
        </div>
        <div className="st-acts">
          <button className="btn" disabled={st.busy}
            onClick={() => act(setSt, () => plansApi.statementPdf(clientId, d.period))}>Download PDF</button>
          <button className="btn" disabled={st.busy}
            onClick={() => act(setSt, () => plansApi.statementXlsx(clientId, d.period))}>Download Excel</button>
        </div>
      </div>
      {warn.length ? (
        <Msg tone={warn.some((m) => m.full) ? "bad" : "note"}>
          {warn.map((m) => `${m.label}: ${m.used.toLocaleString("en-GB")} of ${m.included.toLocaleString("en-GB")} used`).join(" · ")}.{" "}
          {d.allow_overage
            ? "Use beyond the allowance keeps working and is recorded as additional usage."
            : "When an allowance is used up, the AI features pause until the meters reset; your administrator can extend it."}
        </Msg>
      ) : null}
      <div className="pl-meters">
        {d.meters.map((m) => <Meter key={m.key} m={m} />)}
      </div>
      <p className="st-sub pl-foot">
        Counts only. Meters count from 00:00 on the 1st of each month, server time; seats and
        businesses are the most in use on any day. The statement downloads list the same counts.
      </p>
      <Msg tone="bad">{st.bad}</Msg>
    </div>
  );
}

function Meter({ m }) {
  const pct = m.pct === null ? null : Math.min(100, m.pct);
  const tone = m.full ? " pl-full" : m.warn ? " pl-warn" : "";
  return (
    <div className={`pl-meter${tone}`}>
      <div className="pl-meter-h">
        <b>{m.label}</b>
        <span>
          {m.used.toLocaleString("en-GB")}
          {m.included === null ? " · Unlimited" : ` of ${m.included.toLocaleString("en-GB")}`}
        </span>
      </div>
      <div className="pl-bar" aria-hidden="true">
        <i style={{ width: `${pct === null ? 0 : pct}%` }} />
      </div>
      <span className="st-sub">
        {m.included === null
          ? `No limit · ${m.measured}`
          : m.over
            ? `${m.over.toLocaleString("en-GB")} beyond the allowance · ${m.measured}`
            : `${m.remaining.toLocaleString("en-GB")} left · ${m.measured}`}
      </span>
    </div>
  );
}

function ComparePlans({ current, clientId }) {
  const { data, error, loading, reload } = useApi(() => plansApi.tiers(), []);
  const [asking, setAsking] = useState(null);
  if (loading && !data) return <Loading what="Reading the plans" />;
  if (error && !data) return <Failed error={error} onRetry={reload} what="the plans" />;
  const tiers = data.plans;
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Plans</b>
          <span>What each plan includes. Prices are set out in a quotation for your organisation.</span>
        </div>
      </div>
      <div className="pl-compare-w">
        <table className="dt pl-compare">
          <thead>
            <tr>
              <th aria-label="Included" />
              {tiers.map((p) => (
                <th key={p.code} className={p.code === current ? "on" : ""}>
                  {p.name}
                  {p.code === current ? <span className="st-sub">Your plan</span> : null}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="st-dim">For</td>
              {tiers.map((p) => <td key={p.code}>{p.summary}</td>)}
            </tr>
            {data.meters.map((m) => (
              <tr key={m.key}>
                <td className="st-dim">{m.label}{m.key === "seats" || m.key === "businesses" ? "" : " / Month"}</td>
                {tiers.map((p) => <td key={p.code}>{limitWords(p.limits[m.key])}</td>)}
              </tr>
            ))}
            <tr>
              <td className="st-dim">Data refresh</td>
              {tiers.map((p) => <td key={p.code}>{p.refresh}</td>)}
            </tr>
            <tr>
              <td className="st-dim">Support</td>
              {tiers.map((p) => <td key={p.code}>{p.support}</td>)}
            </tr>
            <tr>
              <td className="st-dim">Features</td>
              {tiers.map((p) => (
                <td key={p.code}>
                  <ul className="pl-feats sm">{p.features.map((f) => <li key={f}>{f}</li>)}</ul>
                </td>
              ))}
            </tr>
            <tr>
              <td />
              {tiers.map((p) => (
                <td key={p.code}>
                  <button className={`btn${p.code === current ? "" : " pri"}`} onClick={() => setAsking(p)}>
                    Request a Quotation
                  </button>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      {asking ? (
        <RequestQuote plan={asking} clientId={clientId} vendor={data.vendor} canEmail={data.can_email}
          onClose={() => setAsking(null)} />
      ) : null}
    </div>
  );
}

function Contact({ v }) {
  return (
    <dl className="st-facts" style={{ marginTop: 12 }}>
      <dt>Company</dt>
      <dd>{v.company}</dd>
      {v.person ? (<><dt>Contact</dt><dd>{v.person}</dd></>) : null}
      {v.email ? (<><dt>Email</dt><dd><a href={`mailto:${v.email}`}>{v.email}</a></dd></>) : null}
      {v.phone ? (<><dt>Phone</dt><dd>{v.phone}</dd></>) : null}
      {v.website ? (<><dt>Website</dt><dd>{v.website}</dd></>) : null}
    </dl>
  );
}

function RequestQuote({ plan, clientId, vendor, canEmail, onClose }) {
  const [message, setMessage] = useState("");
  const [st, setSt] = useState({});
  const [out, setOut] = useState(null);
  if (out && !out.sent) {
    return (
      <Dialog title="Request Recorded" onClose={onClose}
        sub={`Your request for a quotation for the ${plan.name} plan was recorded for ${vendor.company}. The platform cannot send email yet, so to hear back sooner, contact them directly:`}>
        <Contact v={out?.contact || vendor} />
        <div className="dlg-acts">
          <button type="button" className="ap-act pri" onClick={onClose}>Done</button>
        </div>
      </Dialog>
    );
  }
  if (out?.sent) {
    return (
      <Dialog title="Request Sent" onClose={onClose}
        sub={`Your request for a quotation for the ${plan.name} plan was sent to ${vendor.company} (${out.to}). They will reply to you directly.`}>
        <div className="dlg-acts">
          <button type="button" className="ap-act pri" onClick={onClose}>Done</button>
        </div>
      </Dialog>
    );
  }
  const send = async (e) => {
    e.preventDefault();
    const got = await act(setSt, () => plansApi.requestQuote({ plan: plan.code, message, client_id: clientId }));
    if (got) setOut(got);
  };
  return (
    <Dialog title="Request a Quotation"
      sub={`Ask ${vendor.company} for a quotation for the ${plan.name} plan. Your name and email are included so they can reply to you.${canEmail ? "" : " Email is not set up on the platform, so the request is recorded for them and their contact details are shown next."}`}
      onClose={onClose}>
      <form onSubmit={send}>
        <label htmlFor="pl-msg">Message (optional)</label>
        <textarea id="pl-msg" className="pl-text" rows={4} maxLength={1500} value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="For example, how many people and businesses you expect." />
        <Msg tone="bad">{st.bad}</Msg>
        <div className="dlg-acts">
          <button type="button" className="ap-act" onClick={onClose}>Cancel</button>
          <button type="submit" className="ap-act pri" disabled={st.busy}>
            {st.busy ? "Sending…" : "Send Request"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
