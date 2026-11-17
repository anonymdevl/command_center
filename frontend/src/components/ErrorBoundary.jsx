import React from "react";

/**
 * A part of the page that failed to draw says so, and the rest of the page stays.
 *
 * Without one, a single malformed answer -- a drawer payload missing a field the drawer
 * reads -- threw while React drew it and unmounted the whole app: a blank page, the
 * sidebar and the question bar gone with it (17 Nov 2026). So there are three: around
 * the app's shell (main.jsx), around each screen (App.jsx) and around each drawer
 * (Drawer.jsx). Each shows one calm line and a Reload; the screen's and the drawer's
 * start clean when another screen, business or drawer is drawn (resetKey, or a key).
 *
 * The platform has no endpoint for errors from the browser, so the error goes to the
 * console, with where it happened, for whoever is looking.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  // Another screen, business or drawer (resetKey) is drawn afresh, not left on the notice.
  componentDidUpdate(prev) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error(`[insights] ${this.props.where || "the page"} failed to draw`, error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    // `head`: what stays above the notice (a drawer's own header, with Back and close).
    return (
      <>
        {this.props.head || null}
        <div className="cc-crash" role="alert">
          <b>Something went wrong showing this.</b>
          <span>Reload the page to try again. Nothing was changed.</span>
          <button type="button" className="btn" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      </>
    );
  }
}
