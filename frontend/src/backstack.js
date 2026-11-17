import React from "react";

/**
 * The browser's Back button and everything that slides over a screen (17 Nov 2026).
 *
 * On a phone, Back with a drawer open left the platform for the site before it: opening a
 * drawer added nothing to the browser's history, and switching screens replaced the one
 * entry there was. Now:
 *
 *   a layer    every drawer in the stack (App.jsx), the phone's menu, and the action,
 *              schedule and Settings dialogs, is one history entry at the same address, carrying
 *              { ccLayer: how many layers are open there }
 *   Back       arrives at an entry with fewer layers, and the layers above it close, top
 *              first: the screen and its list stay as they were
 *   own close  X, Escape, the scrim, Close, Done or a drawer's own Back take the entries
 *              of what they closed off again (history.go), so history never piles up and
 *              the next Back goes to the screen before
 *   a screen   its own entry (#key), so Back between screens works; a screen chosen
 *              while layers are open waits until their entries are gone, so it lands
 *              where they were and never on top of them
 *
 * history.go is asynchronous: anything that would add an entry while one of our own moves
 * is under way waits for it (or for a second, if the browser never says it arrived).
 * An entry with more layers than are open -- Forward, or a page reloaded with a drawer
 * open -- is passed over, back to the last entry that matches what is on screen; a page
 * reloaded on one goes back to it at once, so its first Back is never a press that does
 * nothing.
 *
 * scripts/test_screens.mjs drives this against a stand-in history; scripts/test_phone.mjs
 * presses Back in a real browser.
 */
export function backstack(win) {
  const h = win.history;
  const layers = []; // open now, bottom first: { id, kind, close, written }
  let seq = 0;
  let moving = 0; // our own history.go calls not yet arrived
  let timer = null;
  const waiting = [];

  const depthOf = (state) => (state && Number.isInteger(state.ccLayer) ? state.ccLayer : 0);
  const written = () => layers.filter((l) => l.written).length;

  const flush = () => {
    while (!moving && waiting.length) waiting.shift()();
  };
  const later = (fn) => {
    if (moving) waiting.push(fn);
    else fn();
  };
  const travel = (n) => {
    if (!(n < 0)) return;
    moving += 1;
    clearTimeout(timer);
    // A browser that never reports the move must not hold everything up.
    timer = setTimeout(() => {
      moving = 0;
      flush();
    }, 1000);
    h.go(n);
  };

  const onPop = (e) => {
    if (moving) {
      // Our own move has arrived: what is on screen already matches it.
      moving -= 1;
      if (!moving) clearTimeout(timer);
      flush();
      return;
    }
    // Back (or Forward): the layers above this entry close, top first.
    const depth = depthOf(e.state);
    while (layers.length > depth) layers.pop().close();
    // More layers here than are open: Forward, or a page reloaded with a drawer open.
    if (depth > layers.length) travel(layers.length - depth);
  };
  win.addEventListener("popstate", onPop);
  // Reloaded with a drawer open: nothing is open now, so step back to the screen's entry.
  travel(-depthOf(h.state));

  /** A layer opened over the screen: one history entry at the same address. */
  function open(close, kind = "layer") {
    seq += 1;
    const layer = { id: seq, kind, close, written: false };
    layers.push(layer);
    later(() => {
      if (!layers.includes(layer)) return; // closed before its entry was written
      h.pushState({ ...(h.state || {}), ccLayer: written() + 1 }, "");
      layer.written = true;
    });
    return layer.id;
  }

  /** A layer closed by its own controls: it and every layer above it, and their entries.
   *  `quiet`: the layer has already gone from the screen (a dialog unmounted), so its own
   *  close is not called again; the layers above it still are. */
  function close(id, quiet = false) {
    const at = layers.findIndex((l) => l.id === id);
    if (at < 0) return;
    const gone = layers.splice(at).reverse();
    later(() => travel(written() - depthOf(h.state)));
    // Off the screen now, not when the browser has moved.
    gone.forEach((l) => {
      if (!(quiet && l.id === id)) l.close();
    });
  }

  /** The lowest (or the top) open layer of a kind, with everything above it. */
  function closeKind(kind, which = "first") {
    const list = layers.filter((l) => l.kind === kind);
    const l = which === "last" ? list[list.length - 1] : list[0];
    if (l) close(l.id);
  }

  /** Another screen: every layer closes, then the screen gets its own entry. */
  function screen(key) {
    if (layers.length) close(layers[0].id);
    later(() => {
      if ((win.location.hash || "").replace(/^#/, "") !== key) h.pushState(null, "", `#${key}`);
    });
  }

  return {
    open, close, closeKind, screen,
    depth: () => layers.length,
    stop: () => win.removeEventListener("popstate", onPop),
  };
}

let shared = null;
/** The page's one back stack. */
export function stack() {
  if (!shared) shared = backstack(window);
  return shared;
}

/**
 * A layer while `open` is true: Back closes it (by calling `close`), and closing it any
 * other way takes its history entry off again.
 */
export function useLayer(open, close, kind = "layer") {
  const id = React.useRef(null);
  const latest = React.useRef(close);
  latest.current = close;
  React.useEffect(() => {
    if (open && id.current == null) {
      id.current = stack().open(() => {
        id.current = null;
        latest.current();
      }, kind);
    } else if (!open && id.current != null) {
      const was = id.current;
      id.current = null;
      stack().close(was, true);
    }
  }, [open, kind]);
  // Unmounted while open (a Settings dialog is open for as long as it is mounted): its
  // entry goes, and its close is not called on a component that is already gone.
  React.useEffect(() => () => {
    if (id.current == null) return;
    const was = id.current;
    id.current = null;
    stack().close(was, true);
  }, []);
}
