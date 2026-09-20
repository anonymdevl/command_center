import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Fetch on mount and whenever the dependencies change.
 *
 * Small on purpose. TanStack Query would give caching and retries, and if this
 * interface ever needs them it is a drop-in -- but a dependency earns its place
 * by solving a problem we have, and today we have twenty views each reading a
 * handful of aggregates.
 *
 * It aborts in flight. Without that, switching business twice quickly lets the
 * slower response land last and paint the wrong company's figures.
 */
export function useApi(fn, deps = [], { skip = false } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: !skip });
  const [nonce, setNonce] = useState(0);
  const latest = useRef(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (skip) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    const seq = ++latest.current;
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));

    Promise.resolve(fn({ signal: ctrl.signal }))
      .then((data) => {
        if (seq === latest.current) setState({ data, error: null, loading: false });
      })
      .catch((error) => {
        if (error?.name === "AbortError") return;
        if (seq === latest.current) setState({ data: null, error, loading: false });
      });

    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, skip]);

  return { ...state, reload };
}
