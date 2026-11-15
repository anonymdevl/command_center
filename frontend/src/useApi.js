import { useCallback, useEffect, useRef, useState } from "react";
import { keep, peek, runner, shared } from "./swr.js";

/**
 * Fetch on mount and whenever the dependencies change.
 *
 * Small on purpose. TanStack Query would give caching and retries, and if this
 * interface ever needs them it is a drop-in -- but a dependency earns its place
 * by solving a problem we have, and today we have twenty views each reading a
 * handful of aggregates.
 *
 * The latest request wins. Without that, switching business twice quickly lets the
 * slower response land last and paint the wrong company's figures. A request without a
 * key is aborted when the dependencies change, as before.
 *
 * With `key` (swr.keyFor: the person, the business, the call), the screen is drawn at
 * once from the last answer to that same call while the new one is read, two parts of
 * the page asking the same thing share one request, and nothing kept under another key
 * is ever shown -- when the business changes, the screen shows that business's last
 * answer or nothing, never the previous business's.
 *
 * reload() reads again now; reload({ background: true }) -- the minute's refresh -- is
 * skipped while the last request is still on its way, so refreshes never pile up.
 */
export function useApi(fn, deps = [], { skip = false, key = null } = {}) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const keyRef = useRef(key);
  keyRef.current = key;
  const skipRef = useRef(skip);
  skipRef.current = skip;
  const runRef = useRef(null);
  if (!runRef.current) runRef.current = runner();
  const ctrlRef = useRef(null);
  const [state, setState] = useState(() => ({
    data: skip ? null : peek(key), error: null, loading: !skip,
  }));

  const go = useCallback((mode) => {
    if (skipRef.current) return;
    const k = keyRef.current;
    let ctrl = null;
    if (!k && mode !== "background") {
      ctrlRef.current?.abort();
      ctrl = new AbortController();
      ctrlRef.current = ctrl;
    }
    const call = () => fnRef.current({ signal: ctrl?.signal });
    runRef.current.run(() => (k && mode !== "reload" ? shared(k, call) : call()), {
      background: mode === "background",
      onStart: () => setState((s) => ({ ...s, loading: true, error: null })),
      onData: (data) => {
        if (k) keep(k, data);
        setState({ data, error: null, loading: false });
      },
      onError: (error) => {
        if (error?.name === "AbortError") return;
        setState({ data: null, error, loading: false });
      },
    });
  }, []);

  useEffect(() => {
    const run = runRef.current;
    run.invalidate();
    if (skip) {
      setState({ data: null, error: null, loading: false });
      return undefined;
    }
    if (keyRef.current) setState({ data: peek(keyRef.current), error: null, loading: true });
    go("open");
    return () => {
      run.invalidate();
      ctrlRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, skip]);

  const reload = useCallback(
    (opts) => go(opts && opts.background === true ? "background" : "reload"), [go]);

  return { ...state, reload };
}
