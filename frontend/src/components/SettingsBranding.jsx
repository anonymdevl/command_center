import React, { useEffect, useState } from "react";
import { readImage, settingsApi } from "../api/client.js";
import { useApi } from "../useApi.js";
import { Failed, Loading } from "./States.jsx";
import { Msg, act } from "./SettingsParts.jsx";

const FIELDS = [
  ["product_name", "Product name", "Shown in the sidebar, on the sign-in page, and on every PDF, workbook and email."],
  ["tagline", "Tagline", "The line under the name in the sidebar and on the sign-in page."],
  ["company", "Company", "Who built the product: every PDF page, workbook and email says so."],
  ["person", "Name and role", "Optional, for example a name and a title."],
  ["email", "Email", "Optional."],
  ["phone", "Phone", "Optional."],
  ["website", "Website", "Optional, for example www.example.com."],
];

const LOGOS = [
  ["logo_light", "Logo on light backgrounds", "Used on the PDFs, on paper and in the light theme."],
  ["logo_dark", "Logo on dark backgrounds", "Used in the dark theme. Leave empty to use the other one."],
  ["favicon", "Browser tab icon", "A small square image, at least 32 by 32 pixels."],
];

/** Administrator only: the product's name, tagline, logos and the vendor's footer. */
export default function SettingsBranding() {
  const { data, error, loading, reload } = useApi(() => settingsApi.brand(), []);
  if (loading && !data) return <Loading what="Reading the branding" />;
  if (error && !data) return <Failed error={error} onRetry={reload} what="the branding" />;
  return (
    <div className="st-stack">
      <BrandText data={data} onSaved={reload} />
      <BrandLogos data={data} onSaved={reload} />
    </div>
  );
}

function BrandText({ data, onSaved }) {
  const [f, setF] = useState(null);
  const [st, setSt] = useState({});
  useEffect(() => {
    if (data) setF(Object.fromEntries(FIELDS.map(([k]) => [k, data[k] || ""])));
  }, [data]);
  if (!f) return null;
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => settingsApi.setBrand(f),
      "Saved. Reload the page to see the new name in the sidebar; PDFs, workbooks and emails use it from now on.");
    if (out) onSaved();
  };
  const p = data.preview || {};
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Product and Vendor</b>
          <span>The name the platform carries, and who built it. A blank product name or company goes back to the default.</span>
        </div>
      </div>
      <form onSubmit={save}>
        <div className="st-form">
          {FIELDS.map(([k, label, hint]) => (
            <div key={k}>
              <label htmlFor={`br-${k}`}>{label}</label>
              <input id={`br-${k}`} autoComplete="off" value={f[k]} onChange={set(k)}
                maxLength={data.max_len?.[k] || 120}
                placeholder={data.defaults?.[k] || ""} type={k === "email" ? "email" : "text"} />
              <span className="st-sub">{hint}</span>
            </div>
          ))}
          <div>
            <button type="submit" className="btn pri" disabled={st.busy}>
              {st.busy ? "Saving…" : "Save Branding"}
            </button>
          </div>
        </div>
      </form>
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>
      <dl className="st-facts" style={{ marginTop: 18 }}>
        <dt>Every PDF page</dt>
        <dd>{p.footer} · Page 1 of 2</dd>
        <dt>Workbooks and emails</dt>
        <dd>{p.prepared}</dd>
      </dl>
    </div>
  );
}

function BrandLogos({ data, onSaved }) {
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Logos</b>
          <span>
            PNG, JPEG or WebP, at most {data.max_kb} KB. SVG is not accepted, because it can carry scripts.
            PDFs show PNG and JPEG logos; a WebP logo is shown on screen and the PDFs print the name instead.
          </span>
        </div>
      </div>
      <div className="st-logos">
        {LOGOS.map(([kind, label, hint]) => (
          <LogoSlot key={kind} label={label} hint={hint} url={data[`${kind}_url`]} maxKb={data.max_kb}
            dark={kind === "logo_dark"}
            onUpload={(dataUrl) => settingsApi.uploadBrandLogo(kind, dataUrl)}
            onRemove={() => settingsApi.removeBrandLogo(kind)}
            onSaved={onSaved} />
        ))}
      </div>
    </div>
  );
}

/** One logo: what is set now, Choose File, Remove. Shared with Businesses → Manage. */
export function LogoSlot({ label, hint, url, maxKb = 1024, dark = false, onUpload, onRemove, onSaved }) {
  const [st, setSt] = useState({});
  const choose = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const out = await act(setSt, async () => onUpload(await readImage(file, maxKb)),
      "Uploaded. Reload the page to see it everywhere.");
    if (out) onSaved(out);
  };
  const remove = async () => {
    const out = await act(setSt, onRemove, "Removed.");
    if (out) onSaved(out);
  };
  return (
    <div className="st-logo">
      <b>{label}</b>
      <span className="st-sub">{hint}</span>
      <div className={`st-logo-box${dark ? " dark" : ""}`}>
        {url ? <img src={url} alt={label} /> : <span className="st-dim">None</span>}
      </div>
      <div className="st-acts" style={{ justifyContent: "flex-start" }}>
        <label className="btn st-file">
          {st.busy ? "Uploading…" : url ? "Replace" : "Choose File"}
          <input type="file" accept="image/png,image/jpeg,image/webp" onChange={choose} disabled={st.busy} />
        </label>
        {url ? <button type="button" className="btn" onClick={remove} disabled={st.busy}>Remove</button> : null}
      </div>
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>
    </div>
  );
}
