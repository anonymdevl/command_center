import React, { useEffect, useRef } from "react";

/**
 * The panel that answers "which records?".
 *
 * `content` is a React node, { html } for markup that has not been converted yet
 * (the legacy views' own generated markup only), or { node } for an element built
 * with DOM calls (legacy/guide.js) -- data is never passed as html.
 */
export default function Drawer({ content, onClose, onBack = null }) {
  const open = Boolean(content);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft" && e.altKey && onBack) onBack();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, onBack]);

  return (
    <>
      <div className={`scrim${open ? " on" : ""}`} onClick={onClose} />
      <div className={`drawer${open ? " on" : ""}`}>
        {onBack ? (
          <button type="button" className="btn drawer-back" onClick={onBack}
                  aria-label="Back to the previous panel">
            ← Back
          </button>
        ) : null}
        {content && content.html ? (
          <div dangerouslySetInnerHTML={{ __html: content.html }} />
        ) : content && content.node ? (
          <Mounted node={content.node} />
        ) : (
          content
        )}
      </div>
    </>
  );
}

/** An element built with DOM calls, placed as it is. */
function Mounted({ node }) {
  const ref = useRef(null);
  useEffect(() => {
    const host = ref.current;
    if (!host || !node) return undefined;
    host.replaceChildren(node);
    return () => host.replaceChildren();
  }, [node]);
  return <div ref={ref} />;
}
