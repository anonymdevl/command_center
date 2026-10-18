import React from "react";
import { api } from "../api/client.js";
import { boot } from "../api/boot.js";
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

    const head = document.createElement("div");
    head.className = "print-head";
    head.textContent =
      `${biz} · ${caption} · figures as at ${shortDate(boot.as_of?.date) || "—"} · ` +
      `printed by ${boot.user?.name || ""} on ${new Date().toLocaleString("en-GB", {
        day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
      })}`;
    main?.prepend(head);
    root.setAttribute("data-theme", "light");
    // The browser offers the title as the PDF's file name.
    document.title = `${caption} – ${biz} – ${new Date().toISOString().slice(0, 10)}`;

    const restore = () => {
      head.remove();
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
