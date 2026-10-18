import React, { useEffect, useRef, useState } from "react";
import { getAppearance, setAppearance } from "../appearance.js";
import extras from "../legacy/extras.json";
import Icon from "./Icon.jsx";

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
        className={`ib${open ? " on" : ""}`}
        title="Appearance"
        aria-label="Appearance"
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
      >
        <Icon name="sliders" />
      </button>

      {/* Light and dark live on the bar itself; this menu holds the finer choices.
          Both are saved per browser and only for the person choosing. */}
      <div className={`appearmenu${open ? " on" : ""}`} onClick={(e) => e.stopPropagation()}>
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
          <span>Saved for you only</span>
          <b>{ACCENTS.find((a) => a.key === look.accent)?.label || ""}</b>
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
