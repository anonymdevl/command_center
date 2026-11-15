import React, { useEffect, useState } from "react";
import { settingsApi } from "../api/client.js";
import { useApi } from "../useApi.js";
import { Failed, Loading } from "./States.jsx";
import { Dialog, Msg, act, when } from "./SettingsParts.jsx";
import { LogoSlot } from "./SettingsBranding.jsx";

const STATUS_TAG = { Active: "t-ok", Paused: "t-dr", Unreachable: "t-od" };

function busy(b) {
  return b.loading || ["queued", "running"].includes(b.reload?.state);
}

/** The businesses the platform reads, how each was last loaded, and their keys. */
export default function SettingsBusinesses() {
  const { data, error, loading, reload } = useApi(() => settingsApi.businesses(), []);
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState(null);
  const rows = data || [];
  const anyBusy = rows.some(busy);

  // While a load runs, read the list again every few seconds to show its progress.
  useEffect(() => {
    if (!anyBusy) return undefined;
    const t = setInterval(reload, 4000);
    return () => clearInterval(t);
  }, [anyBusy, reload]);

  if (loading && !data) return <Loading what="Reading the connected businesses" />;
  if (error && !data) return <Failed error={error} onRetry={reload} what="the connected businesses" />;

  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Connected Businesses</b>
          <span>Each is read from its own ERPNext with a read-only key. Nothing is written back.</span>
        </div>
        <button className="btn pri" onClick={() => setAdding(true)}>Add Business</button>
      </div>
      {rows.length ? (
        <table className="dt">
          <thead>
            <tr>
              <th>Business</th>
              <th>ERPNext address</th>
              <th>Status</th>
              <th>Currency</th>
              <th>Last load</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => (
              <tr key={b.name}>
                <td>
                  {b.business_name}
                  {b.erpnext_company && b.erpnext_company !== b.business_name ? (
                    <span className="st-sub">{b.erpnext_company}</span>
                  ) : null}
                </td>
                <td className="st-dim">{b.is_local ? "This platform" : b.site_url || "Not set"}</td>
                <td>
                  <span className={`tag ${STATUS_TAG[b.status] || "t-dr"}`}>{b.status}</span>
                </td>
                <td className="st-dim">{b.currency || "—"}</td>
                <td><LastLoad b={b} /></td>
                <td>
                  <div className="st-acts">
                    <button className="btn" onClick={() => setOpen(b.name)}>Manage</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="thin">No business is connected yet. Add one with its ERPNext address and the API key and secret of a read-only user there.</div>
      )}

      {adding ? <AddBusiness onClose={() => setAdding(false)} onDone={reload} /> : null}
      {open ? (
        <ManageBusiness b={rows.find((x) => x.name === open)} onClose={() => setOpen(null)} onDone={reload} />
      ) : null}
    </div>
  );
}

function LastLoad({ b }) {
  if (busy(b)) {
    const r = b.reload;
    return (
      <span className="st-progress">
        <span className="spin" />
        {r && ["queued", "running"].includes(r.state)
          ? r.state === "queued" ? "Full reload starting…" : `Reloading: ${r.done || 0} of ${r.total} kinds of record`
          : "Loading changes now…"}
      </span>
    );
  }
  return (
    <span className="st-nowrap">
      {when(b.last_load)}
      {b.facts_failed ? (
        <span className="st-sub" style={{ color: "var(--crit)" }}>
          {b.facts_failed} of {b.facts_total} kinds of record did not load
        </span>
      ) : null}
      {b.reload?.state === "failed" ? (
        <span className="st-sub" style={{ color: "var(--crit)" }}>Last full reload failed: {b.reload.error}</span>
      ) : b.reload?.state === "done" ? (
        <span className="st-sub">Full reload finished {when(b.reload.finished)}</span>
      ) : null}
    </span>
  );
}

/** What check_access found: who the key reads as, what it can read, and whether it can write. */
function Access({ a }) {
  if (!a) return null;
  return (
    <>
      <Msg tone="ok">
        It reads as <b>{a.reads_as || "an unknown user"}</b> and can read {a.readable.length} of {a.total} kinds
        of record the platform needs.
      </Msg>
      {a.unreadable.length ? (
        <Msg tone="note">
          It cannot read: {a.unreadable.join(", ")}. Give its user read permission for these on that ERPNext,
          or the figures that need them stay empty.
        </Msg>
      ) : null}
      {a.write_capable_roles.length ? (
        <Msg tone="bad">
          Warning: its user can change records there ({a.write_capable_roles.join(", ")}). The platform only
          reads, but give that user read-only roles instead.
        </Msg>
      ) : a.read_only === null ? (
        <Msg tone="note">Its roles could not be read. Check on that ERPNext that its user holds read-only roles.</Msg>
      ) : null}
    </>
  );
}

/** Check Figures: each figure the screens rest on, from the platform and from ERPNext now. */
function FigureCheck({ c }) {
  const fmt = (v, unit) => (v === null || v === undefined ? "—"
    : unit === "count" ? Math.round(v).toLocaleString("en-GB")
      : Number(v).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const bad = c.lines.filter((x) => !x.ok).length;
  return (
    <div className="dlg-sec">
      <h4>Check Figures</h4>
      <Msg tone={bad ? "note" : "ok"}>
        {bad ? `${bad} of ${c.lines.length} figures differ from ERPNext.` : `All ${c.lines.length} figures agree with ERPNext.`}
        {` Figures as at ${c.as_of}; checked ${when(c.checked_at)}.`}
      </Msg>
      <div className="dt-scroll">
        <table className="dt">
          <thead>
            <tr>
              <th>Figure</th>
              <th style={{ textAlign: "right" }}>Platform</th>
              <th style={{ textAlign: "right" }}>ERPNext</th>
              <th style={{ textAlign: "right" }}>Difference</th>
              <th aria-label="Agrees" />
            </tr>
          </thead>
          <tbody>
            {c.lines.map((x) => (
              <tr key={x.key}>
                <td>
                  {x.check}
                  {x.reason ? <span className="st-sub">{x.reason}</span> : null}
                </td>
                <td className="num">{fmt(x.platform, x.unit)}</td>
                <td className="num">{fmt(x.erpnext, x.unit)}</td>
                <td className="num" style={x.ok ? undefined : { color: "var(--crit)" }}>{fmt(x.difference, x.unit)}</td>
                <td>
                  <span className={`tag ${x.ok ? "t-ok" : "t-od"}`}>{x.ok ? "✓" : "✗"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AddBusiness({ onClose, onDone }) {
  const [f, setF] = useState({ business_name: "", site_url: "https://", api_key: "", api_secret: "", erpnext_company: "" });
  const [st, setSt] = useState({});
  const [done, setDone] = useState(null);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => settingsApi.addBusiness(f));
    if (out) {
      setDone(out);
      onDone();
    }
  };

  if (done) {
    return (
      <Dialog title="Business connected" sub={`${done.business.business_name}${done.company ? `, company ${done.company}` : ""}${done.currency ? `, in ${done.currency}` : ""}.`} onClose={onClose} wide>
        <Access a={done.access} />
        <p className="dlg-hint">
          Its figures appear after a load: open Manage and press Reload Everything, or wait for the next
          fifteen-minute refresh. Reload the page to see it in the business switcher.
        </p>
        <div className="dlg-acts">
          <button type="button" className="ap-act pri" onClick={onClose}>Done</button>
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog title="Add Business" sub="Use the API key and secret of a read-only user on the business's ERPNext." onClose={onClose} wide>
      <form onSubmit={save}>
        <label htmlFor="ab-name">Business name</label>
        <input id="ab-name" autoComplete="off" value={f.business_name} onChange={set("business_name")} required />
        <label htmlFor="ab-url">ERPNext address</label>
        <input id="ab-url" autoComplete="off" value={f.site_url} onChange={set("site_url")} placeholder="https://erp.example.com" required />
        <label htmlFor="ab-key">API key</label>
        <input id="ab-key" autoComplete="off" value={f.api_key} onChange={set("api_key")} required />
        <label htmlFor="ab-secret">API secret</label>
        <input id="ab-secret" type="password" autoComplete="new-password" value={f.api_secret} onChange={set("api_secret")} required />
        <label htmlFor="ab-co">Company in ERPNext (optional)</label>
        <input id="ab-co" autoComplete="off" value={f.erpnext_company} onChange={set("erpnext_company")} placeholder="The first company there, if left blank" />
        <p className="dlg-hint">The secret is stored encrypted and is never shown again.</p>
        {st.bad ? <div className="dlg-err" role="alert">{st.bad}</div> : null}
        <div className="dlg-acts">
          <button type="button" className="ap-act" onClick={onClose}>Cancel</button>
          <button type="submit" className="ap-act pri" disabled={st.busy}>
            {st.busy ? "Connecting…" : "Connect Business"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

function ManageBusiness({ b, onClose, onDone }) {
  const [f, setF] = useState({ site_url: b?.site_url || "", api_key: "", api_secret: "" });
  const [st, setSt] = useState({});
  const [test, setTest] = useState(null);
  const [check, setCheck] = useState(null);
  if (!b) return null;
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => settingsApi.updateBusiness({
      name: b.name, site_url: f.site_url === b.site_url ? "" : f.site_url,
      api_key: f.api_key, api_secret: f.api_secret,
    }), "Saved. Press Test Connection to check it.");
    if (out) {
      setF((x) => ({ ...x, api_key: "", api_secret: "" }));
      onDone();
    }
  };
  const runCheck = async () => {
    setCheck(null);
    const out = await act(setSt, () => settingsApi.checkFigures(b.name));
    if (out) {
      setSt({});
      setCheck(out);
    }
  };
  const runTest = async () => {
    setTest(null);
    const out = await act(setSt, () => settingsApi.testBusiness(b.name));
    if (out) {
      setSt({});
      setTest(out);
      onDone();
    }
  };

  return (
    <Dialog title={b.business_name} sub={b.is_local ? "Its data is on this platform." : b.site_url} onClose={onClose} wide>
      <dl className="st-facts" style={{ marginTop: 14 }}>
        <dt>Status</dt>
        <dd>
          {b.status === "Unreachable"
            ? "Unreachable: the last attempt to read it failed. Test Connection says why."
            : b.status}
        </dd>
        <dt>Company</dt><dd>{b.erpnext_company || "—"}</dd>
        <dt>Currency</dt><dd>{b.currency || "—"}</dd>
        <dt>Last load</dt><dd>{when(b.last_load)}</dd>
        <dt>API key</dt><dd>{b.api_key || "Not set"}</dd>
        <dt>API secret</dt><dd>{b.has_secret ? "Stored" : "Not set"}</dd>
      </dl>

      <div className="dlg-acts" style={{ justifyContent: "flex-start" }}>
        {!b.is_local ? (
          <button type="button" className="ap-act" disabled={st.busy} onClick={runTest}>Test Connection</button>
        ) : null}
        <button type="button" className="ap-act" disabled={st.busy || busy(b) || b.status === "Paused"}
          title={b.status === "Paused" ? "Resume it first" : undefined}
          onClick={() => act(setSt, () => settingsApi.reloadBusiness(b.name),
            "Started. Every kind of record is being loaded again in the background; the list shows how far it has got.").then((o) => o && onDone())}>
          Reload Everything
        </button>
        <button type="button" className="ap-act" disabled={st.busy}
          onClick={() => act(setSt, () => settingsApi.setPaused(b.name, b.status !== "Paused"),
            b.status === "Paused" ? "Resumed. It is loaded again from the next refresh." : "Paused. It is not loaded and not offered on the screens until it is resumed.")
            .then((o) => o && onDone())}>
          {b.status === "Paused" ? "Resume" : "Pause"}
        </button>
        <button type="button" className="ap-act" disabled={st.busy || b.status === "Paused"}
          title="Compare the platform's figures with what this business's ERPNext says now"
          onClick={runCheck}>
          {st.busy && !check ? "Checking…" : "Check Figures"}
        </button>
      </div>
      {test ? <Msg tone={test.ok ? "ok" : "bad"}>{test.says}</Msg> : null}
      {check ? <FigureCheck c={check} /> : null}
      {test?.access ? <Access a={{ ...test.access }} /> : null}
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>

      {!b.is_local ? (
        <div className="dlg-sec">
          <h4>Change Address or Key</h4>
          <form onSubmit={save}>
            <label htmlFor="mb-url">ERPNext address</label>
            <input id="mb-url" autoComplete="off" value={f.site_url} onChange={set("site_url")} />
            <label htmlFor="mb-key">New API key</label>
            <input id="mb-key" autoComplete="off" value={f.api_key} onChange={set("api_key")}
              placeholder={b.api_key ? `Leave blank to keep ${b.api_key}` : "Not set"} />
            <label htmlFor="mb-secret">New API secret</label>
            <input id="mb-secret" type="password" autoComplete="new-password" value={f.api_secret} onChange={set("api_secret")}
              placeholder={b.has_secret ? "Leave blank to keep the stored one" : "Not set"} />
            <div className="dlg-acts">
              <button type="submit" className="ap-act" disabled={st.busy}>Save Changes</button>
            </div>
          </form>
        </div>
      ) : null}

      <CoBrand b={b} onDone={onDone} />

      <div className="dlg-acts">
        <button type="button" className="ap-act pri" onClick={onClose}>Done</button>
      </div>
    </Dialog>
  );
}

/** The name and logo this business's PDFs, workbooks and printouts are prepared for. */
function CoBrand({ b, onDone }) {
  const [name, setName] = useState(b.client_name || "");
  const [st, setSt] = useState({});
  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => settingsApi.setBusinessBrand(b.name, name),
      name.trim() ? "Saved. Its documents are prepared for this name from now on." : "Cleared. Its documents use its own name.");
    if (out) onDone();
  };
  return (
    <div className="dlg-sec">
      <h4>Co-Branding</h4>
      <p className="dlg-hint">
        Optional. Its PDFs, workbooks and printed screens say "Prepared for" this name, with its logo beside the product's.
      </p>
      <div className="st-cobrand">
        <form onSubmit={save}>
          <label htmlFor="mb-client">Display name</label>
          <input id="mb-client" autoComplete="off" value={name} maxLength={100}
            onChange={(e) => setName(e.target.value)} placeholder={b.business_name} />
          <div className="dlg-acts" style={{ justifyContent: "flex-start" }}>
            <button type="submit" className="ap-act" disabled={st.busy || name === (b.client_name || "")}>Save Name</button>
          </div>
          <Msg tone="ok">{st.ok}</Msg>
          <Msg tone="bad">{st.bad}</Msg>
        </form>
        <LogoSlot label="Client logo" hint="PNG or JPEG, on a light background." url={b.client_logo_url}
          onUpload={(dataUrl) => settingsApi.uploadBusinessLogo(b.name, dataUrl)}
          onRemove={() => settingsApi.removeBusinessLogo(b.name)}
          onSaved={onDone} />
      </div>
    </div>
  );
}
