import React, { useEffect } from "react";

/**
 * The panel that answers "which records?".
 *
 * `content` is either a React node or { html } for markup that has not been
 * converted yet. The html branch exists only for the legacy views and goes when
 * they do.
 */
export default function Drawer({ content, onClose }) {
  const open = Boolean(content);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      <div className={`scrim${open ? " on" : ""}`} onClick={onClose} />
      <div className={`drawer${open ? " on" : ""}`}>
        {content && content.html ? (
          <div dangerouslySetInnerHTML={{ __html: content.html }} />
        ) : (
          content
        )}
      </div>
    </>
  );
}
