import React, { useState } from "react";
import { plansApi, settingsApi } from "../api/client.js";
import { useApi } from "../useApi.js";
import { Failed, Loading } from "./States.jsx";
import { Dialog, Msg, act, when } from "./SettingsParts.jsx";

/**
 * User Management says no more than it has to (Michael, 17 Nov 2026: "You're too chatty
 * with the interface"): headings, column labels, field labels and buttons, and one short
 * line when something is done or refused. Password rules, what a choice will do and why a
 * control is missing are not explained here; the server's refusal says what was wrong.
 * scripts/preflight.py keeps hint paragraphs and sub-lines out of this page.
 */

/** How a new person gets their password (platform_settings.add_person). */
const PW_CHOICES = [
  ["now", "Set Password Now"],
  ["invite", "Email a Set-Password Link"],
  ["later", "Set Later"],
];

/** The Settings sections an administrator can give a manager (platform_settings.GRANTS). */
const GRANTS = [
  ["businesses", "Businesses"],
  ["people", "User Management"],
  ["keys", "ERPNext API Keys"],
];
const GRANT_LABEL = Object.fromEntries(GRANTS);

function accessWords(p) {
  if (p.is_admin) return "All";
  return (p.settings_access || []).map((k) => GRANT_LABEL[k] || k).join(", ");
}

/**
 * Anyone with Settings access, in any section, is a kind of administrator, and the list
 * says Yes for them -- only Yes: which sections they may open is in Manage, not in the
 * table, where it made one row unlike the rest (17 Nov 2026).
 */
function AdminCell({ p }) {
  const yes = p.settings_admin ?? (p.is_admin || (p.settings_access || []).length > 0);
  return yes ? <span className="tag t-ok">Yes</span> : <span className="st-dim">No</span>;
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
  // The administrator sees everyone here; someone given User Management sees the people of
  // their own customer, never an administrator (the server leaves them out).
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
              <td><AdminCell p={p} /></td>
              <td>{p.active ? <span className="tag t-ok">Active</span> : <span className="tag t-dr">Deactivated</span>}</td>
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
  // pw: "now" (typed here), "invite" (they are emailed a link to set their own) or "later".
  const [f, setF] = useState({ email: "", full_name: "", password: "", password2: "", pw: "now",
    manager: true, admin: false, client_id: "", override: false });
  const [st, setSt] = useState({});
  const [made, setMade] = useState(null);
  // The customers whose seat the new person may take (insights/core/plans.py): every one
  // for the administrator, the delegate's own for a delegate.
  const { data: customers } = useApi(() => plansApi.clientChoices(), []);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  const save = async (e) => {
    e.preventDefault();
    const typed = f.pw === "now";
    const out = await act(setSt, () => settingsApi.addPerson({
      email: f.email, full_name: f.full_name, password: typed ? f.password : "",
      password2: typed ? f.password2 : "", set_later: f.pw === "later" ? 1 : 0,
      invite: f.pw === "invite" ? 1 : 0,
      manager: f.manager ? 1 : 0, admin: meAdmin && f.admin ? 1 : 0,
      client_id: f.client_id || undefined, override_seats: meAdmin && f.override ? 1 : 0,
    }));
    if (out) {
      setMade(out);
      onDone();
    }
  };

  if (made) {
    const inv = made.invite;
    return (
      <Dialog title="Person Added" onClose={onClose}>
        <p className="dlg-sub">{made.full_name} ({made.email}) is added.</p>
        {inv && !made.has_password ? (
          <>
            <Msg tone={inv.ok ? "ok" : "bad"}>{inv.says}</Msg>
            {!inv.ok ? (
              <PasswordNow person={made} onSet={(p) => { setMade({ ...p, invite: inv }); onDone(); }} />
            ) : null}
          </>
        ) : null}
        <div className="dlg-acts">
          <button type="button" className="ap-act pri" onClick={onClose}>Done</button>
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog title="Add Person" onClose={onClose}>
      <form onSubmit={save}>
        <label htmlFor="sp-email">Email</label>
        <input id="sp-email" type="email" autoComplete="off" value={f.email} onChange={set("email")} required />
        <label htmlFor="sp-name">Full Name</label>
        <input id="sp-name" autoComplete="off" value={f.full_name} onChange={set("full_name")} required />

        <div className="st-choice" role="radiogroup" aria-label="Password">
          {PW_CHOICES.map(([key, label]) => (
            <label className="st-check" key={key}>
              <input type="radio" name="sp-pw" checked={f.pw === key} onChange={() => setF((x) => ({ ...x, pw: key }))} />
              <span>{label}</span>
            </label>
          ))}
        </div>
        {f.pw === "now" ? (
          <>
            <label htmlFor="sp-pw1">Password</label>
            <input id="sp-pw1" type="password" autoComplete="new-password" value={f.password} onChange={set("password")} />
            <label htmlFor="sp-pw2">Confirm Password</label>
            <input id="sp-pw2" type="password" autoComplete="new-password" value={f.password2} onChange={set("password2")} />
          </>
        ) : null}

        <label className="st-check">
          <input type="checkbox" checked={f.manager} onChange={set("manager")} />
          <span>Manager</span>
        </label>
        {meAdmin ? (
          <label className="st-check">
            <input type="checkbox" checked={f.admin} onChange={set("admin")} />
            <span>Administrator</span>
          </label>
        ) : null}

        {customers?.length && meAdmin && !f.admin ? (
            <>
              <label htmlFor="sp-cust">Customer</label>
              <select id="sp-cust" value={f.client_id} onChange={set("client_id")}>
                <option value="">None</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.seats_used} of {c.seats ?? "unlimited"} seats in use)
                  </option>
                ))}
              </select>
              {f.client_id ? (
                <label className="st-check">
                  <input type="checkbox" checked={f.override} onChange={set("override")} />
                  <span>Allow Beyond Seat Limit</span>
                </label>
              ) : null}
            </>
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

/** After an invite that could not be sent: set a password for them now instead. */
function PasswordNow({ person, onSet }) {
  const [pw, setPw] = useState({ password: "", password2: "" });
  const [st, setSt] = useState({});
  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => settingsApi.resetPassword({
      username: person.username, password: pw.password, password2: pw.password2, set_later: 0,
    }), "Password set.");
    if (out) onSet(out);
  };
  if (person.has_password) return <Msg tone="ok">Password set.</Msg>;
  return (
    <form className="dlg-sec" onSubmit={save}>
      <h4>Set a Password Instead</h4>
      <label htmlFor="pn-pw1">Password</label>
      <input id="pn-pw1" type="password" autoComplete="new-password" value={pw.password}
        onChange={(e) => setPw((x) => ({ ...x, password: e.target.value }))} />
      <label htmlFor="pn-pw2">Confirm Password</label>
      <input id="pn-pw2" type="password" autoComplete="new-password" value={pw.password2}
        onChange={(e) => setPw((x) => ({ ...x, password2: e.target.value }))} />
      <Msg tone="bad">{st.bad}</Msg>
      <div className="dlg-acts">
        <button type="submit" className="ap-act" disabled={st.busy}>{st.busy ? "Saving…" : "Set Password"}</button>
      </div>
    </form>
  );
}

function ManagePerson({ meAdmin, person, onClose, onDone }) {
  const [p, setP] = useState(person);
  const [name, setName] = useState(person?.full_name || "");
  const [st, setSt] = useState({});
  const [pw, setPw] = useState({ password: "", password2: "", later: false });
  const [pwSt, setPwSt] = useState({});
  const [link, setLink] = useState({});
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
    }), pw.later ? "Password removed." : "Password changed.");
    if (out) {
      setP(out);
      setPw({ password: "", password2: "", later: false });
      onDone();
    }
  };

  // A link by email to set their own password (also the answer to a forgotten one).
  // Never claimed sent when it was not: the server's own sentence is shown either way.
  const sendLink = async () => {
    const out = await act(setLink, () => settingsApi.sendSetPasswordLink(p.username),
      (o) => (o.ok ? o.says : undefined));
    if (out && !out.ok) setLink({ bad: out.says });
  };

  return (
    <Dialog title={p.full_name} sub={p.email} onClose={onClose} wide>
      <dl className="st-facts" style={{ marginTop: 14 }}>
        <dt>Status</dt><dd>{p.active ? "Active" : "Deactivated"}</dd>
        <dt>Manager</dt><dd>{p.is_manager ? "Yes" : "No"}</dd>
        <dt>Administrator</dt><dd>{p.is_admin || (p.settings_access || []).length ? "Yes" : "No"}</dd>
        <dt>Settings</dt><dd>{accessWords(p) || "None"}</dd>
        <dt>Password</dt><dd>{p.has_password ? "Set" : "Not set"}</dd>
        <dt>Last sign-in</dt><dd>{when(p.last_login)}</dd>
      </dl>

      {!locked && !ownOnly ? (
      <div className="dlg-acts" style={{ justifyContent: "flex-start" }}>
        <button type="button" className="ap-act" disabled={st.busy}
          onClick={() => run(() => settingsApi.setManager(p.username, !p.is_manager),
            p.is_manager ? "Manager removed." : "Made a manager.")}>
          {p.is_manager ? "Remove Manager" : "Make Manager"}
        </button>
        {meAdmin ? (
          <button type="button" className="ap-act" disabled={st.busy || (p.is_me && p.is_admin)}
            title={p.is_me && p.is_admin ? "Another administrator has to do this" : undefined}
            onClick={() => run(() => settingsApi.setAdmin(p.username, !p.is_admin),
              p.is_admin ? "Administrator removed." : "Made an administrator.")}>
            {p.is_admin ? "Remove Administrator" : "Make Administrator"}
          </button>
        ) : null}
        <button type="button" className={`ap-act${p.active ? " failed" : ""}`} disabled={st.busy || p.is_me}
          title={p.is_me ? "Another administrator has to do this" : undefined}
          onClick={() => run(() => settingsApi.setActive(p.username, !p.active),
            p.active ? "Deactivated." : "Reactivated.")}>
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
          <label htmlFor="mp-name">Full Name</label>
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
              <span>Set New Password</span>
            </label>
            {!p.is_me ? (
              <label className="st-check">
                <input type="radio" name="mp-pw" checked={pw.later} onChange={() => setPw((x) => ({ ...x, later: true }))} />
                <span>Remove Password</span>
              </label>
            ) : null}
          </div>
          {!pw.later ? (
            <>
              <label htmlFor="mp-pw1">New Password</label>
              <input id="mp-pw1" type="password" autoComplete="new-password" value={pw.password}
                onChange={(e) => setPw((x) => ({ ...x, password: e.target.value }))} />
              <label htmlFor="mp-pw2">Confirm Password</label>
              <input id="mp-pw2" type="password" autoComplete="new-password" value={pw.password2}
                onChange={(e) => setPw((x) => ({ ...x, password2: e.target.value }))} />
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

      {!locked && !p.is_me ? (
      <div className="dlg-sec">
        <h4>Set-Password Link</h4>
        <Msg tone="ok">{link.ok}</Msg>
        <Msg tone="bad">{link.bad}</Msg>
        <div className="dlg-acts">
          <button type="button" className="ap-act" disabled={link.busy || !p.active} onClick={sendLink}
            title={p.active ? undefined : "Reactivate them first"}>
            {link.busy ? "Sending…" : "Send Set-Password Link"}
          </button>
        </div>
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
      on.length ? "Access saved." : "Access removed.");
    if (out) onSaved(out);
  };

  return (
    <div className="dlg-sec">
      <h4>Settings Access</h4>
      <form onSubmit={save}>
        {GRANTS.map(([key, label]) => (
          <label className="st-check" key={key}
            title={canHave ? undefined : person.active ? "Make them a manager first" : "Reactivate them first"}>
            <input type="checkbox" checked={on.includes(key)} disabled={!canHave && !on.includes(key)}
              onChange={(e) => setOn((x) => (e.target.checked ? [...x, key] : x.filter((k) => k !== key)))} />
            <span>{label}</span>
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
