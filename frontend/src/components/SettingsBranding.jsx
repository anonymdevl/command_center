import React, { useEffect, useState } from "react";
import { IMAGE_TYPES, PRINT_TYPES, readImage, settingsApi } from "../api/client.js";
import { useApi } from "../useApi.js";
import { Failed, Loading } from "./States.jsx";
import { Msg, act } from "./SettingsParts.jsx";
import LensMark from "./LensMark.jsx";

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
  ["logo_light", "Logo on light backgrounds", "Used in the light theme, and on PDFs when no Report Logo is set."],
  ["logo_dark", "Logo on dark backgrounds", "Used in the dark theme. Leave empty to use the other one."],
  ["favicon", "Browser tab icon", "A small square image, at least 32 by 32 pixels.", "icon"],
  ["logo_signin", "Sign-In Logo",
    "Shown on the sign-in page only, on light and dark. Leave empty to keep the built-in mark.", "mark"],
];

/** What an empty slot shows: the built-in mark or icon itself, as the page will show it.
 *  The icon is the file the browser tab gets (branding.DEFAULT_FAVICON, which the
 *  preview's favicon_url is while none is uploaded). */
function BuiltIn({ kind, data }) {
  if (kind === "icon") {
    const src = data.preview?.favicon_url;
    return src ? <img src={src} alt="Built-in icon" title="Built-in icon" />
      : <span className="st-dim">Built-in icon</span>;
  }
  return (
    <span className="logo" role="img" aria-label="Built-in mark" title="Built-in mark">
      <LensMark />
    </span>
  );
}

const REPORT_USES = {
  report: "PDFs print the Report Logo.",
  light: "No Report Logo is set, so PDFs print the logo for light backgrounds.",
  name: "No logo PDFs can show is set, so PDFs print the product name.",
};

/** Administrator only: the product's name, tagline, logos and the vendor's footer. */
export default function SettingsBranding() {
  const { data, error, loading, reload } = useApi(() => settingsApi.brand(), []);
  if (loading && !data) return <Loading what="Reading the branding" />;
  if (error && !data) return <Failed error={error} onRetry={reload} what="the branding" />;
  return (
    <div className="st-stack">
      <BrandText data={data} onSaved={reload} />
      <BrandLogos data={data} onSaved={reload} />
      <BrandReports data={data} onSaved={reload} />
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
          <b>Platform Logos</b>
          <span>
            The screens' logos and the sign-in page's own. PNG, JPEG or WebP, at most {data.max_kb} KB. SVG is not
            accepted, because it can carry scripts. Each is used only where its note says.
            PDFs have their own Report Logo, below.
          </span>
        </div>
      </div>
      <div className="st-logos">
        {LOGOS.map(([kind, label, hint, empty]) => (
          <LogoSlot key={kind} label={label} hint={hint} url={data[`${kind}_url`]} maxKb={data.max_kb}
            empty={empty ? <BuiltIn kind={empty} data={data} /> : undefined}
            dark={kind === "logo_dark"}
            onUpload={(dataUrl) => settingsApi.uploadBrandLogo(kind, dataUrl)}
            onRemove={() => settingsApi.removeBrandLogo(kind)}
            onSaved={onSaved} />
        ))}
      </div>
    </div>
  );
}

/** The PDFs' own logo (PNG or JPEG only), and a preview of a document in the platform's brand. */
function BrandReports({ data, onSaved }) {
  return (
    <div className="panel">
      <div className="ph">
        <div>
          <b>Reports</b>
          <span>
            The logo on PDFs in Platform Branding, instead of the logo for light backgrounds. PNG or JPEG only, at
            most {data.max_kb} KB: the PDF engine cannot draw WebP, and SVG is not accepted.
            Each business can instead carry its own logo or letterhead: Businesses → Manage → Co-Branding.
          </span>
        </div>
      </div>
      <div className="st-logos">
        <LogoSlot label="Report Logo" hint={REPORT_USES[data.report_uses] || ""} url={data.logo_report_url}
          maxKb={data.max_kb} types={PRINT_TYPES}
          onUpload={(dataUrl) => settingsApi.uploadBrandLogo("logo_report", dataUrl)}
          onRemove={() => settingsApi.removeBrandLogo("logo_report")}
          onSaved={onSaved} />
      </div>
      <div style={{ marginTop: 14 }}>
        <ReportPreview run={() => settingsApi.previewReportStyle("", "platform", "show")} />
      </div>
    </div>
  );
}

/** Preview: a one-page sample PDF (or its HTML where the server has no PDF engine), shown
 *  here, labelled as a preview. Nothing is stored. Shared with Businesses → Manage. */
export function ReportPreview({ run, label = "Preview" }) {
  const [st, setSt] = useState({});
  const [view, setView] = useState(null);
  useEffect(() => () => view?.url && URL.revokeObjectURL(view.url), [view]);
  const go = async () => {
    const out = await act(setSt, run);
    if (!out) return;
    setSt({});
    if (out.pdf) {
      const bytes = Uint8Array.from(atob(out.pdf), (c) => c.charCodeAt(0));
      setView({ url: URL.createObjectURL(new Blob([bytes], { type: "application/pdf" })), label: out.style_label });
    } else {
      setView({ html: out.html, label: out.style_label, reason: out.reason });
    }
  };
  return (
    <div className="st-preview">
      <div className="st-acts" style={{ justifyContent: "flex-start" }}>
        <button type="button" className="btn" onClick={go} disabled={st.busy}>
          {st.busy ? "Preparing…" : label}
        </button>
        {view ? <button type="button" className="btn" onClick={() => setView(null)}>Close Preview</button> : null}
        {view?.url ? <a className="btn" href={view.url} target="_blank" rel="noreferrer">Open PDF</a> : null}
      </div>
      <Msg tone="bad">{st.bad}</Msg>
      {view ? (
        <>
          <span className="st-sub">
            Preview, {view.label}: sample wording, nothing saved.
            {view.html ? " No PDF engine here, so this is the page as HTML; the PDF is laid out the same way." : ""}
          </span>
          {view.url
            ? <iframe title="Report preview" src={view.url} />
            : <iframe title="Report preview" sandbox="allow-same-origin" srcDoc={view.html} />}
        </>
      ) : null}
    </div>
  );
}

/** One logo: what is set now, Choose File, Remove. Shared with Businesses → Manage. */
export function LogoSlot({ label, hint, url, maxKb = 1024, dark = false, wide = false, types = IMAGE_TYPES,
  empty = "None", onUpload, onRemove, onSaved }) {
  const [st, setSt] = useState({});
  const choose = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const out = await act(setSt, async () => onUpload(await readImage(file, maxKb, types)),
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
      <div className={`st-logo-box${dark ? " dark" : ""}${wide ? " wide" : ""}`}>
        {url ? <img src={url} alt={label} />
          : typeof empty === "string" ? <span className="st-dim">{empty || "None"}</span> : empty}
      </div>
      <div className="st-acts" style={{ justifyContent: "flex-start" }}>
        <label className="btn st-file">
          {st.busy ? "Uploading…" : url ? "Replace" : "Choose File"}
          <input type="file" accept={types.join(",")} onChange={choose} disabled={st.busy} />
        </label>
        {url ? <button type="button" className="btn" onClick={remove} disabled={st.busy}>Remove</button> : null}
      </div>
      <Msg tone="ok">{st.ok}</Msg>
      <Msg tone="bad">{st.bad}</Msg>
    </div>
  );
}
