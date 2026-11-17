import React, { useEffect, useState } from "react";
import { settingsApi } from "../api/client.js";
import { brand } from "../api/boot.js";
import { useApi } from "../useApi.js";
import { Failed, Loading } from "./States.jsx";
import { Msg, act, when } from "./SettingsParts.jsx";

const SECURITY = [
  ["starttls", "STARTTLS (usually port 587)"],
  ["ssl", "SSL (usually port 465)"],
  ["none", "None (not recommended)"],
];
const PORT = { starttls: "587", ssl: "465", none: "25" };

/** Administrator only: what the platform sends, and the mail server it sends from. */
export default function SettingsEmail() {
  const status = useApi(() => settingsApi.notifications(), []);
  const mail = useApi(() => settingsApi.email(), []);
  const reloadBoth = () => {
    status.reload();
    mail.reload();
  };
  return (
    <div className="st-stack">
      <Notifications {...status} />
      <EmailServer {...mail} onSaved={reloadBoth} />
      <EmailLog onResent={status.reload} />
    </div>
  );
}

const KIND_LABEL = { alert: "Alert", report: "Report", notice: "Notice", test: "Test", digest: "Digest", invite: "Invite", other: "Other" };

/** Every send attempt, newest first (insights/core/platform_settings.email_log). */
function EmailLog({ onResent }) {
  const [status, setStatus] = useState("");
  const log = useApi(() => settingsApi.emailLog(status), [status]);
  const [open, setOpen] = useState(null);
  const [st, setSt] = useState({});
  const rows = log.data?.rows || [];
  const resend = async (r) => {
    const out = await act(setSt, () => settingsApi.resendEmail(r.id), (o) => o?.says);
    if (out && !out.ok) setSt({ bad: out.says });
    log.reload();
    onResent?.();
  };
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Email Log</b>
          <span>
            Every email the platform tried to send, newest first: the last {log.data?.shown || 100}
            {log.data?.keep_days ? `, kept ${log.data.keep_days} days` : ""}. Select a failed one to see why.
          </span>
        </div>
        <select aria-label="Show" value={status} onChange={(e) => { setStatus(e.target.value); setOpen(null); }}>
          <option value="">All</option>
          <option value="Sent">Sent</option>
          <option value="Failed">Failed</option>
        </select>
      </div>
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>
      {log.loading && !log.data ? <Loading what="Reading the email log" /> : null}
      {log.error && !log.data ? <Failed error={log.error} onRetry={log.reload} what="the email log" /> : null}
      {log.data && !rows.length ? (
        <div className="thin">{status ? `No ${status.toLowerCase()} emails in the log.` : "Nothing has been sent yet. Each email the platform sends is listed here."}</div>
      ) : null}
      {rows.length ? (
        <div className="sec-scroll">
          <table className="dt mail-log">
            <thead><tr><th>Time</th><th>Kind</th><th>To</th><th>Subject</th><th>Status</th><th aria-label="Actions" /></tr></thead>
            <tbody>
              {rows.map((r) => (
                <React.Fragment key={r.id}>
                  <tr className={r.status === "Failed" ? "mail-failed" : undefined}
                      onClick={r.status === "Failed" ? () => setOpen(open === r.id ? null : r.id) : undefined}
                      title={r.error || undefined}>
                    <td className="st-nowrap st-dim">{when(r.at)}</td>
                    <td className="st-nowrap">{KIND_LABEL[r.kind] || r.kind}</td>
                    <td className="sec-wrap">{r.to || "—"}</td>
                    <td className="sec-wrap">{r.subject || "—"}{r.resend_of ? <span className="st-sub">Sent again</span> : null}</td>
                    <td className="st-nowrap">
                      {r.status === "Sent" ? <span className="tag t-ok">Sent</span> : <span className="tag t-od">Failed</span>}
                    </td>
                    <td className="st-acts">
                      {r.status === "Failed" ? (
                        <button type="button" className="btn" aria-expanded={open === r.id}
                                onClick={(e) => { e.stopPropagation(); setOpen(open === r.id ? null : r.id); }}>
                          {open === r.id ? "Hide" : "Why"}
                        </button>
                      ) : null}
                      {r.can_resend ? (
                        <button type="button" className="btn" disabled={st.busy}
                                onClick={(e) => { e.stopPropagation(); resend(r); }}>Resend</button>
                      ) : null}
                    </td>
                  </tr>
                  {open === r.id ? (
                    <tr className="mail-why">
                      <td colSpan={6}>
                        <b>Why it failed:</b> {r.error || "No reason was given."}
                        {r.why_not ? <span className="st-sub">{r.why_not}</span> : null}
                      </td>
                    </tr>
                  ) : null}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function lastSend(a) {
  if (!a) return "Nothing has been sent yet.";
  if (a.ok) return `${when(a.when)}: sent${a.subject ? ` (${a.subject})` : ""}.`;
  return `${when(a.when)}: not sent. ${a.error || ""}`.trim();
}

function Notifications({ data, error, loading, reload }) {
  if (loading && !data) return <Loading what="Reading what the platform sends" />;
  if (error && !data) return <Failed error={error} onRetry={reload} what="the notifications" />;
  const n = data || {};
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Notifications</b>
          <span>What the platform sends by email, and whether it can.</span>
        </div>
        <button className="btn" onClick={reload}>Refresh</button>
      </div>
      <dl className="st-facts">
        <dt>Email</dt>
        <dd>
          {n.email_configured
            ? <span className="tag t-ok">Set up</span>
            : <><span className="tag t-od">Not set up</span> <span className="st-dim">Scheduled reports cannot be sent until it is.</span></>}
        </dd>
        <dt>Scheduled reports</dt>
        <dd>{n.schedules_on} switched on{n.schedules_total > n.schedules_on ? ` (${n.schedules_total - n.schedules_on} switched off)` : ""}</dd>
        <dt>Alert rules</dt>
        <dd>
          {n.rules_on} of {n.rules_total} switched on
          <span className="st-sub">Alerts are shown in the bell on the screens; they are not sent by email.</span>
        </dd>
        <dt>Last email</dt>
        <dd>{lastSend(n.last_attempt)}</dd>
      </dl>
      {n.failing?.length ? (
        <Msg tone="bad">
          {n.failing.length === 1 ? "One scheduled report was not sent last time:" : `${n.failing.length} scheduled reports were not sent last time:`}
          <ul>
            {n.failing.map((f, i) => (
              <li key={i}>{f.report} for {f.business}. {f.status}</li>
            ))}
          </ul>
        </Msg>
      ) : null}
    </div>
  );
}

function EmailServer({ data, error, loading, reload, onSaved }) {
  const [f, setF] = useState(null);
  const [st, setSt] = useState({});
  const [to, setTo] = useState("");
  const [test, setTest] = useState({});

  useEffect(() => {
    if (!data) return;
    setF({
      host: data.host || "", port: data.port ? String(data.port) : "", security: data.security || "starttls",
      user: data.user || "", password: "", sender: data.sender || "", sender_name: data.sender_name || "",
    });
  }, [data]);

  if (loading && !data) return <Loading what="Reading the email settings" />;
  if (error && !data) return <Failed error={error} onRetry={reload} what="the email settings" />;
  if (!f) return null;
  const m = data || {};
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => settingsApi.setEmail(f),
      "Saved. It is used from the next email; send a test to check it.");
    if (out) {
      setTest({});
      onSaved();
    }
  };

  const sendTest = async (e) => {
    e.preventDefault();
    const out = await act(setTest, () => settingsApi.testEmail(to.trim()));
    if (out) {
      setTest({ [out.ok ? "ok" : "bad"]: out.says });
      onSaved();
    }
  };

  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Email</b>
          <span>The mail server scheduled reports are sent from. Your email provider gives these details.</span>
        </div>
      </div>
      <form onSubmit={save}>
        <div className="st-form">
          <div>
            <label htmlFor="em-host">Mail server</label>
            <input id="em-host" autoComplete="off" value={f.host} onChange={set("host")} placeholder="smtp.example.com" />
          </div>
          <div>
            <label htmlFor="em-sec">Security</label>
            <select id="em-sec" value={f.security} onChange={set("security")}>
              {SECURITY.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="em-port">Port</label>
            <input id="em-port" inputMode="numeric" autoComplete="off" value={f.port} onChange={set("port")} placeholder={PORT[f.security]} />
          </div>
          <div>
            <label htmlFor="em-user">Username</label>
            <input id="em-user" autoComplete="off" value={f.user} onChange={set("user")} placeholder="Usually the email address" />
          </div>
          <div>
            <label htmlFor="em-pw">Password</label>
            <input id="em-pw" type="password" autoComplete="new-password" value={f.password} onChange={set("password")}
              placeholder={m.has_password ? "Leave blank to keep the stored one" : ""} />
          </div>
          <div>
            <label htmlFor="em-from">From address</label>
            <input id="em-from" type="email" autoComplete="off" value={f.sender} onChange={set("sender")} placeholder="reports@example.com" />
          </div>
          <div>
            <label htmlFor="em-name">From name</label>
            <input id="em-name" autoComplete="off" value={f.sender_name} onChange={set("sender_name")} placeholder={brand.product} />
          </div>
          <div>
            <button type="submit" className="btn pri" disabled={st.busy || !f.host.trim()}>
              {st.busy ? "Saving…" : m.configured ? "Save Changes" : "Save Email Settings"}
            </button>
          </div>
        </div>
      </form>
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>

      <form className="st-form" style={{ marginTop: 20 }} onSubmit={sendTest}>
        <div>
          <label htmlFor="em-to">Send a test to</label>
          <input id="em-to" type="email" autoComplete="off" value={to} onChange={(e) => setTo(e.target.value)} placeholder="you@example.com" />
        </div>
        <div>
          <button type="submit" className="btn" disabled={test.busy || !to.trim() || !m.configured}
            title={!m.configured ? "Save the email settings first" : undefined}>
            {test.busy ? "Sending…" : "Send Test Email"}
          </button>
        </div>
      </form>
      <Msg tone="ok">{test.ok}</Msg>
      <Msg tone="bad">{test.bad}</Msg>
    </div>
  );
}
