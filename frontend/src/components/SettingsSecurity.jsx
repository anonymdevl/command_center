import React, { useEffect, useState } from "react";
import { securityApi, settingsApi } from "../api/client.js";
import { useApi } from "../useApi.js";
import { Failed, Loading } from "./States.jsx";
import { Dialog, Msg, act, when } from "./SettingsParts.jsx";

/**
 * Settings -> Security (insights/core/security.py, security_watch.py): the platform
 * administrator's own, never given to a manager and absent from everyone else's boot
 * payload; the server refuses every call to anyone else whatever this screen does.
 *
 * Sign-in activity, live sessions, the security-relevant changes, the read-only watch of
 * each connected ERPNext, the incident register (with its Incident Report) and what the
 * application can tell about its own server settings. Nothing here sends anything to
 * anyone; nothing here runs a command on the server.
 */
const PARTS = [
  ["signins", "Sign-In Activity"],
  ["sessions", "Sessions"],
  ["watch", "ERPNext Watch"],
  ["incidents", "Incidents"],
  ["changes", "Configuration Changes"],
  ["posture", "Server Posture"],
];

const SEV_TAG = { critical: "tag t-od", high: "tag t-wt", medium: "tag sec-med", low: "tag t-dr", info: "tag t-dr" };
const SEV_WORD = { critical: "Critical", high: "High", medium: "Medium", low: "Low", info: "Information" };

function Sev({ s }) {
  return <span className={SEV_TAG[s] || "tag t-dr"}>{SEV_WORD[s] || s}</span>;
}

export default function SettingsSecurity() {
  const [part, setPart] = useState("signins");
  const ov = useApi(() => securityApi.overview(), []);
  const o = ov.data;
  const openF = o ? Object.values(o.open_findings || {}).reduce((a, b) => a + b, 0) : 0;
  return (
    <div className="st-stack">
      <div className="panel">
        <div className="ph">
          <div>
            <b>Security</b>
            <span>Who signs in and from where, what changed, what each connected ERPNext shows, and the incident register. For the platform&apos;s administrator only; it can never be given to anyone else.</span>
          </div>
          <button className="btn" onClick={ov.reload}>Refresh</button>
        </div>
        {o ? (
          <div className="sec-kpis">
            <div><b>{o.failed_24h}</b><span>Failed Sign-Ins, 24 Hours</span></div>
            <div><b>{o.lockouts}</b><span>Current Lockouts</span></div>
            <div><b>{o.sessions}</b><span>Live Sessions</span></div>
            <div>
              <b>{openF}</b>
              <span>Open Findings{o.open_findings?.critical ? `, ${o.open_findings.critical} critical` : ""}</span>
            </div>
            <div><b>{o.open_incidents}</b><span>Open Incidents</span></div>
            <div><b className="sec-small">{when(o.watch_checked, "Not yet")}</b><span>ERPNext Last Checked</span></div>
          </div>
        ) : ov.error ? <Failed error={ov.error} onRetry={ov.reload} what="the security summary" /> : <Loading what="Reading the security summary" />}
      </div>
      <div className="tabbar st-tabs" role="tablist" aria-label="Security">
        {PARTS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={part === k} className={`tab${part === k ? " on" : ""}`} onClick={() => setPart(k)}>
            {label}
          </button>
        ))}
      </div>
      {part === "signins" ? <SignIns onChange={ov.reload} /> : null}
      {part === "sessions" ? <Sessions onChange={ov.reload} /> : null}
      {part === "watch" ? <Watch onChange={ov.reload} /> : null}
      {part === "incidents" ? <Incidents onChange={ov.reload} /> : null}
      {part === "changes" ? <Changes /> : null}
      {part === "posture" ? <Posture /> : null}
    </div>
  );
}

/* --- sign-in activity ----------------------------------------------------------------- */
function SignIns({ onChange }) {
  const [days, setDays] = useState(7);
  const v = useApi(() => securityApi.signIns(days), [days]);
  const [st, setSt] = useState({});
  if (v.loading && !v.data) return <Loading what="Reading the sign-in record" />;
  if (v.error && !v.data) return <Failed error={v.error} onRetry={v.reload} what="the sign-in record" />;
  const d = v.data;
  const unlock = async (l) => {
    const out = await act(setSt, () => securityApi.unlock(l.kind, l.username || "", l.ip || ""), (x) => x.says);
    if (out) { v.reload(); onChange?.(); }
  };
  return (
    <>
      <div className="panel">
        <div className="ph">
          <div>
            <b>Current Lockouts</b>
            <span>Accounts and addresses refused for now after too many wrong passwords. A lock lifts by itself 15 minutes after the last attempt; Unlock lifts it now.</span>
          </div>
        </div>
        <Msg tone="ok">{st.ok}</Msg>
        <Msg tone="bad">{st.bad}</Msg>
        {d.lockouts.length ? (
          <div className="sec-scroll">
            <table className="dt">
              <thead><tr><th>Locked</th><th>Failed Attempts</th><th aria-label="Actions" /></tr></thead>
              <tbody>
                {d.lockouts.map((l, i) => (
                  <tr key={i}>
                    <td>{l.what}</td>
                    <td>{l.failures}</td>
                    <td className="st-acts"><button className="btn" disabled={st.busy} onClick={() => unlock(l)}>Unlock</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="thin">Nothing is locked out right now.</div>}
      </div>

      <div className="panel">
        <div className="ph">
          <div>
            <b>New Address Or Browser</b>
            <span>Successful sign-ins from an address or a kind of browser the account had not used before. Confirm the unexpected ones with the person.</span>
          </div>
          <select aria-label="Period" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={1}>Last 24 Hours</option>
            <option value={7}>Last 7 Days</option>
            <option value={30}>Last 30 Days</option>
            <option value={90}>Last 90 Days</option>
          </select>
        </div>
        {d.flagged.length ? <EventTable rows={d.flagged} /> : <div className="thin">No sign-in from a new address or browser in this period.</div>}
      </div>

      <div className="sec-two">
        <div className="panel">
          <div className="ph"><div><b>Failures By Address</b><span>Wrong passwords and attempts refused while locked.</span></div></div>
          {d.by_ip.length ? (
            <div className="sec-scroll">
              <table className="dt">
                <thead><tr><th>Address</th><th>Failures</th><th>Accounts Tried</th><th>Last</th></tr></thead>
                <tbody>
                  {d.by_ip.map((r) => (
                    <tr key={r.ip}>
                      <td className="st-nowrap">{r.ip || "Unknown"}</td>
                      <td>{r.failures}</td>
                      <td className="sec-wrap">{r.accounts.join(", ")}</td>
                      <td className="st-nowrap st-dim">{when(r.last)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="thin">No failed sign-ins in this period.</div>}
        </div>
        <div className="panel">
          <div className="ph"><div><b>Failures By Account</b><span>Names typed that are not an account or an email address are kept by length only.</span></div></div>
          {d.by_account.length ? (
            <div className="sec-scroll">
              <table className="dt">
                <thead><tr><th>Account</th><th>Failures</th><th>Addresses</th><th>Last</th></tr></thead>
                <tbody>
                  {d.by_account.map((r) => (
                    <tr key={r.username}>
                      <td className="sec-wrap">{r.username || "Not given"}{r.known ? null : <span className="st-sub">Not an account on the platform</span>}</td>
                      <td>{r.failures}</td>
                      <td>{r.addresses}</td>
                      <td className="st-nowrap st-dim">{when(r.last)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="thin">No failed sign-ins in this period.</div>}
        </div>
      </div>

      <div className="panel">
        <div className="ph">
          <div>
            <b>Recent Activity</b>
            <span>Every sign-in attempt on the platform, the administration and by single sign-on, newest first. Passwords are never recorded. Countries are not shown: looking an address up would send it to a third party.</span>
          </div>
          <button className="btn" onClick={v.reload}>Refresh</button>
        </div>
        {d.recent.length ? <EventTable rows={d.recent} /> : <div className="thin">No sign-in has been recorded in this period. Every attempt from now on is listed here.</div>}
      </div>
    </>
  );
}

function EventTable({ rows }) {
  return (
    <div className="sec-scroll">
      <table className="dt">
        <thead><tr><th>When</th><th>What</th><th>Account</th><th>Address</th><th>Browser</th><th>Route</th></tr></thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id}>
              <td className="st-nowrap st-dim">{when(e.at)}</td>
              <td>
                <span className={e.outcome === "success" || e.outcome === "done" ? "tag t-ok" : e.outcome === "failed" ? "tag t-wt" : "tag t-od"}>{e.what}</span>
                {e.locked ? <span className="st-sub">Locked out by this attempt</span> : null}
                {e.first_seen ? <span className="st-sub">First recorded sign-in</span> : (
                  <>
                    {e.new_ip && e.outcome === "success" ? <span className="st-sub">New address for this account</span> : null}
                    {e.new_agent && e.outcome === "success" ? <span className="st-sub">New browser for this account</span> : null}
                  </>
                )}
                {e.actor ? <span className="st-sub">By {e.actor}</span> : null}
                {e.note && !e.actor ? <span className="st-sub">{e.note}</span> : null}
              </td>
              <td className="sec-wrap">{e.username || "—"}</td>
              <td className="st-nowrap">{e.ip || "—"}</td>
              <td className="st-nowrap">{e.agent || "—"}</td>
              <td className="st-nowrap st-dim">{e.channel}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* --- sessions ---------------------------------------------------------------------------- */
function Sessions({ onChange }) {
  const v = useApi(() => securityApi.sessions(), []);
  const [ask, setAsk] = useState(null);
  const [st, setSt] = useState({});
  if (v.loading && !v.data) return <Loading what="Reading the live sessions" />;
  if (v.error && !v.data) return <Failed error={v.error} onRetry={v.reload} what="the live sessions" />;
  const rows = v.data || [];
  const go = async () => {
    const out = await act(setSt, () => securityApi.signOutEverywhere(ask.username), (x) => x.says);
    if (out) { setAsk(null); v.reload(); onChange?.(); }
  };
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Live Sessions</b>
          <span>Who is signed in now, on how many devices. Sign Out Everywhere ends every session of that person at once; for your own account it keeps this one.</span>
        </div>
        <button className="btn" onClick={v.reload}>Refresh</button>
      </div>
      <Msg tone="ok">{st.ok && !ask ? st.ok : null}</Msg>
      {rows.length ? (
        <div className="sec-scroll">
          <table className="dt">
            <thead><tr><th>Person</th><th>Sessions</th><th>Latest</th><th aria-label="Actions" /></tr></thead>
            <tbody>
              {rows.map((p) => {
                const s = p.sessions[0] || {};
                return (
                  <tr key={p.username}>
                    <td className="sec-wrap">
                      {p.full_name}{p.is_me ? " (you)" : ""}
                      <span className="st-sub">{p.username}{p.is_admin ? " · Administrator" : ""}{p.active ? "" : " · Deactivated"}</span>
                    </td>
                    <td>{p.count}</td>
                    <td className="sec-wrap">
                      {s.since ? when(s.since) : "Began before sessions were recorded"}
                      <span className="st-sub">{[s.ip, s.agent].filter(Boolean).join(" · ")}{s.current ? " · This session" : ""}</span>
                      {p.sessions.length > 1 ? (
                        <details className="sec-more">
                          <summary>All {p.sessions.length}</summary>
                          <ul>
                            {p.sessions.map((x, i) => (
                              <li key={i}>{x.since ? when(x.since) : "Not recorded"} · {x.ip || "No address"} · {x.agent}{x.current ? " · This session" : ""}</li>
                            ))}
                          </ul>
                        </details>
                      ) : null}
                    </td>
                    <td className="st-acts">
                      <button className="btn" onClick={() => { setSt({}); setAsk(p); }}
                        disabled={p.is_me && p.count <= 1}>
                        Sign Out Everywhere
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : <div className="thin">Nobody is signed in right now.</div>}
      {ask ? (
        <Dialog title="Sign Out Everywhere" onClose={() => setAsk(null)}
          sub={ask.is_me ? "Every other session of your account ends now. This one stays." : `Every session of ${ask.full_name} ends now. They can sign in again unless their account is deactivated or their password is changed (Settings, People).`}>
          <Msg tone="bad">{st.bad}</Msg>
          <div className="dlg-acts">
            <button className="btn" onClick={() => setAsk(null)}>Cancel</button>
            <button className="btn pri" disabled={st.busy} onClick={go}>{st.busy ? "Signing Out…" : "Sign Out Everywhere"}</button>
          </div>
        </Dialog>
      ) : null}
    </div>
  );
}

/* --- the ERPNext watch ------------------------------------------------------------------- */
const CHECK_TAG = { ok: "tag t-ok", refused: "tag t-wt", unavailable: "tag t-dr", unreachable: "tag t-od", error: "tag t-od", pending: "tag t-dr" };

function Watch({ onChange }) {
  const [status, setStatus] = useState("open");
  const v = useApi(() => securityApi.watch(status === "all" ? "" : status), [status]);
  const [run, setRun] = useState({});
  const [open, setOpen] = useState(null);
  if (v.loading && !v.data) return <Loading what="Reading the ERPNext watch" />;
  if (v.error && !v.data) return <Failed error={v.error} onRetry={v.reload} what="the ERPNext watch" />;
  const d = v.data;
  const runNow = async (code) => {
    const out = await act(setRun, () => securityApi.runWatch(code || ""), (x) => x.says);
    if (out) { v.reload(); onChange?.(); }
  };
  return (
    <>
      <div className="panel">
        <div className="ph">
          <div>
            <b>ERPNext Watch</b>
            <span>Every 30 minutes the platform reads each connected business&apos;s ERPNext, with its existing read-only account, for signs of trouble: Server Scripts, the System Console, new administrators, API keys, sign-ins, new users and the password settings. It only reads; it never changes anything there.</span>
          </div>
          {d.businesses.length ? (
            <button className="btn pri" disabled={run.busy} onClick={() => runNow("")}>{run.busy ? "Checking…" : "Run Checks Now"}</button>
          ) : null}
        </div>
        <Msg tone="ok">{run.ok}</Msg>
        <Msg tone="bad">{run.bad}</Msg>
        {d.businesses.length ? d.businesses.map((b) => (
          <div key={b.business_code} className="sec-biz">
            <h4>{b.name} <span className="st-dim">{b.checked_at ? `checked ${when(b.checked_at)}` : "not checked yet"}</span></h4>
            <div className="sec-scroll">
              <table className="dt">
                <thead><tr><th>Check</th><th>Result</th><th>What Was Seen</th></tr></thead>
                <tbody>
                  {b.checks.map((c) => (
                    <tr key={c.id}>
                      <td className="st-nowrap">{c.label}</td>
                      <td className="st-nowrap"><span className={CHECK_TAG[c.status] || "tag t-dr"}>{c.status_label}</span></td>
                      <td className="sec-wrap">{c.guide ? <div className="st-msg note">{c.message}</div> : c.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )) : (
          <div className="thin">No connected business to watch. Businesses are checked once they are connected under Settings, Businesses (paused businesses are not checked).</div>
        )}
      </div>

      <div className="panel">
        <div className="ph">
          <div>
            <b>Findings</b>
            <span>What the watch and the sign-in record found, most serious first. Critical findings go to your bell, and by email when email is set up, once each.</span>
          </div>
          <select aria-label="Show" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="cleared">Cleared</option>
            <option value="all">All</option>
          </select>
        </div>
        {d.findings.length ? (
          <div className="sec-scroll">
            <table className="dt">
              <thead><tr><th>Severity</th><th>Finding</th><th>Where</th><th>First Seen</th><th aria-label="Actions" /></tr></thead>
              <tbody>
                {d.findings.map((f) => (
                  <tr key={f.id}>
                    <td><Sev s={f.severity} /></td>
                    <td className="sec-wrap">{f.title}<span className="st-sub">{f.check_label}{f.status !== "open" ? ` · ${f.status_label}` : ""}{f.incidents.length ? ` · Incident ${f.incidents.map((x) => `INC-${String(x).padStart(4, "0")}`).join(", ")}` : ""}</span></td>
                    <td className="sec-wrap">{f.business}</td>
                    <td className="st-nowrap st-dim">{when(f.first_seen)}</td>
                    <td className="st-acts"><button className="btn" onClick={() => setOpen(f)}>Details</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="thin">
            {status === "open" ? "No open findings. " : "None in this list. "}
            {d.businesses.some((b) => b.checked_at) ? "Findings appear here as the checks and the sign-in record find them." : "The first checks have not run yet; press Run Checks Now, or wait for the next half hour."}
          </div>
        )}
      </div>
      {open ? <FindingDialog f={open} onClose={() => setOpen(null)} onChanged={() => { v.reload(); onChange?.(); }} /> : null}
    </>
  );
}

function FindingDialog({ f, onClose, onChanged }) {
  const [st, setSt] = useState({});
  const [mode, setMode] = useState(null);
  const inc = useApi(() => securityApi.incidents(), [], { skip: mode !== "link" });
  const [pick, setPick] = useState("");
  const ack = async () => {
    const out = await act(setSt, () => securityApi.acknowledge(f.id), "Acknowledged. It stays on record under Acknowledged.");
    if (out) onChanged();
  };
  const openInc = async () => {
    const out = await act(setSt, () => securityApi.openIncident({ finding_id: f.id }), (x) => `Incident ${x.ref} opened. Find it under Incidents.`);
    if (out) onChanged();
  };
  const link = async () => {
    const out = await act(setSt, () => securityApi.linkFinding(pick, f.id), (x) => `Added to ${x.ref}.`);
    if (out) { setMode(null); onChanged(); }
  };
  const open = (inc.data || []).filter((x) => x.status !== "Resolved");
  return (
    <Dialog title={f.title} wide onClose={onClose} sub={`${f.business} · ${f.check_label} · first seen ${when(f.first_seen)}, last seen ${when(f.last_seen)}`}>
      <p><Sev s={f.severity} /> <span className="st-dim">{f.status_label}{f.acknowledged_by ? ` by ${f.acknowledged_by}, ${when(f.acknowledged_at)}` : ""}</span></p>
      <p>{f.detail}</p>
      {f.evidence.length ? (
        <dl className="st-facts">
          {f.evidence.map((e, i) => (
            <React.Fragment key={i}><dt>{e.label}</dt><dd className="sec-code">{e.value}</dd></React.Fragment>
          ))}
        </dl>
      ) : null}
      <div className="dlg-sec">
        <h4>Recommended Action</h4>
        <p>{f.action}</p>
        {f.doc_url ? <p><a className="lnk" href={f.doc_url} target="_blank" rel="noreferrer noopener">Open In The Business&apos;s ERPNext ↗</a></p> : null}
      </div>
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>
      {mode === "link" ? (
        <div className="st-form" style={{ marginTop: 12 }}>
          <div>
            <label htmlFor="sec-link">Incident</label>
            <select id="sec-link" value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">Choose an open incident</option>
              {open.map((x) => <option key={x.id} value={x.id}>{x.ref} {x.title}</option>)}
            </select>
          </div>
          <div className="dlg-acts"><button className="btn pri" disabled={!pick || st.busy} onClick={link}>Add To Incident</button></div>
        </div>
      ) : null}
      <div className="dlg-acts">
        <button className="btn" onClick={onClose}>Close</button>
        {f.status === "open" ? <button className="btn" disabled={st.busy} onClick={ack}>Acknowledge</button> : null}
        <button className="btn" disabled={st.busy} onClick={() => setMode("link")}>Add To An Incident</button>
        <button className="btn pri" disabled={st.busy} onClick={openInc}>Open Incident</button>
      </div>
    </Dialog>
  );
}

/* --- incidents ----------------------------------------------------------------------------- */
const STATUS_TAG = { Open: "tag t-od", Investigating: "tag t-wt", Contained: "tag sec-med", Resolved: "tag t-ok" };

function Incidents({ onChange }) {
  const v = useApi(() => securityApi.incidents(), []);
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState(null);
  if (v.loading && !v.data) return <Loading what="Reading the incident register" />;
  if (v.error && !v.data) return <Failed error={v.error} onRetry={v.reload} what="the incident register" />;
  const rows = v.data || [];
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Incident Register</b>
          <span>Every security incident, from a finding or opened by hand, with its timeline. The Incident Report is a PDF you download; nothing is sent to anyone.</span>
        </div>
        <button className="btn pri" onClick={() => setAdding(true)}>Open Incident</button>
      </div>
      {rows.length ? (
        <div className="sec-scroll">
          <table className="dt">
            <thead><tr><th>Reference</th><th>Incident</th><th>Severity</th><th>Status</th><th>Opened</th><th aria-label="Actions" /></tr></thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.id}>
                  <td className="st-nowrap">{i.ref}</td>
                  <td className="sec-wrap">{i.title}<span className="st-sub">{i.business_names.join(", ") || "The platform"}</span></td>
                  <td><Sev s={i.severity} /></td>
                  <td><span className={STATUS_TAG[i.status] || "tag t-dr"}>{i.status}</span></td>
                  <td className="st-nowrap st-dim">{when(i.opened_at)}</td>
                  <td className="st-acts"><button className="btn" onClick={() => setOpen(i.id)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <div className="thin">No incidents are on record. Open one from a finding (ERPNext Watch, Details) or by hand when something needs investigating.</div>}
      {adding ? <NewIncident onClose={() => setAdding(false)} onDone={(x) => { setAdding(false); v.reload(); onChange?.(); setOpen(x.id); }} /> : null}
      {open ? <IncidentDialog id={open} onClose={() => { setOpen(null); v.reload(); onChange?.(); }} /> : null}
    </div>
  );
}

function useBusinesses() {
  return useApi(() => settingsApi.businesses(), []);
}

function BusinessPicks({ value, onChange }) {
  const b = useBusinesses();
  const list = b.data || [];
  if (!list.length) return null;
  const toggle = (code) => onChange(value.includes(code) ? value.filter((x) => x !== code) : [...value, code]);
  return (
    <div className="st-choice">
      {list.map((x) => (
        <label key={x.business_code} className="st-check">
          <input type="checkbox" checked={value.includes(x.business_code)} onChange={() => toggle(x.business_code)} />
          {x.business_name}
        </label>
      ))}
    </div>
  );
}

function NewIncident({ onClose, onDone }) {
  const [f, setF] = useState({ title: "", severity: "high", summary: "", businesses: [] });
  const [st, setSt] = useState({});
  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => securityApi.openIncident(f), "Opened.");
    if (out) onDone(out);
  };
  return (
    <Dialog title="Open Incident" onClose={onClose} sub="Give it a short title. The timeline, evidence and report sections can be filled in as the investigation goes.">
      <form onSubmit={save}>
        <label htmlFor="ni-title">Title</label>
        <input id="ni-title" maxLength={200} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
        <label htmlFor="ni-sev">Severity</label>
        <select id="ni-sev" value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })}>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <label>Affected Businesses</label>
        <BusinessPicks value={f.businesses} onChange={(businesses) => setF({ ...f, businesses })} />
        <label htmlFor="ni-sum">Summary</label>
        <textarea id="ni-sum" rows={4} maxLength={20000} value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} />
        <Msg tone="bad">{st.bad}</Msg>
        <div className="dlg-acts">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn pri" disabled={st.busy}>{st.busy ? "Opening…" : "Open Incident"}</button>
        </div>
      </form>
    </Dialog>
  );
}

const SECTIONS = [
  ["summary", "Summary"],
  ["impact", "Impact"],
  ["actions", "Actions Taken"],
  ["root_cause", "Root Cause"],
  ["recommendations", "Recommendations"],
  ["lessons", "Lessons Learned"],
];

function IncidentDialog({ id, onClose }) {
  const v = useApi(() => securityApi.incident(id), [id]);
  const [f, setF] = useState(null);
  const [st, setSt] = useState({});
  const [note, setNote] = useState("");
  const [status, setStatus] = useState("");
  const [statusNote, setStatusNote] = useState("");
  const [dl, setDl] = useState({});
  useEffect(() => {
    const d = v.data;
    if (!d) return;
    setF({ title: d.title, severity: d.severity, businesses: d.businesses,
      ...Object.fromEntries(SECTIONS.map(([k]) => [k, d[k] || ""])) });
    setStatus(d.status);
  }, [v.data]);
  if (!v.data || !f) {
    return (
      <Dialog title="Incident" onClose={onClose}>
        {v.error ? <Failed error={v.error} onRetry={v.reload} what="the incident" /> : <Loading what="Reading the incident" />}
      </Dialog>
    );
  }
  const d = v.data;
  const saveSections = async () => {
    const out = await act(setSt, () => securityApi.updateIncident({ id, ...f }), "Saved.");
    if (out) v.reload();
  };
  const saveStatus = async () => {
    const out = await act(setSt, () => securityApi.setIncidentStatus(id, status, statusNote), (x) => `Status is now ${x.status}.`);
    if (out) { setStatusNote(""); v.reload(); }
  };
  const addNote = async () => {
    const out = await act(setSt, () => securityApi.addIncidentNote(id, note), "Note added to the timeline.");
    if (out) { setNote(""); v.reload(); }
  };
  return (
    <Dialog title={`${d.ref} ${d.title}`} wide onClose={onClose}
      sub={`Opened ${when(d.opened_at)} by ${d.opened_by}${d.resolved_at ? ` · Resolved ${when(d.resolved_at)}` : ""}`}>
      <div className="dlg-acts sec-left">
        <button className="btn" disabled={dl.busy} onClick={() => act(setDl, () => securityApi.incidentPdf(id), "Incident Report downloaded.")}>Incident Report (PDF)</button>
        <button className="btn" disabled={dl.busy} onClick={() => act(setDl, () => securityApi.incidentXlsx(id), "Events downloaded.")}>Events (Excel)</button>
      </div>
      <Msg tone="ok">{dl.ok}</Msg>
      <Msg tone="bad">{dl.bad}</Msg>

      <div className="dlg-sec">
        <h4>Status</h4>
        <label htmlFor="in-status">Status</label>
        <select id="in-status" value={status} onChange={(e) => setStatus(e.target.value)}>
          {["Open", "Investigating", "Contained", "Resolved"].map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <label htmlFor="in-snote">Note For The Timeline (Optional)</label>
        <input id="in-snote" maxLength={4000} value={statusNote} onChange={(e) => setStatusNote(e.target.value)} />
        <div className="dlg-acts"><button className="btn" disabled={st.busy || status === d.status} onClick={saveStatus}>Change Status</button></div>
      </div>

      <div className="dlg-sec">
        <h4>Report</h4>
        <label htmlFor="in-title">Title</label>
        <input id="in-title" maxLength={200} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
        <label htmlFor="in-sev">Severity</label>
        <select id="in-sev" value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })}>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <label>Affected Businesses</label>
        <BusinessPicks value={f.businesses} onChange={(businesses) => setF({ ...f, businesses })} />
        {SECTIONS.map(([k, label]) => (
          <React.Fragment key={k}>
            <label htmlFor={`in-${k}`}>{label}</label>
            <textarea id={`in-${k}`} rows={3} maxLength={20000} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
          </React.Fragment>
        ))}
        <div className="dlg-acts"><button className="btn pri" disabled={st.busy} onClick={saveSections}>Save Report</button></div>
      </div>
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>

      <div className="dlg-sec">
        <h4>Evidence</h4>
        {d.finding_rows.length ? (
          <ul className="sec-list">
            {d.finding_rows.map((x) => (
              <li key={x.id}><Sev s={x.severity} /> {x.title} <span className="st-dim">· {x.business} · {when(x.first_seen)}</span></li>
            ))}
          </ul>
        ) : <p className="st-dim">No findings attached. Add one from ERPNext Watch → Details → Add To An Incident.</p>}
      </div>

      <div className="dlg-sec">
        <h4>Timeline</h4>
        <ul className="sec-list">
          {d.notes.map((n, i) => (
            <li key={i}><span className="st-dim st-nowrap">{when(n.at)} · {n.by}</span><span className="sec-note">{n.text}</span></li>
          ))}
        </ul>
        <label htmlFor="in-note">Add A Note</label>
        <textarea id="in-note" rows={2} maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} />
        <div className="dlg-acts">
          <button className="btn" onClick={onClose}>Close</button>
          <button className="btn pri" disabled={!note.trim() || st.busy} onClick={addNote}>Add Note</button>
        </div>
      </div>
    </Dialog>
  );
}

/* --- configuration changes ------------------------------------------------------------- */
function Changes() {
  const v = useApi(() => securityApi.changes(), []);
  if (v.loading && !v.data) return <Loading what="Reading the changes" />;
  if (v.error && !v.data) return <Failed error={v.error} onRetry={v.reload} what="the changes" />;
  const rows = v.data || [];
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Configuration Changes</b>
          <span>Changes made in Settings that bear on security: business keys, the Claude key, Settings access, administrators and people, email, branding, plans and the actions taken here. Secrets are never recorded. Every change is under Settings, Changes.</span>
        </div>
        <button className="btn" onClick={v.reload}>Refresh</button>
      </div>
      {rows.length ? (
        <div className="sec-scroll">
          <table className="dt">
            <thead><tr><th>When</th><th>Who</th><th>Kind</th><th>What</th></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td className="st-nowrap st-dim">{when(r.when)}</td>
                  <td className="st-nowrap">{r.who}</td>
                  <td className="st-nowrap"><span className="tag t-dr">{r.kind}</span></td>
                  <td className="sec-wrap">{r.what}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <div className="thin">No security-relevant change has been made in Settings yet.</div>}
    </div>
  );
}

/* --- server posture ------------------------------------------------------------------------ */
function Posture() {
  const v = useApi(() => securityApi.posture(), []);
  if (v.loading && !v.data) return <Loading what="Reading the platform's settings" />;
  if (v.error && !v.data) return <Failed error={v.error} onRetry={v.reload} what="the platform's settings" />;
  const d = v.data;
  return (
    <>
      <div className="panel">
        <div className="ph">
          <div>
            <b>Platform Settings</b>
            <span>What the application can tell about its own security settings. Read only.</span>
          </div>
          <button className="btn" onClick={v.reload}>Refresh</button>
        </div>
        <div className="sec-scroll">
          <table className="dt">
            <thead><tr><th>Setting</th><th>Now</th><th>State</th></tr></thead>
            <tbody>
              {d.items.map((x) => (
                <tr key={x.label}>
                  <td className="sec-wrap">{x.label}{x.advice ? <span className="st-sub">{x.advice}</span> : null}</td>
                  <td className="sec-wrap">{x.value}</td>
                  <td className="st-nowrap">
                    {x.ok === true ? <span className="tag t-ok">Good</span> : x.ok === false ? <span className="tag t-wt">Attention</span> : <span className="tag t-dr">Check By Hand</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="panel">
        <div className="ph">
          <div>
            <b>Manual Checks</b>
            <span>{d.note}</span>
          </div>
        </div>
        <ol className="sec-manual">
          {d.manual.map((m) => (
            <li key={m.label}>
              <b>{m.label}</b> <span className="tag t-dr">Manual</span>
              <code>{m.command}</code>
              <span className="st-sub">{m.note}</span>
            </li>
          ))}
        </ol>
      </div>
    </>
  );
}
