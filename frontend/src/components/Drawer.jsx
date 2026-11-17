import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import ErrorBoundary from "./ErrorBoundary.jsx";

/**
 * The panel that answers "which records?".
 *
 * `content` is a React node, { html } for markup that has not been converted yet
 * (the legacy views' own generated markup only), or { node } for an element built
 * with DOM calls (legacy/guide.js) -- data is never passed as html.
 *
 * Every drawer has one solid header that stays at the top while its content scrolls
 * under it (the old Back button floated over the rows with nothing behind it). A
 * component that draws its own header -- the records and figure drawers, which put
 * their title and actions in it -- says so with a static `ownsHeader` and places
 * <DrawerHead>; everything else gets the plain one here, with Back and close.
 */
const DrawerCtx = createContext({ onBack: null, onClose: () => {}, trail: [] });

export default function Drawer({ content, entry = null, onClose, onBack = null, trail = [] }) {
  const open = Boolean(content);
  const panel = useRef(null);
  const [scrolled, setScrolled] = useState(false);
  // A new panel (a related figure, a customer's records, Back) starts at its top.
  useEffect(() => {
    if (panel.current) panel.current.scrollTop = 0;
    setScrolled(false);
  }, [content, entry]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      // A dialog open over the drawer takes Escape (and Back) first: only it closes.
      if (document.querySelector(".dlg-scrim")) return;
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft" && e.altKey && onBack) onBack();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, onBack]);

  const owns = React.isValidElement(content) && content.type && content.type.ownsHeader;
  return (
    <>
      <div className={`scrim${open ? " on" : ""}`} onClick={onClose} />
      <div ref={panel} className={`drawer${open ? " on" : ""}${scrolled ? " dw-scrolled" : ""}`}
           role="dialog" aria-modal="true" aria-hidden={!open}
           onScroll={(e) => setScrolled(e.currentTarget.scrollTop > 2)}>
        <DrawerCtx.Provider value={{ onBack, onClose, trail }}>
          {/* Keyed by the stack entry (App.jsx): each drawer opened, or come back to, is
              mounted fresh, so none shows the state of the one before it. */}
          {!open ? null : owns ? (
            <ErrorBoundary key={entry ?? "drawer"} where="the drawer" head={<DrawerHead />}>
              {content}
            </ErrorBoundary>
          ) : (
            <React.Fragment key={entry ?? "drawer"}>
              <DrawerHead />
              <div className="dw-body">
                <ErrorBoundary where="the drawer">
                {content.html ? (
                  <div dangerouslySetInnerHTML={{ __html: content.html }} />
                ) : content.node ? (
                  <Mounted node={content.node} />
                ) : (
                  content
                )}
                </ErrorBoundary>
              </div>
            </React.Fragment>
          )}
        </DrawerCtx.Provider>
      </div>
    </>
  );
}

/**
 * The drawer's header: Back (only when there is a drawer to go back to), where it was
 * opened from, its title, its actions, and close.
 */
export function DrawerHead({ title = null, actions = null }) {
  const { onBack, onClose, trail } = useContext(DrawerCtx);
  const crumb = [...(trail || []), title].filter(Boolean);
  return (
    <header className="dw-head">
      {onBack ? (
        <button type="button" className="dw-btn dw-back" onClick={onBack}
                aria-label="Back to the previous panel">
          <span aria-hidden="true">←</span> Back
        </button>
      ) : null}
      <div className="dw-titles">
        {crumb.length > 1 ? (
          <div className="dw-crumb" title={crumb.join(" › ")}>{crumb.join(" › ")}</div>
        ) : null}
        {title ? <h4 className="dw-title" title={title}>{title}</h4> : null}
      </div>
      <div className="dw-acts">
        {actions}
        <button type="button" className="dw-btn dw-x" onClick={onClose} aria-label="Close">
          <span aria-hidden="true">×</span>
        </button>
      </div>
    </header>
  );
}

/** Back, close and the breadcrumb, for a drawer's own controls. */
export function useDrawer() {
  return useContext(DrawerCtx);
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
