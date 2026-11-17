import React, { useState } from "react";
import { settingsApi } from "../api/client.js";
import { useApi } from "../useApi.js";
import { Failed, Loading } from "./States.jsx";
import { Dialog, Msg, act, when } from "./SettingsParts.jsx";

/** The Claude key: set or not (masked), replace it, and check it answers. */
export function SettingsClaude() {
  const { data, error, loading, reload } = useApi(() => settingsApi.claude(), []);
  const [key, setKey] = useState("");
  const [st, setSt] = useState({});
  const [check, setCheck] = useState({});

  if (loading && !data) return <Loading what="Reading the Claude settings" />;
  if (error && !data) return <Failed error={error} onRetry={reload} what="the Claude settings" />;
  const c = data || {};

  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => settingsApi.setClaudeKey(key), "Key replaced. It is used from the next question; press Check to try it.");
    if (out) {
      setKey("");
      setCheck({});
      reload();
    }
  };

  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Claude</b>
          <span>The AI that answers questions and writes the reports.</span>
        </div>
      </div>
      <dl className="st-facts">
        <dt>Key</dt>
        <dd>{c.set ? <>Set <span className="st-dim">({c.masked})</span></> : "Not set: questions are answered by the basic search only"}</dd>
        <dt>In use</dt>
        <dd>{c.provider === "claude" ? "Claude" : c.provider ? `${c.provider} (not Claude)` : "No AI"}</dd>
        <dt>Questions</dt>
        <dd>{c.model}</dd>
        <dt>Deeper looks and reports</dt>
        <dd>{c.deep_model}</dd>
      </dl>
      <div className="acts">
        <button className="btn" disabled={check.busy}
          onClick={() => act(setCheck, () => settingsApi.checkClaude()).then((o) => o && setCheck({ [o.ok ? "ok" : "bad"]: o.says }))}>
          {check.busy ? "Checking…" : "Check"}
        </button>
      </div>
      <Msg tone="ok">{check.ok}</Msg>
      <Msg tone="bad">{check.bad}</Msg>

      <form className="st-form" style={{ marginTop: 20 }} onSubmit={save}>
        <div>
          <label htmlFor="cl-key">{c.set ? "Replace the key" : "Add the key"}</label>
          <input id="cl-key" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)}
            placeholder="Paste the key from the Anthropic console" />
        </div>
        <div>
          <button type="submit" className="btn pri" disabled={st.busy || !key.trim()}>
            {st.busy ? "Saving…" : c.set ? "Replace Key" : "Save Key"}
          </button>
        </div>
      </form>
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>
    </div>
  );
}

/** Each person's own ERPNext key per business, used when they approve from the platform. */
export function SettingsCredentials() {
  const { data, error, loading, reload } = useApi(() => settingsApi.credentials(), []);
  const [editing, setEditing] = useState(null); // {} for a new one, or a row
  const [removing, setRemoving] = useState(null);
  const [tests, setTests] = useState({});

  if (loading && !data) return <Loading what="Reading the personal keys" />;
  if (error && !data) return <Failed error={error} onRetry={reload} what="the personal keys" />;
  const rows = data || [];

  const test = async (row) => {
    setTests((t) => ({ ...t, [row.name]: { busy: true } }));
    try {
      const out = await settingsApi.testCredential(row.name);
      setTests((t) => ({ ...t, [row.name]: { [out.ok ? "ok" : "bad"]: out.says } }));
    } catch (e) {
      setTests((t) => ({ ...t, [row.name]: { bad: e?.message || "The test did not run." } }));
    }
  };

  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>ERPNext API Keys</b>
          <span>A person's own key on a business's ERPNext, so what they approve here is done as them there.</span>
        </div>
        <button className="btn pri" onClick={() => setEditing({})}>Add Key</button>
      </div>
      {rows.length ? (
        <table className="dt">
          <thead>
            <tr>
              <th>Person</th>
              <th>Business</th>
              <th>API key</th>
              <th>Secret</th>
              <th>Last used</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name}>
                <td>{r.person}<span className="st-sub">{r.user}</span></td>
                <td>{r.business_name}</td>
                <td className="st-dim">{r.api_key || "Not set"}</td>
                <td>{r.has_secret ? <span className="tag t-ok">Stored</span> : <span className="tag t-od">Missing</span>}</td>
                <td className="st-nowrap st-dim">
                  {when(r.last_used)}
                  {tests[r.name]?.ok ? <span className="st-sub" style={{ color: "var(--ok)" }}>{tests[r.name].ok}</span> : null}
                  {tests[r.name]?.bad ? <span className="st-sub" style={{ color: "var(--crit)" }}>{tests[r.name].bad}</span> : null}
                </td>
                <td>
                  <div className="st-acts">
                    <button className="btn" disabled={tests[r.name]?.busy} onClick={() => test(r)}>
                      {tests[r.name]?.busy ? "Testing…" : "Test"}
                    </button>
                    <button className="btn" onClick={() => setEditing(r)}>Replace</button>
                    <button className="btn dgr" onClick={() => setRemoving(r)}>Remove</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="thin">No personal keys yet. They are needed only for approving from the platform.</div>
      )}
      {editing ? <EditCredential row={editing} onClose={() => setEditing(null)} onDone={reload} /> : null}
      {removing ? <RemoveCredential row={removing} onClose={() => setRemoving(null)} onDone={reload} /> : null}
    </div>
  );
}

function EditCredential({ row, onClose, onDone }) {
  const isNew = !row.name;
  const people = useApi(() => (isNew ? settingsApi.people() : Promise.resolve([])), []);
  const businesses = useApi(() => (isNew ? settingsApi.businesses() : Promise.resolve([])), []);
  // Someone given Personal ERPNext Keys manages managers' keys, not administrators'.
  const meAdmin = (people.data || []).some((p) => p.is_me && p.is_admin);
  const [f, setF] = useState({ user: row.user || "", business_code: row.business_code || "", api_key: "", api_secret: "" });
  const [st, setSt] = useState({});
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => settingsApi.setCredential(f));
    if (out) {
      onDone();
      onClose();
    }
  };

  return (
    <Dialog title={isNew ? "Add Key" : "Replace Key"}
      sub={isNew ? "The API key and secret of this person's own user on that ERPNext." : `${row.person} on ${row.business_name}`}
      onClose={onClose}>
      <form onSubmit={save}>
        {isNew ? (
          <>
            <label htmlFor="ck-user">Person</label>
            <select id="ck-user" value={f.user} onChange={set("user")} required>
              <option value="">Choose…</option>
              {(people.data || []).filter((p) => p.active && (meAdmin || !p.is_admin)).map((p) => (
                <option key={p.username} value={p.username}>{p.full_name} ({p.email})</option>
              ))}
            </select>
            <label htmlFor="ck-biz">Business</label>
            <select id="ck-biz" value={f.business_code} onChange={set("business_code")} required>
              <option value="">Choose…</option>
              {(businesses.data || []).filter((b) => !b.is_local).map((b) => (
                <option key={b.business_code} value={b.business_code}>{b.business_name}</option>
              ))}
            </select>
          </>
        ) : null}
        <label htmlFor="ck-key">API key</label>
        <input id="ck-key" autoComplete="off" value={f.api_key} onChange={set("api_key")}
          placeholder={isNew ? "" : `Leave blank to keep ${row.api_key || "the current one"}`} required={isNew} />
        <label htmlFor="ck-secret">API secret</label>
        <input id="ck-secret" type="password" autoComplete="new-password" value={f.api_secret} onChange={set("api_secret")}
          placeholder={isNew ? "" : "Leave blank to keep the stored one"} required={isNew} />
        <p className="dlg-hint">The secret is stored encrypted and is never shown again.</p>
        {st.bad ? <div className="dlg-err" role="alert">{st.bad}</div> : null}
        <div className="dlg-acts">
          <button type="button" className="ap-act" onClick={onClose}>Cancel</button>
          <button type="submit" className="ap-act pri" disabled={st.busy}>{st.busy ? "Saving…" : "Save Key"}</button>
        </div>
      </form>
    </Dialog>
  );
}

function RemoveCredential({ row, onClose, onDone }) {
  const [st, setSt] = useState({});
  const remove = async () => {
    const out = await act(setSt, () => settingsApi.removeCredential(row.name));
    if (out) {
      onDone();
      onClose();
    }
  };
  return (
    <Dialog title="Remove Key" sub={`${row.person}'s key for ${row.business_name}.`} onClose={onClose}>
      <p className="dlg-hint">
        They will not be able to approve on {row.business_name} from the platform until a key is added again.
        The key itself still exists on that ERPNext; revoke it there if it is no longer needed.
      </p>
      {st.bad ? <div className="dlg-err" role="alert">{st.bad}</div> : null}
      <div className="dlg-acts">
        <button type="button" className="ap-act" onClick={onClose}>Cancel</button>
        <button type="button" className="ap-act failed" disabled={st.busy} onClick={remove}>
          {st.busy ? "Removing…" : "Remove Key"}
        </button>
      </div>
    </Dialog>
  );
}

/** Every change made from Settings: who, when and what (never a secret). */
export function SettingsChanges() {
  const { data, error, loading, reload } = useApi(() => settingsApi.changes(), []);
  if (loading && !data) return <Loading what="Reading the changes" />;
  if (error && !data) return <Failed error={error} onRetry={reload} what="the changes" />;
  const rows = data || [];
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Changes</b>
          <span>The latest changes made in Settings, newest first. Secrets are never recorded.</span>
        </div>
        <button className="btn" onClick={reload}>Refresh</button>
      </div>
      {rows.length ? (
        <table className="dt">
          <thead>
            <tr><th>When</th><th>Who</th><th>What</th></tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="st-nowrap st-dim">{when(r.when)}</td>
                <td className="st-nowrap">{r.who}</td>
                <td>{r.what}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="thin">No changes have been made in Settings yet.</div>
      )}
    </div>
  );
}
