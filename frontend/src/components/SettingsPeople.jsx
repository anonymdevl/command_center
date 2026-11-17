import React, { useState } from "react";
import { plansApi, settingsApi } from "../api/client.js";
import { useApi } from "../useApi.js";
import { Failed, Loading } from "./States.jsx";
import { Dialog, Msg, act, when } from "./SettingsParts.jsx";

const RULES =
  "At least 10 characters. Not a common password, not only numbers, and not too like their name or email.";

/** The Settings sections an administrator can give a manager (platform_settings.GRANTS). */
const GRANTS = [
  ["businesses", "Businesses", "add, edit, test, pause and reload businesses"],
  ["people", "User Management", "add managers, deactivate and reactivate them, reset their passwords"],
  ["keys", "ERPNext API Keys", "add, replace and remove managers' personal keys"],
];
const GRANT_LABEL = Object.fromEntries(GRANTS.map(([k, label]) => [k, label]));

function accessWords(p) {
  if (p.is_admin) return "All";
  return (p.settings_access || []).map((k) => GRANT_LABEL[k] || k).join(", ");
}

/** Everyone who can sign in: who manages, who administers, who is switched off. */
export default function SettingsPeople() {
  const { data, error, loading, reload } = useApi(() => settingsApi.people(), []);
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState(null);

  if (loading && !data) return <Loading what="Reading the people" />;
  if (error) return <Failed error={error} onRetry={reload} what="the people" />;
  const rows = data || [];
  const managers = rows.filter((p) => p.active && p.is_manager).length;
  // The administrator sees everything here; someone given People sees managers only.
  const meAdmin = rows.some((p) => p.is_me && p.is_admin);
  const admins = rows.filter((p) => p.active && p.is_admin).length;

  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>People</b>
          <span>
            {rows.length} {rows.length === 1 ? "person" : "people"} · {managers} active{" "}
            {managers === 1 ? "manager" : "managers"} · {admins} active{" "}
            {admins === 1 ? "administrator" : "administrators"}
          </span>
        </div>
        <button className="btn pri" onClick={() => setAdding(true)}>Add Person</button>
      </div>
      <table className="dt">
        <thead>
          <tr>
            <th>Person</th>
            <th>Manager</th>
            <th>Administrator</th>
            <th>Settings</th>
            <th>Status</th>
            <th>Last sign-in</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.username}>
              <td>
                {p.full_name}
                {p.is_me ? <span className="st-dim"> (you)</span> : null}
                <span className="st-sub">{p.email}{p.customers?.length ? ` · ${p.customers.join(", ")}` : ""}</span>
              </td>
              <td>{p.is_manager ? <span className="tag t-ok">Yes</span> : <span className="st-dim">No</span>}</td>
              <td>{p.is_admin ? <span className="tag t-ok">Yes</span> : <span className="st-dim">No</span>}</td>
              <td>{accessWords(p) ? accessWords(p) : <span className="st-dim">No</span>}</td>
              <td>
                {p.active ? <span className="tag t-ok">Active</span> : <span className="tag t-dr">Deactivated</span>}
                {!p.has_password ? <span className="st-sub">No password yet</span> : null}
              </td>
              <td className="st-nowrap st-dim">{when(p.last_login)}</td>
              <td>
                <div className="st-acts">
                  <button className="btn" onClick={() => setOpen(p.username)}>Manage</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {adding ? <AddPerson meAdmin={meAdmin} onClose={() => setAdding(false)} onDone={reload} /> : null}
      {open ? (
        <ManagePerson
          meAdmin={meAdmin}
          person={rows.find((p) => p.username === open)}
          onClose={() => setOpen(null)}
          onDone={reload}
        />
      ) : null}
    </div>
  );
}

function AddPerson({ meAdmin, onClose, onDone }) {
  const [f, setF] = useState({ email: "", full_name: "", password: "", password2: "", later: false,
    manager: true, admin: false, client_id: "", override: false });
  const [st, setSt] = useState({});
  const [made, setMade] = useState(null);
  // The customers whose seat the new person may take (insights/core/plans.py): every one
  // for the administrator, the delegate's own for a delegate.
  const { data: customers } = useApi(() => plansApi.clientChoices(), []);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => settingsApi.addPerson({
      email: f.email, full_name: f.full_name, password: f.later ? "" : f.password,
      password2: f.later ? "" : f.password2, set_later: f.later ? 1 : 0,
      manager: f.manager ? 1 : 0, admin: meAdmin && f.admin ? 1 : 0,
      client_id: f.client_id || undefined, override_seats: meAdmin && f.override ? 1 : 0,
    }));
    if (out) {
      setMade(out);
      onDone();
    }
  };

  if (made) {
    return (
      <Dialog title="Person added" onClose={onClose}>
        <p className="dlg-sub">
          {made.full_name} ({made.email}) can{" "}
          {made.has_password
            ? "now sign in with their email and the password you set. Tell them the password yourself; no email is sent."
            : "sign in with their business's ERPNext. Set a password for them later from Manage if they need one."}
        </p>
        <div className="dlg-acts">
          <button type="button" className="ap-act pri" onClick={onClose}>Done</button>
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog title="Add Person" sub="They can use the platform once they are a manager." onClose={onClose}>
      <form onSubmit={save}>
        <label htmlFor="sp-email">Email</label>
        <input id="sp-email" type="email" autoComplete="off" value={f.email} onChange={set("email")} required />
        <label htmlFor="sp-name">Full name</label>
        <input id="sp-name" autoComplete="off" value={f.full_name} onChange={set("full_name")} required />

        <div className="st-choice" role="radiogroup" aria-label="Password">
          <label className="st-check">
            <input type="radio" name="sp-pw" checked={!f.later} onChange={() => setF((x) => ({ ...x, later: false }))} />
            <span>Set a password now</span>
          </label>
          <label className="st-check">
            <input type="radio" name="sp-pw" checked={f.later} onChange={() => setF((x) => ({ ...x, later: true }))} />
            <span>Set it later</span>
          </label>
        </div>
        {!f.later ? (
          <>
            <label htmlFor="sp-pw1">Password</label>
            <input id="sp-pw1" type="password" autoComplete="new-password" value={f.password} onChange={set("password")} />
            <label htmlFor="sp-pw2">Type it again</label>
            <input id="sp-pw2" type="password" autoComplete="new-password" value={f.password2} onChange={set("password2")} />
            <p className="dlg-hint">{RULES}</p>
          </>
        ) : (
          <p className="dlg-hint">Until a password is set they can only sign in with their business's ERPNext.</p>
        )}

        <label className="st-check">
          <input type="checkbox" checked={f.manager} onChange={set("manager")} />
          <span>Manager: can use the platform</span>
        </label>
        {meAdmin ? (
          <label className="st-check">
            <input type="checkbox" checked={f.admin} onChange={set("admin")} />
            <span>Administrator: can also open all of Settings</span>
          </label>
        ) : null}

        {customers?.length && !(meAdmin && f.admin) ? (
          meAdmin ? (
            <>
              <label htmlFor="sp-cust">Customer</label>
              <select id="sp-cust" value={f.client_id} onChange={set("client_id")}>
                <option value="">None: takes no customer&apos;s seat</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.seats_used} of {c.seats ?? "unlimited"} seats in use)
                  </option>
                ))}
              </select>
              {f.client_id ? (
                <label className="st-check">
                  <input type="checkbox" checked={f.override} onChange={set("override")} />
                  <span>Allow beyond the customer&apos;s seat limit</span>
                </label>
              ) : null}
            </>
          ) : (
            <p className="dlg-hint">
              They take one of {customers[0].name}&apos;s seats ({customers[0].seats_used} of{" "}
              {customers[0].seats ?? "unlimited"} in use).
            </p>
          )
        ) : null}

        {st.bad ? <div className="dlg-err" role="alert">{st.bad}</div> : null}
        <div className="dlg-acts">
          <button type="button" className="ap-act" onClick={onClose}>Cancel</button>
          <button type="submit" className="ap-act pri" disabled={st.busy}>{st.busy ? "Adding…" : "Add Person"}</button>
        </div>
      </form>
    </Dialog>
  );
}

function ManagePerson({ meAdmin, person, onClose, onDone }) {
  const [p, setP] = useState(person);
  const [name, setName] = useState(person?.full_name || "");
  const [st, setSt] = useState({});
  const [pw, setPw] = useState({ password: "", password2: "", later: false });
  const [pwSt, setPwSt] = useState({});
  if (!p) return null;
  // Someone given People can change managers only: not an administrator, not anyone
  // with Settings access, and of themselves only their password (the server says so too).
  const locked = !meAdmin && p.protected && !p.is_me;
  const ownOnly = !meAdmin && p.is_me;

  const run = async (fn, okText) => {
    const out = await act(setSt, fn, okText);
    if (out) {
      setP(out);
      onDone();
    }
  };

  const savePw = async (e) => {
    e.preventDefault();
    const out = await act(setPwSt, () => settingsApi.resetPassword({
      username: p.username, password: pw.later ? "" : pw.password,
      password2: pw.later ? "" : pw.password2, set_later: pw.later ? 1 : 0,
    }), pw.later
      ? "Their password is removed. They can sign in only with their business's ERPNext."
      : p.is_me ? "Your password is changed." : "Password changed. They have been signed out everywhere; tell them the new one yourself.");
    if (out) {
      setP(out);
      setPw({ password: "", password2: "", later: false });
      onDone();
    }
  };

  return (
    <Dialog title={p.full_name} sub={p.email} onClose={onClose} wide>
      <dl className="st-facts" style={{ marginTop: 14 }}>
        <dt>Status</dt><dd>{p.active ? "Active" : "Deactivated: cannot sign in"}</dd>
        <dt>Manager</dt><dd>{p.is_manager ? "Yes: can use the platform" : "No"}</dd>
        <dt>Administrator</dt><dd>{p.is_admin ? "Yes: can open all of Settings" : "No"}</dd>
        <dt>Settings</dt><dd>{accessWords(p) || "No access"}</dd>
        <dt>Password</dt><dd>{p.has_password ? "Set" : "Not set"}</dd>
        <dt>Last sign-in</dt><dd>{when(p.last_login)}</dd>
      </dl>

      {locked ? (
        <Msg tone="note">
          Only the platform's administrator can change {p.is_admin ? "an administrator" : "someone who has access to Settings"}.
        </Msg>
      ) : null}
      {ownOnly ? (
        <Msg tone="note">You can change your own password here. Anything else about you is changed by the platform's administrator.</Msg>
      ) : null}

      {!locked && !ownOnly ? (
      <div className="dlg-acts" style={{ justifyContent: "flex-start" }}>
        <button type="button" className="ap-act" disabled={st.busy}
          onClick={() => run(() => settingsApi.setManager(p.username, !p.is_manager),
            p.is_manager ? "No longer a manager." : "Now a manager.")}>
          {p.is_manager ? "Remove Manager" : "Make Manager"}
        </button>
        {meAdmin ? (
          <button type="button" className="ap-act" disabled={st.busy || (p.is_me && p.is_admin)}
            title={p.is_me && p.is_admin ? "Another administrator has to do this" : undefined}
            onClick={() => run(() => settingsApi.setAdmin(p.username, !p.is_admin),
              p.is_admin ? "No longer an administrator." : "Now an administrator.")}>
            {p.is_admin ? "Remove Administrator" : "Make Administrator"}
          </button>
        ) : null}
        <button type="button" className={`ap-act${p.active ? " failed" : ""}`} disabled={st.busy || p.is_me}
          title={p.is_me ? "Another administrator has to do this" : undefined}
          onClick={() => run(() => settingsApi.setActive(p.username, !p.active),
            p.active ? "Deactivated. They have been signed out and cannot sign in." : "Reactivated.")}>
          {p.active ? "Deactivate" : "Reactivate"}
        </button>
      </div>
      ) : null}
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>

      {meAdmin && !p.is_admin ? (
        <SettingsAccess person={p} onSaved={(out) => { setP(out); onDone(); }} />
      ) : null}

      {!locked && !ownOnly ? (
      <div className="dlg-sec">
        <h4>Name</h4>
        <form onSubmit={(e) => { e.preventDefault(); run(() => settingsApi.updatePerson(p.username, name), "Name saved."); }}>
          <label htmlFor="mp-name">Full name</label>
          <input id="mp-name" value={name} onChange={(e) => setName(e.target.value)} />
          <div className="dlg-acts">
            <button type="submit" className="ap-act" disabled={st.busy || !name.trim() || name === p.full_name}>Save Name</button>
          </div>
        </form>
      </div>
      ) : null}

      {!locked ? (
      <div className="dlg-sec">
        <h4>Reset Password</h4>
        <form onSubmit={savePw}>
          <div className="st-choice" role="radiogroup" aria-label="Password">
            <label className="st-check">
              <input type="radio" name="mp-pw" checked={!pw.later} onChange={() => setPw((x) => ({ ...x, later: false }))} />
              <span>Set a new password</span>
            </label>
            {!p.is_me ? (
              <label className="st-check">
                <input type="radio" name="mp-pw" checked={pw.later} onChange={() => setPw((x) => ({ ...x, later: true }))} />
                <span>Remove it (set later)</span>
              </label>
            ) : null}
          </div>
          {!pw.later ? (
            <>
              <label htmlFor="mp-pw1">New password</label>
              <input id="mp-pw1" type="password" autoComplete="new-password" value={pw.password}
                onChange={(e) => setPw((x) => ({ ...x, password: e.target.value }))} />
              <label htmlFor="mp-pw2">Type it again</label>
              <input id="mp-pw2" type="password" autoComplete="new-password" value={pw.password2}
                onChange={(e) => setPw((x) => ({ ...x, password2: e.target.value }))} />
              <p className="dlg-hint">{RULES}</p>
            </>
          ) : null}
          <Msg tone="ok">{pwSt.ok}</Msg>
          <Msg tone="bad">{pwSt.bad}</Msg>
          <div className="dlg-acts">
            <button type="submit" className="ap-act" disabled={pwSt.busy}>
              {pwSt.busy ? "Saving…" : pw.later ? "Remove Password" : "Set Password"}
            </button>
          </div>
        </form>
      </div>
      ) : null}

      <div className="dlg-acts">
        <button type="button" className="ap-act pri" onClick={onClose}>Done</button>
      </div>
    </Dialog>
  );
}

/** Administrator only: which Settings sections this manager may open. */
function SettingsAccess({ person, onSaved }) {
  const [on, setOn] = useState(person.settings_access || []);
  const [st, setSt] = useState({});
  const same = [...on].sort().join() === [...(person.settings_access || [])].sort().join();
  const canHave = person.is_manager && person.active;

  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => settingsApi.setSettingsAccess(person.username, on),
      on.length
        ? "Access saved. They see Settings in their sidebar the next time they open or reload the platform."
        : "Access taken away. Settings is no longer open to them.");
    if (out) onSaved(out);
  };

  return (
    <div className="dlg-sec">
      <h4>Settings Access</h4>
      <p className="dlg-hint">
        {canHave
          ? "Let them use parts of Settings. They can never make anyone an administrator, give Settings access, or change an administrator. The Claude key and email stay with you."
          : person.active
            ? "Make them a manager first; only managers can be given parts of Settings."
            : "Reactivate them first; only active managers can be given parts of Settings."}
      </p>
      <form onSubmit={save}>
        {GRANTS.map(([key, label, does]) => (
          <label className="st-check" key={key}>
            <input type="checkbox" checked={on.includes(key)} disabled={!canHave && !on.includes(key)}
              onChange={(e) => setOn((x) => (e.target.checked ? [...x, key] : x.filter((k) => k !== key)))} />
            <span>{label}: {does}</span>
          </label>
        ))}
        <Msg tone="ok">{st.ok}</Msg>
        <Msg tone="bad">{st.bad}</Msg>
        <div className="dlg-acts">
          <button type="submit" className="ap-act" disabled={st.busy || same}>
            {st.busy ? "Saving…" : "Save Access"}
          </button>
        </div>
      </form>
    </div>
  );
}
