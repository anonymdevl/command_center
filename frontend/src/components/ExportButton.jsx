import React, { useState } from "react";

/**
 * One export control, the same everywhere: says what it will make, shows that it is
 * working, and says when it is done or what went wrong -- a download that silently
 * fails looks exactly like one that never started.
 */
export default function ExportButton({ label, run, className = "ap-act", title }) {
  const [state, setState] = useState("idle"); // idle | busy | done | failed
  const [error, setError] = useState("");

  const go = async () => {
    if (state === "busy") return;
    setState("busy");
    setError("");
    try {
      await run();
      setState("done");
      setTimeout(() => setState("idle"), 2200);
    } catch (e) {
      setError(e?.message || "The export failed.");
      setState("failed");
      setTimeout(() => setState("idle"), 5000);
    }
  };

  const text =
    state === "busy" ? "Preparing…" : state === "done" ? "Downloaded" : state === "failed" ? "Export failed" : label;
  return (
    <button
      type="button"
      className={`${className}${state === "failed" ? " failed" : ""}`}
      onClick={go}
      disabled={state === "busy"}
      title={state === "failed" ? error : title || label}
      aria-live="polite"
    >
      {text}
    </button>
  );
}
