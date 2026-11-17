import React from "react";
import { api } from "../api/client.js";
import { asOfFor, boot, brand, clientBrand } from "../api/boot.js";
import { shortDate } from "../format.js";
import { tablesFrom } from "../exportTables.js";
import ExportButton from "./ExportButton.jsx";

/**
 * Export the screen being looked at: as a PDF, or its tables as Excel.
 *
 * The PDF is the browser's print, laid out for paper by the print styles in shell.py:
 * no sidebar or bar, light theme whatever the screen is in, a header saying whose
 * figures, as at when, printed by whom. Printing what is rendered means the PDF holds
 * exactly the figures on screen, hydrated ones included -- a server rebuilding the
 * screen would have to re-derive them and could disagree.
 */
export default function ViewTools({ caption, scope }) {
  const pdf = async () => {
    const root = document.documentElement;
    const theme = root.getAttribute("data-theme");
    const title = document.title;
    const main = document.getElementById("cc-main");
    const biz = (boot.scopes || []).find((s) => s.code === scope)?.label || "All businesses";

    const client = clientBrand(scope);
    const head = printHead(caption, client?.display_name || biz, client?.logo_url,
      `Figures as at ${shortDate(asOfFor(scope)?.date) || "—"} · printed by ${boot.user?.name || ""} on ${
        new Date().toLocaleString("en-GB", {
          day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
        })}`);
    const foot = node("div", "print-foot", brand.footer || brand.product);
    main?.prepend(head);
    main?.append(foot);
    root.setAttribute("data-theme", "light");
    // The browser offers the title as the PDF's file name.
    document.title = `${caption} – ${biz} – ${new Date().toISOString().slice(0, 10)}`;

    const restore = () => {
      head.remove();
      foot.remove();
      if (theme) root.setAttribute("data-theme", theme);
      document.title = title;
      window.removeEventListener("afterprint", restore);
    };
    window.addEventListener("afterprint", restore);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    window.print();
    // Some browsers never fire afterprint; a timer makes sure the screen comes back.
    setTimeout(restore, 1500);
  };

  const excel = () => {
    const tables = tablesFrom(document.getElementById("cc-main"));
    if (!tables.length) {
      return Promise.reject(new Error("There are no tables on this part of the screen."));
    }
    return api.tablesXlsx({ title: caption, tables, business_code: scope });
  };

  return (
    <div className="vtools" role="toolbar" aria-label="Export this screen">
      <ExportButton label="PDF" title="Print this screen or save it as a PDF" run={pdf} />
      <ExportButton label="Excel" title="Download the tables on this screen as Excel" run={excel} />
    </div>
  );
}

/** The printed page's header: the product's logo (or name), the screen, who it is for,
 *  and as at when -- built from nodes, never HTML. */
function printHead(caption, forName, clientLogo, meta) {
  const head = node("div", "print-head");
  if (brand.logo_light_url) {
    const img = document.createElement("img");
    img.src = brand.logo_light_url;
    img.alt = "";
    head.append(img);
  }
  const title = node("div", "");
  title.append(node("b", "", caption), document.createElement("br"),
    document.createTextNode(`${brand.product} · Prepared for ${forName}`));
  head.append(title);
  if (clientLogo) {
    const img = document.createElement("img");
    img.src = clientLogo;
    img.alt = "";
    head.append(img);
  }
  head.append(node("div", "ph-meta", meta));
  return head;
}

function node(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text) n.textContent = text;
  return n;
}
