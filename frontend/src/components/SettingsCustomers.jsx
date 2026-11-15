import React, { useEffect, useState } from "react";
import { plansApi } from "../api/client.js";
import { useApi } from "../useApi.js";
import { Failed, Loading } from "./States.jsx";
import { Dialog, Msg, act } from "./SettingsParts.jsx";
import "../styles/plans.css";

/**
 * Settings -> Customers (administrator only; never given to a delegate): every customer
 * with its plan, limits, licence, seats and this month's usage, its estimated Claude cost
 * and its statement; the plans themselves and the Claude price table
 * (insights/core/plans.py). Money is shown here and nowhere else. Nothing here sends
 * anything to a customer: a statement is for the administrator to review.
 */
const ROLE_WORDS = { manager: "Account Manager", user: "User" };
const TONE = { active: "t-ok", due: "t-wt", grace: "t-wt", lapsed: "t-od" };

function n(v) {
  return v === null || v === undefined ? "Unlimited" : Number(v).toLocaleString("en-GB");
}
function money(v, cur) {
  const s = Number(v || 0).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return cur ? `${cur} ${s}` : s;
}

export default function SettingsCustomers() {
  const { data, error, loading, reload } = useApi(() => plansApi.customers(), []);
  const [open, setOpen] = useState(null);
  const [adding, setAdding] = useState(false);
  const [stmt, setStmt] = useState(null);
  if (loading && !data) return <Loading what="Reading the customers" />;
  if (error && !data) return <Failed error={error} onRetry={reload} what="the customers" />;
  const rows = data.customers;
  const current = rows.find((r) => r.id === open);
  return (
    <div className="st-stack">
      <div className="panel">
        <div className="ph">
          <div>
            <b>Customers</b>
            <span>
              {rows.length} {rows.length === 1 ? "customer" : "customers"} · usage for {data.period_label},
              resetting on {data.resets_on} (server time)
            </span>
          </div>
          <button className="btn pri" onClick={() => setAdding(true)}>Add Customer</button>
        </div>
        {rows.length ? (
          <div className="pl-table-w">
            <table className="dt">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Plan</th>
                  <th>Licence</th>
                  <th className="pl-num">Seats</th>
                  <th className="pl-num">AI Questions</th>
                  <th className="pl-num">AI Reports</th>
                  <th className="pl-num">Est. Claude Cost</th>
                  <th className="pl-num">Statement</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => {
                  const m = Object.fromEntries(c.meters.map((x) => [x.key, x]));
                  return (
                    <tr key={c.id}>
                      <td>
                        {c.name}
                        <span className="st-sub">
                          Licensed to {c.licensed_to || c.name} · {c.businesses.map((b) => b.name).join(", ") || "no business yet"}
                        </span>
                      </td>
                      <td>{c.plan_name}</td>
                      <td>
                        <span className={`tag ${TONE[c.licence.state]}`}>{c.licence.label}</span>
                        <span className="st-sub">{c.licence.no_expiry ? "No expiry" : `Renews ${c.licence.renews}`}</span>
                      </td>
                      <td className="pl-num">{c.seats_used} / {n(c.limits.seats)}</td>
                      <td className="pl-num">{n(m.ai_questions.used)} / {n(m.ai_questions.included)}</td>
                      <td className="pl-num">{n(m.ai_reports.used)} / {n(m.ai_reports.included)}</td>
                      <td className="pl-num">
                        {money(c.statement.claude.cost, data.cost_currency)}
                        {c.statement.claude.unpriced ? <span className="st-sub">some calls unpriced</span> : null}
                      </td>
                      <td className="pl-num">{money(c.statement.total, c.statement.currency)}</td>
                      <td>
                        <div className="st-acts">
                          <button className="btn" onClick={() => setStmt(c)}>Statement</button>
                          <button className="btn" onClick={() => setOpen(c.id)}>Manage</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="st-dim">
            No customers yet. Add one to give a client a plan, a licence, seats and a monthly usage
            statement. Until then every business keeps working with no limits and no expiry.
          </p>
        )}
        {data.unassigned.length ? (
          <p className="st-sub">
            Not on a customer (no limits, no expiry): {data.unassigned.map((b) => b.business_name).join(", ")}.
          </p>
        ) : null}
      </div>
      <PlansPanel onSaved={reload} />
      <PricesPanel />
      {adding ? <CustomerForm data={data} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); reload(); }} /> : null}
      {current ? <CustomerForm data={data} c={current} onClose={() => setOpen(null)} onSaved={reload} /> : null}
      {stmt ? <Statement c={stmt} data={data} onClose={() => setStmt(null)} onChanged={reload} /> : null}
    </div>
  );
}

function CustomerForm({ data, c, onClose, onSaved }) {
  const [f, setF] = useState(() => ({
    name: c?.name || "", licensed_to: c?.licensed_to || "", plan: c?.plan || "essentials",
    licence_start: c?.licence_start || "", renewal_date: c?.renewal_date || "",
    grace_days: c?.grace_days ?? 30, allow_overage: c ? c.allow_overage : true,
    businesses: (c?.businesses || []).map((b) => b.code), notes: c?.notes || "",
    limits: Object.fromEntries(Object.entries(c?.overrides || {}).map(([k, v]) => [k, v === null ? "Unlimited" : String(v)])),
    currency: c?.own_rates?.currency || "", base_fee: c?.own_rates?.base_fee ?? "",
    overage: { ...(c?.own_rates?.overage || {}) },
  }));
  const [st, setSt] = useState({});
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const owned = new Set(data.customers.filter((x) => x.id !== c?.id).flatMap((x) => x.businesses.map((b) => b.code)));
  const save = async (e) => {
    e.preventDefault();
    const limits = Object.fromEntries(Object.entries(f.limits).filter(([, v]) => String(v).trim() !== ""));
    const overage = Object.fromEntries(Object.entries(f.overage).filter(([, v]) => String(v).trim() !== ""));
    const out = await act(setSt, () => plansApi.saveCustomer({
      id: c?.id, name: f.name, licensed_to: f.licensed_to, plan: f.plan, licence_start: f.licence_start,
      renewal_date: f.renewal_date, grace_days: f.grace_days, allow_overage: f.allow_overage ? 1 : 0,
      businesses: f.businesses, notes: f.notes, limits,
      rates: { currency: f.currency, base_fee: f.base_fee, overage },
    }), "Saved.");
    if (out) onSaved();
  };
  const plan = c && c.plan === f.plan ? c.limits : null;
  return (
    <Dialog title={c ? `Manage ${c.name}` : "Add Customer"} wide onClose={onClose}
      sub="A customer is one client: its businesses, its plan and licence, and the people who use the platform for it.">
      <form onSubmit={save}>
        <div className="st-form">
          <div>
            <label htmlFor="cu-name">Customer</label>
            <input id="cu-name" value={f.name} onChange={set("name")} maxLength={140} required />
          </div>
          <div>
            <label htmlFor="cu-lic">Licensed To</label>
            <input id="cu-lic" value={f.licensed_to} onChange={set("licensed_to")} maxLength={140}
              placeholder="The name on the licence" />
          </div>
          <div>
            <label htmlFor="cu-plan">Plan</label>
            <select id="cu-plan" value={f.plan} onChange={set("plan")}>
              {data.plans.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="cu-start">Licence Start</label>
            <input id="cu-start" type="date" value={f.licence_start || ""} onChange={set("licence_start")} />
          </div>
          <div>
            <label htmlFor="cu-end">Renewal Date</label>
            <input id="cu-end" type="date" value={f.renewal_date || ""} onChange={set("renewal_date")} />
            <span className="st-sub">Empty: no expiry.</span>
          </div>
          <div>
            <label htmlFor="cu-grace">Grace Period (Days)</label>
            <input id="cu-grace" type="number" min={0} max={365} value={f.grace_days} onChange={set("grace_days")} />
          </div>
        </div>
        <label className="st-check">
          <input type="checkbox" checked={f.allow_overage} onChange={set("allow_overage")} />
          Allow use beyond the AI allowance, recorded as additional usage
        </label>

        <div className="dlg-sec">
          <h4>Businesses</h4>
          <div className="pl-checks">
            {data.all_businesses.length ? data.all_businesses.map((b) => (
              <label key={b.business_code} className="st-check">
                <input type="checkbox" disabled={owned.has(b.business_code)}
                  checked={f.businesses.includes(b.business_code)}
                  onChange={(e) => setF((x) => ({ ...x, businesses: e.target.checked
                    ? [...x.businesses, b.business_code] : x.businesses.filter((y) => y !== b.business_code) }))} />
                {b.business_name}{owned.has(b.business_code) ? " (another customer)" : ""}
              </label>
            )) : <span className="st-dim">No business is connected yet.</span>}
          </div>
        </div>

        <div className="dlg-sec">
          <h4>Limits</h4>
          <p className="dlg-sub">Leave empty for the plan&apos;s own; type Unlimited for no limit.</p>
          <div className="pl-limits">
            {data.meters.map((m) => (
              <div key={m.key}>
                <label htmlFor={`cu-l-${m.key}`}>{m.label}</label>
                <input id={`cu-l-${m.key}`} className="pl-in sm" value={f.limits[m.key] ?? ""}
                  placeholder={plan ? `Plan: ${n(plan[m.key])}` : "Plan's"}
                  onChange={(e) => setF((x) => ({ ...x, limits: { ...x.limits, [m.key]: e.target.value } }))} />
              </div>
            ))}
          </div>
        </div>

        <div className="dlg-sec">
          <h4>Rates</h4>
          <p className="dlg-sub">Seen by the administrator only. Empty fields take the plan&apos;s default rates.</p>
          <div className="pl-limits">
            <div>
              <label htmlFor="cu-cur">Currency</label>
              <input id="cu-cur" className="pl-in sm" value={f.currency} onChange={set("currency")} maxLength={8}
                placeholder={c?.rates?.currency || "GHS"} />
            </div>
            <div>
              <label htmlFor="cu-base">Monthly Base Fee</label>
              <input id="cu-base" className="pl-in sm" inputMode="decimal" value={f.base_fee} onChange={set("base_fee")}
                placeholder={c ? String(c.rates.base_fee) : "0"} />
            </div>
            {data.meters.map((m) => (
              <div key={m.key}>
                <label htmlFor={`cu-r-${m.key}`}>{m.label}: Each Beyond</label>
                <input id={`cu-r-${m.key}`} className="pl-in sm" inputMode="decimal" value={f.overage[m.key] ?? ""}
                  placeholder={c ? String(c.rates.overage[m.key]) : "0"}
                  onChange={(e) => setF((x) => ({ ...x, overage: { ...x.overage, [m.key]: e.target.value } }))} />
              </div>
            ))}
          </div>
        </div>

        <div className="dlg-sec">
          <label htmlFor="cu-notes">Notes</label>
          <textarea id="cu-notes" className="pl-text" rows={2} value={f.notes} onChange={set("notes")} maxLength={2000} />
        </div>
        <Msg tone="ok">{st.ok}</Msg>
        <Msg tone="bad">{st.bad}</Msg>
        <div className="dlg-acts">
          <button type="button" className="ap-act" onClick={onClose}>Close</button>
          <button type="submit" className="ap-act pri" disabled={st.busy}>{st.busy ? "Saving…" : c ? "Save Changes" : "Add Customer"}</button>
        </div>
      </form>
      {c ? <Licence c={c} onSaved={onSaved} /> : null}
      {c ? <Members c={c} people={data.people} onSaved={onSaved} /> : null}
      {c ? <RemoveCustomer c={c} onDone={() => { onClose(); onSaved(); }} /> : null}
    </Dialog>
  );
}

function Licence({ c, onSaved }) {
  const [st, setSt] = useState({});
  const extend = async (days) => {
    const out = await act(setSt, () => plansApi.extend(c.id, days), (r) => `Renews ${r.licence.renews}.`);
    if (out) onSaved();
  };
  return (
    <div className="dlg-sec">
      <h4>Licence</h4>
      <p className="dlg-sub">
        <span className={`tag ${TONE[c.licence.state]}`}>{c.licence.label}</span>{" "}
        {c.licence.no_expiry ? "No expiry date is set." : `Renews ${c.licence.renews}; grace until ${c.licence.grace_until}.`}{" "}
        Extending takes effect at once, from the renewal date or from today if it has passed.
      </p>
      <div className="st-acts" style={{ justifyContent: "flex-start" }}>
        <button type="button" className="btn" disabled={st.busy} onClick={() => extend(30)}>Extend 30 Days</button>
        <button type="button" className="btn" disabled={st.busy} onClick={() => extend(365)}>Extend 1 Year</button>
      </div>
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>
    </div>
  );
}

function Members({ c, people, onSaved }) {
  const [f, setF] = useState({ username: "", role: "user", override: false });
  const [st, setSt] = useState({});
  const named = new Set(c.members.map((m) => m.username.toLowerCase()));
  const choices = people.filter((p) => !named.has(p.username.toLowerCase()));
  const run = async (args, ok) => {
    const out = await act(setSt, () => plansApi.setMember({ id: c.id, ...args }), ok);
    if (out) onSaved();
  };
  return (
    <div className="dlg-sec">
      <h4>People and Seats</h4>
      <p className="dlg-sub">
        {c.seats_used} of {n(c.limits.seats)} seats in use. Account Managers also see Plan &amp; Usage and its
        notices; Users see the plan badge only. People let in by the business&apos;s ERPNext count as Users.
      </p>
      {c.members.length ? (
        <table className="dt pl-members">
          <tbody>
            {c.members.map((m) => (
              <tr key={m.username}>
                <td>
                  {m.name}
                  <span className="st-sub">{m.username}{m.via === "erpnext" ? " · signed in with ERPNext" : ""}{!m.active ? " · deactivated" : ""}</span>
                </td>
                <td>{ROLE_WORDS[m.role]}</td>
                <td>
                  {m.via === "named" ? (
                    <div className="st-acts">
                      <button type="button" className="btn" disabled={st.busy}
                        onClick={() => run({ username: m.username, role: m.role === "manager" ? "user" : "manager" }, "Changed.")}>
                        {m.role === "manager" ? "Make User" : "Make Account Manager"}
                      </button>
                      <button type="button" className="btn" disabled={st.busy}
                        onClick={() => run({ username: m.username, remove: 1 }, "Taken off.")}>Remove</button>
                    </div>
                  ) : (
                    <button type="button" className="btn" disabled={st.busy}
                      onClick={() => run({ username: m.username, role: "manager" }, "Changed.")}>Make Account Manager</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="st-dim">No one is named on this customer yet.</p>}
      <div className="pl-row" style={{ marginTop: 12 }}>
        <div>
          <label htmlFor="cu-person">Person</label>
          <select id="cu-person" className="pl-in" value={f.username} onChange={(e) => setF((x) => ({ ...x, username: e.target.value }))}>
            <option value="">Choose a person</option>
            {choices.map((p) => <option key={p.username} value={p.username}>{p.name} ({p.username})</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="cu-role">Role</label>
          <select id="cu-role" className="pl-in" value={f.role} onChange={(e) => setF((x) => ({ ...x, role: e.target.value }))}>
            <option value="user">User</option>
            <option value="manager">Account Manager</option>
          </select>
        </div>
        <button type="button" className="btn" disabled={st.busy || !f.username}
          onClick={() => run({ username: f.username, role: f.role, override_seats: f.override ? 1 : 0 }, "Added.")}>
          Add Person
        </button>
      </div>
      <label className="st-check">
        <input type="checkbox" checked={f.override} onChange={(e) => setF((x) => ({ ...x, override: e.target.checked }))} />
        Allow beyond the seat limit
      </label>
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>
    </div>
  );
}

function RemoveCustomer({ c, onDone }) {
  const [sure, setSure] = useState(false);
  const [st, setSt] = useState({});
  return (
    <div className="dlg-sec">
      <h4>Remove Customer</h4>
      <p className="dlg-sub">
        Its businesses go back to no plan (no limits, no expiry) and its people stop taking its seats.
        Its usage stays on record.
      </p>
      {sure ? (
        <div className="st-acts" style={{ justifyContent: "flex-start" }}>
          <button type="button" className="btn" onClick={() => setSure(false)}>Keep It</button>
          <button type="button" className="btn pri" disabled={st.busy}
            onClick={async () => { if (await act(setSt, () => plansApi.remove(c.id), "Removed.")) onDone(); }}>
            Remove {c.name}
          </button>
        </div>
      ) : <button type="button" className="btn" onClick={() => setSure(true)}>Remove Customer</button>}
      <Msg tone="bad">{st.bad}</Msg>
    </div>
  );
}

function Statement({ c, data, onClose, onChanged }) {
  const [period, setPeriod] = useState(data.period);
  const { data: s, error, loading, reload } = useApi(() => plansApi.billing(c.id, period), [c.id, period]);
  const [st, setSt] = useState({});
  const [fix, setFix] = useState({ meter: "ai_questions", quantity: "", note: "" });
  const correct = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => plansApi.correction({ id: c.id, period, ...fix }), "Correction recorded as a new row.");
    if (out) {
      setFix((x) => ({ ...x, quantity: "", note: "" }));
      reload();
      onChanged();
    }
  };
  return (
    <Dialog title={`Usage Statement · ${c.name}`} wide onClose={onClose}
      sub="The basis for a pro-forma invoice. It is not an invoice, and nothing is sent to the customer.">
      <div className="pl-row">
        <div>
          <label htmlFor="cu-month">Month</label>
          <input id="cu-month" className="pl-in" type="month" value={period} max={data.period}
            onChange={(e) => e.target.value && setPeriod(e.target.value)} />
        </div>
        <button type="button" className="btn" disabled={st.busy || !s} onClick={() => act(setSt, () => plansApi.billingPdf(c.id, period))}>Download PDF</button>
        <button type="button" className="btn" disabled={st.busy || !s} onClick={() => act(setSt, () => plansApi.billingXlsx(c.id, period))}>Download Excel</button>
      </div>
      {loading && !s ? <Loading what="Working out the statement" /> : null}
      {error ? <Failed error={error} onRetry={reload} what="the statement" /> : null}
      {s ? (
        <>
          <p className="dlg-sub">
            {s.licensed_to} · {s.plan} plan · {s.period_label}{s.complete ? "" : " (month in progress)"}
          </p>
          <div className="pl-table-w">
            <table className="dt">
              <thead>
                <tr>
                  <th>Meter</th>
                  <th className="pl-num">Used</th>
                  <th className="pl-num">Included</th>
                  <th className="pl-num">Over</th>
                  <th className="pl-num">Rate</th>
                  <th className="pl-num">Amount</th>
                </tr>
              </thead>
              <tbody>
                {s.lines.map((l) => (
                  <tr key={l.key}>
                    <td>{l.label}<span className="st-sub">{l.measured}</span></td>
                    <td className="pl-num">{n(l.used)}</td>
                    <td className="pl-num">{n(l.included)}</td>
                    <td className="pl-num">{n(l.over)}</td>
                    <td className="pl-num">{money(l.rate)}</td>
                    <td className="pl-num">{money(l.amount)}</td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={5}>Monthly base fee</td>
                  <td className="pl-num">{money(s.base_fee)}</td>
                </tr>
                <tr className="pl-total">
                  <td colSpan={5}>Total for the month</td>
                  <td className="pl-num">{money(s.total, s.currency)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="st-sub">
            Total = base fee + for each meter (used − included, never below 0) × its rate. Estimated
            Claude cost, the platform&apos;s own: {money(s.claude.cost, data.cost_currency)} over{" "}
            {Number(s.claude.requests).toLocaleString("en-GB")} requests
            {s.claude.unpriced ? `, ${s.claude.unpriced} with no price for their model` : ""}.
          </p>
          <form onSubmit={correct} className="dlg-sec">
            <h4>Record a Correction</h4>
            <p className="dlg-sub">Recorded as a new row in the ledger, with the reason; nothing is edited.</p>
            <div className="pl-row">
              <div>
                <label htmlFor="cu-fm">Meter</label>
                <select id="cu-fm" className="pl-in" value={fix.meter} onChange={(e) => setFix((x) => ({ ...x, meter: e.target.value }))}>
                  {data.meters.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="cu-fq">Add (or −Take Away)</label>
                <input id="cu-fq" className="pl-in" inputMode="numeric" value={fix.quantity}
                  onChange={(e) => setFix((x) => ({ ...x, quantity: e.target.value }))} placeholder="-2" />
              </div>
              <div style={{ flexBasis: 260 }}>
                <label htmlFor="cu-fn">Reason</label>
                <input id="cu-fn" className="pl-in" value={fix.note} maxLength={255}
                  onChange={(e) => setFix((x) => ({ ...x, note: e.target.value }))} />
              </div>
              <button type="submit" className="btn" disabled={st.busy}>Record Correction</button>
            </div>
          </form>
        </>
      ) : null}
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>
      <div className="dlg-acts">
        <button type="button" className="ap-act pri" onClick={onClose}>Done</button>
      </div>
    </Dialog>
  );
}

function PlansPanel({ onSaved }) {
  const { data, error, loading, reload } = useApi(() => plansApi.planSettings(), []);
  const [edit, setEdit] = useState(null);
  if (loading && !data) return <Loading what="Reading the plans" />;
  if (error && !data) return <Failed error={error} onRetry={reload} what="the plans" />;
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Plans</b>
          <span>What each tier includes (customers see this under View Plans, without rates), and its default rates.</span>
        </div>
      </div>
      <div className="pl-table-w">
        <table className="dt">
          <thead>
            <tr>
              <th>Plan</th>
              {data.meters.map((m) => <th key={m.key} className="pl-num">{m.label}</th>)}
              <th className="pl-num">Base Fee</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {data.plans.map((p) => (
              <tr key={p.code}>
                <td>{p.name}<span className="st-sub">{p.summary}</span></td>
                {data.meters.map((m) => <td key={m.key} className="pl-num">{n(p.limits[m.key])}</td>)}
                <td className="pl-num">{money(p.base_fee, p.currency)}</td>
                <td><div className="st-acts"><button className="btn" onClick={() => setEdit(p)}>Edit</button></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {edit ? <PlanForm p={edit} meters={data.meters} onClose={() => setEdit(null)}
        onSaved={() => { setEdit(null); reload(); onSaved(); }} /> : null}
    </div>
  );
}

function PlanForm({ p, meters, onClose, onSaved }) {
  const [f, setF] = useState({
    name: p.name, summary: p.summary, refresh: p.refresh, support: p.support,
    features: p.features.join("\n"), currency: p.currency, base_fee: String(p.base_fee),
    limits: Object.fromEntries(meters.map((m) => [m.key, p.limits[m.key] === null ? "Unlimited" : String(p.limits[m.key])])),
    overage: Object.fromEntries(meters.map((m) => [m.key, String(p.overage[m.key])])),
  });
  const [st, setSt] = useState({});
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => plansApi.savePlan({ code: p.code, ...f }), "Saved.");
    if (out) onSaved();
  };
  return (
    <Dialog title={`Edit the ${p.name} Plan`} wide onClose={onClose}
      sub="Limits apply to every customer on this plan unless overridden for one. Plain text only; no prices are shown to customers.">
      <form onSubmit={save}>
        <div className="st-form">
          <div><label htmlFor="pf-name">Name</label><input id="pf-name" value={f.name} onChange={set("name")} maxLength={40} /></div>
          <div><label htmlFor="pf-sum">Summary</label><input id="pf-sum" value={f.summary} onChange={set("summary")} maxLength={200} /></div>
          <div><label htmlFor="pf-ref">Data Refresh</label><input id="pf-ref" value={f.refresh} onChange={set("refresh")} maxLength={60} /></div>
          <div><label htmlFor="pf-sup">Support</label><input id="pf-sup" value={f.support} onChange={set("support")} maxLength={80} /></div>
        </div>
        <label htmlFor="pf-feat">Features (one per line)</label>
        <textarea id="pf-feat" className="pl-text" rows={5} value={f.features} onChange={set("features")} />
        <div className="dlg-sec">
          <h4>Limits</h4>
          <div className="pl-limits">
            {meters.map((m) => (
              <div key={m.key}>
                <label htmlFor={`pf-l-${m.key}`}>{m.label}</label>
                <input id={`pf-l-${m.key}`} className="pl-in sm" value={f.limits[m.key]}
                  onChange={(e) => setF((x) => ({ ...x, limits: { ...x.limits, [m.key]: e.target.value } }))} />
              </div>
            ))}
          </div>
        </div>
        <div className="dlg-sec">
          <h4>Default Rates</h4>
          <div className="pl-limits">
            <div><label htmlFor="pf-cur">Currency</label><input id="pf-cur" className="pl-in sm" value={f.currency} onChange={set("currency")} maxLength={8} /></div>
            <div><label htmlFor="pf-base">Monthly Base Fee</label><input id="pf-base" className="pl-in sm" inputMode="decimal" value={f.base_fee} onChange={set("base_fee")} /></div>
            {meters.map((m) => (
              <div key={m.key}>
                <label htmlFor={`pf-r-${m.key}`}>{m.label}: Each Beyond</label>
                <input id={`pf-r-${m.key}`} className="pl-in sm" inputMode="decimal" value={f.overage[m.key]}
                  onChange={(e) => setF((x) => ({ ...x, overage: { ...x.overage, [m.key]: e.target.value } }))} />
              </div>
            ))}
          </div>
        </div>
        <Msg tone="bad">{st.bad}</Msg>
        <div className="dlg-acts">
          <button type="button" className="ap-act" onClick={onClose}>Cancel</button>
          <button type="submit" className="ap-act pri" disabled={st.busy}>{st.busy ? "Saving…" : "Save Plan"}</button>
        </div>
      </form>
    </Dialog>
  );
}

const PRICE_COLS = [["input", "Input"], ["output", "Output"], ["cache_read", "Cache Read"], ["cache_write", "Cache Write"]];

function PricesPanel() {
  const { data, error, loading, reload } = useApi(() => plansApi.planSettings(), []);
  const [rows, setRows] = useState(null);
  const [st, setSt] = useState({});
  useEffect(() => {
    if (data) setRows(Object.entries(data.prices).map(([model, p]) => ({ model, ...Object.fromEntries(PRICE_COLS.map(([k]) => [k, String(p[k])])) })));
  }, [data]);
  if (loading && !data) return null;
  if (error && !data) return <Failed error={error} onRetry={reload} what="the Claude prices" />;
  if (!rows) return null;
  const setCell = (i, k) => (e) => setRows((r) => r.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)));
  const save = async () => {
    const prices = Object.fromEntries(rows.filter((r) => r.model.trim()).map((r) => [r.model.trim(),
      Object.fromEntries(PRICE_COLS.map(([k]) => [k, r[k] || 0]))]));
    const out = await act(setSt, () => plansApi.savePrices(prices), "Saved. New usage is costed with these prices; past usage keeps its own.");
    if (out) reload();
  };
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Claude Prices</b>
          <span>
            US dollars per million tokens, for the estimated cost. The shipped values are editable defaults,
            not a quotation from Anthropic: check Anthropic&apos;s current price list and keep them up to date.
          </span>
        </div>
      </div>
      <div className="pl-table-w">
        <table className="dt">
          <thead>
            <tr>
              <th>Model</th>
              {PRICE_COLS.map(([k, label]) => <th key={k} className="pl-num">{label}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td><input className="pl-in sm" aria-label="Model" value={r.model} onChange={setCell(i, "model")} placeholder="claude-…" /></td>
                {PRICE_COLS.map(([k, label]) => (
                  <td key={k}><input className="pl-in sm pl-num" aria-label={label} inputMode="decimal" value={r[k]} onChange={setCell(i, k)} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="st-acts" style={{ marginTop: 12 }}>
        <button type="button" className="btn" onClick={() => setRows((r) => [...r, { model: "", input: "0", output: "0", cache_read: "0", cache_write: "0" }])}>Add Model</button>
        <button type="button" className="btn pri" disabled={st.busy} onClick={save}>Save Prices</button>
      </div>
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>
    </div>
  );
}
