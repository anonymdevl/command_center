import React, { useEffect, useRef, useState } from "react";
import { getAppearance, setAppearance } from "../appearance.js";
import extras from "../legacy/extras.json";

const ACCENTS = extras.accents || [];
const SIGNALS = [
  ["vivid", "Vivid"],
  ["muted", "Muted"],
  ["quiet", "Quiet"],
];

export default function Appearance() {
  const [open, setOpen] = useState(false);
  const [look, setLook] = useState(getAppearance);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const away = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("click", away);
    return () => document.removeEventListener("click", away);
  }, [open]);

  const set = (kind, value) => {
    setAppearance(kind, value);
    setLook(getAppearance());
  };

  return (
    <div className="appear" ref={ref}>
      <button
        className="themebtn"
        title="Appearance"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
      >
        {look.theme === "light" ? "◘" : "◑"}
      </button>

      <div className={`appearmenu${open ? " on" : ""}`} onClick={(e) => e.stopPropagation()}>
        <div className="amsec">Theme</div>
        <div className="seg">
          {["light", "dark"].map((t) => (
            <button key={t} className={look.theme === t ? "on" : ""} onClick={() => set("theme", t)}>
              {t === "light" ? "Light" : "Dark"}
            </button>
          ))}
        </div>

        <div className="amsec">Accent</div>
        <div className="swatches">
          {ACCENTS.map((a) => (
            <button
              key={a.key}
              className={`sw${look.accent === a.key ? " on" : ""}`}
              data-a={a.key}
              title={`${a.label} \u2014 ${a.note}`}
              /* Split disc: dark half, light half. Without this every swatch is
                 an empty circle, which is what the port shipped. */
              style={{
                background: `linear-gradient(135deg, ${a.dark} 0 50%, ${a.light} 50% 100%)`,
              }}
              onClick={() => set("accent", a.key)}
            />
          ))}
        </div>
        <div className="swname">
          {ACCENTS.find((a) => a.key === look.accent)?.label || ""}
        </div>

        <div className="amsec">Signal strength</div>
        <div className="seg">
          {SIGNALS.map(([v, label]) => (
            <button key={v} className={look.signal === v ? "on" : ""} onClick={() => set("signal", v)}>
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
