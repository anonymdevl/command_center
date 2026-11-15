/**
 * Every chart on the platform goes through here: an answer's chart blocks (charts.js)
 * and the designed screens' chart panels (panels.js).
 *
 *   const viz = createViz(model, { key, title, compact, onPick });
 *   parent.append(viz.node);      // the toolbar, the chart, its table
 *   viz.update(nextModel);        // the screen's minute refresh: in place, no flicker
 *
 * What it adds to the figures it is given (vizoptions.js turns them into ECharts):
 *
 *   - Apache ECharts, loaded the first time a chart is on the page (its own chunk, so
 *     the first paint never waits for it), drawn as SVG.
 *   - The theme, read from the stylesheet's tokens at render time, and redrawn when the
 *     theme, accent or signal changes -- so a chart is right in light and dark.
 *   - A switcher between the views that make sense for the figures (Bar / Donut / Pie
 *     / Table for parts of a whole; Line / Area / Bar / Table over time ...), remembered
 *     per chart in this browser; Download as PNG or SVG (drawn again from the same
 *     figures, with the title, in the screen's colours); and Table, every figure in
 *     full, which is also how the chart reads to a keyboard or a screen reader.
 *   - Resizing with its box (ResizeObserver), and cleaning up after itself: a chart
 *     whose node has left the page is disposed, so screens that redraw every minute do
 *     not pile up instances.
 *
 * Nothing from data is ever written as HTML here: the toolbar and table are built with
 * textContent, and tooltips are escaped in vizoptions.js.
 */

import { buildOption, viewsFor, heightFor, tableOf, describe, pieModel, VIEW_LABELS, esc } from "./vizoptions.js";

let lib = null;
/** ECharts, fetched once, the first time a chart needs it. */
export function loadECharts() {
  lib ||= import("./echarts-lib.js").then((m) => m.default);
  return lib;
}

const LIVE = new Set();
const BY_NODE = new WeakMap();
let sweeper = null;
let themeWatch = null;

/** The handle for a node createViz made, if it is still live. */
export function vizOf(node) {
  return node ? BY_NODE.get(node) || null : null;
}

/** Dispose every chart inside root (a screen being taken down). */
export function disposeWithin(root) {
  if (!root) return;
  [...LIVE].forEach((h) => { if (root.contains(h.node)) h.dispose(); });
}

export function createViz(model, opts = {}) {
  const node = el("div", `vz${opts.compact ? " vz-compact" : ""}`);
  const bar = el("div", "vz-bar");
  bar.setAttribute("role", "toolbar");
  bar.setAttribute("aria-label", "Chart options");
  const seg = el("div", "vz-seg");
  seg.setAttribute("role", "group");
  seg.setAttribute("aria-label", "Show as");
  const tools = el("div", "vz-tools");
  bar.append(seg, tools);
  const stage = el("div", "vz-stage");
  stage.setAttribute("role", "img");
  const table = el("div", "vz-table");
  table.hidden = true;
  node.append(bar, stage, table);

  const s = {
    node, model, opts, views: [], view: null, chart: null, pending: null, ro: null, width: 0, sig: "",
    lostAt: 0, dead: false, lastChart: null, height: 0, drawn: null,
  };

  const h = {
    node,
    get view() { return s.view; },
    get model() { return s.model; },
    update(next, more = {}) {
      s.model = next;
      s.opts = { ...s.opts, ...more };
      if (s.dead) revive();
      setViews();
      render();
    },
    setView(v) {
      if (!s.views.includes(v)) return;
      s.view = v;
      remember(v);
      paintSeg();
      render();
    },
    dispose() {
      s.dead = true;
      LIVE.delete(h);
      s.ro?.disconnect();
      s.ro = null;
      s.chart?.dispose();
      s.chart = null;
      s.drawn = null;
    },
    /** The chart as an SVG file's text, in the screen's colours (also what PNG draws). */
    toSvg: () => fileSvg(s),
    _state: s,
  };
  BY_NODE.set(node, h);

  /* ------------------------------------------------------------- toolbar */
  const button = (cls, label, title, fn) => {
    const b = el("button", cls, label);
    b.type = "button";
    if (title) b.title = title;
    b.dataset.ccWired = "1"; // actions.js leaves it alone
    b.addEventListener("click", fn);
    return b;
  };
  const dl = (fmt, title) => button("vz-dl", fmt, title, async (e) => {
    const b = e.currentTarget;
    try {
      if (fmt === "PNG") await savePng(s);
      else save(new Blob([await fileSvg(s)], { type: "image/svg+xml;charset=utf-8" }), fileName(s, "svg"));
    } catch (err) {
      b.textContent = "Failed";
      b.title = err?.message || "The download failed.";
      setTimeout(() => { b.textContent = fmt; b.title = title; }, 2500);
    }
  });
  tools.append(el("span", "vz-dl-t", "Download"),
    dl("PNG", "Save this chart as a picture"),
    dl("SVG", "Save this chart as a drawing that stays sharp at any size"));

  function setViews() {
    const views = viewsFor(s.model);
    const changed = views.join() !== s.views.join();
    s.views = views;
    if (!s.views.includes(s.view)) s.view = recalled(views) || views[0];
    if (changed) {
      seg.textContent = "";
      if (views.length > 1) {
        views.forEach((v) => seg.append(button("vz-opt", VIEW_LABELS[v] || v, `Show as ${(VIEW_LABELS[v] || v).toLowerCase()}`, () => h.setView(v))));
      }
      seg.hidden = views.length <= 1;
    }
    paintSeg();
  }

  function paintSeg() {
    [...seg.children].forEach((b, i) => {
      const on = s.views[i] === s.view;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  const storeKey = () => (s.opts.key ? `cc-viz:${s.opts.key}` : null);
  function recalled(views) {
    const k = storeKey();
    if (!k) return null;
    try {
      const v = localStorage.getItem(k);
      return views.includes(v) ? v : null;
    } catch {
      return null;
    }
  }
  function remember(v) {
    const k = storeKey();
    if (!k) return;
    try {
      if (v === s.views[0]) localStorage.removeItem(k);
      else localStorage.setItem(k, v);
    } catch {
      /* private browsing: the choice simply does not persist */
    }
  }

  /* -------------------------------------------------------------- drawing */
  function render() {
    if (s.dead) return;
    stage.setAttribute("aria-label", describe(s.model, s.view === "table" ? s.views[0] : s.view));
    node.dataset.view = s.view;
    s.opts.onView?.(s.view);
    if (s.view === "table") {
      drawTable();
      table.hidden = false;
      stage.hidden = true;
      return;
    }
    table.hidden = true;
    stage.hidden = false;
    s.lastChart = s.view;
    const width = s.width || node.clientWidth || 0;
    const height = heightFor(s.model, s.view, width || 640, !!s.opts.compact);
    if (height !== s.height) {
      s.height = height;
      stage.style.height = `${height}px`;
    }
    if (!width || typeof window === "undefined") return; // not on the page yet: drawn on arrival
    if (!s.chart) {
      if (s.pending) return;
      s.pending = loadECharts().then((ec) => {
        s.pending = null;
        if (s.dead || s.chart || !node.isConnected) return;
        s.chart = ec.init(stage, null, { renderer: "svg" });
        s.chart.on("click", (p) => {
          if (!s.opts.onPick || s.model.other && p.dataIndex === s.model.labels.length - 1) return;
          let i = s.view === "strip" ? p.seriesIndex : p.dataIndex;
          if (["pie", "donut", "rose"].includes(s.view)) i = pieModel(s.model).index[i];
          if (Number.isInteger(i) && i >= 0 && i < s.model.labels.length) s.opts.onPick(i);
        });
        apply(true);
      }).catch(() => {
        s.pending = null;
        // ECharts could not be fetched (offline, a stale chunk after a deploy): the
        // figures are still all there, as a table.
        drawTable();
        table.hidden = false;
        stage.hidden = true;
      });
      return;
    }
    apply(false);
  }

  function apply(first) {
    if (!s.chart) return;
    const T = readTheme(node);
    const width = s.width || node.clientWidth || 640;
    const ctx = { width: Math.round(width), compact: !!s.opts.compact, pick: !!s.opts.onPick };
    const sig = JSON.stringify([s.model, s.view, T, Math.round(width / 40), ctx.compact, ctx.pick]);
    s.chart.resize();
    if (!first && sig === s.sig) return;
    s.sig = sig;
    const option = buildOption(s.model, s.view, T, ctx);
    if (!option) return;
    if (s.drawn !== s.view) {
      // A new view replaces the drawing (bars morph into slices as it does); the same
      // view is updated in place, so a refresh moves the marks rather than redrawing.
      s.chart.setOption(option, { notMerge: true });
      s.drawn = s.view;
    } else {
      s.chart.setOption(option, {
        replaceMerge: ["series", "xAxis", "yAxis", "grid", "legend", "title", "visualMap", "radar"],
      });
    }
  }

  function drawTable() {
    const t = tableOf(s.model);
    table.textContent = "";
    const tbl = el("table", "dt vz-tbl");
    const thead = el("thead");
    const hr = el("tr");
    t.head.forEach((x, i) => {
      const th = el("th", i ? "num" : null, x);
      hr.append(th);
    });
    thead.append(hr);
    const body = el("tbody");
    t.rows.forEach((r) => {
      const tr = el("tr");
      r.cells.forEach((x, i) => {
        const td = el("td", i ? "num" : null);
        if (i === 0 && r.strong) td.append(el("b", null, x));
        else td.textContent = x;
        tr.append(td);
      });
      if (s.opts.onPick && !(s.model.other && r.index === s.model.labels.length - 1)) {
        tr.classList.add("clickable");
        tr.setAttribute("role", "button");
        tr.setAttribute("tabindex", "0");
        const go = () => s.opts.onPick(r.index);
        tr.addEventListener("click", go);
        tr.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            go();
          }
        });
      }
      body.append(tr);
    });
    tbl.append(thead, body);
    table.append(tbl);
  }

  /* ------------------------------------------------------------ lifecycle */
  function observe() {
    if (typeof ResizeObserver === "undefined") return;
    s.ro = new ResizeObserver((entries) => {
      const w = entries[entries.length - 1]?.contentRect?.width || 0;
      if (!node.isConnected) { sweep(); return; }
      if (w && Math.abs(w - s.width) >= 1) {
        s.width = w;
        render();
      }
    });
    s.ro.observe(node);
  }
  function revive() {
    s.dead = false;
    s.sig = "";
    LIVE.add(h);
    observe();
  }

  setViews();
  LIVE.add(h);
  observe();
  watchTheme();
  startSweeper();
  render();
  return h;
}

/* ------------------------------------------------------------------ theme */
const TOKENS = ["ink", "ink2", "mut", "dim", "line", "line2", "surface", "raised", "accent", "ok", "med", "high", "crit"];
const FALLBACK = {
  ink: "#111317", ink2: "#3b3f47", mut: "#646973", dim: "#7c818b", line: "#ecedf0", line2: "#dfe1e6",
  surface: "#ffffff", raised: "#f5f6f8", accent: "#2443e8", ok: "#127a55", med: "#856307", high: "#a85a0a", crit: "#c2392f",
};
const FALLBACK_PALETTE = ["#2443e8", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"];

/** The theme's tokens, as the stylesheet resolves them where the chart sits. */
export function readTheme(node) {
  const cs = typeof getComputedStyle === "function" ? getComputedStyle(node.isConnected ? node : document.documentElement) : null;
  const tok = (name) => (cs ? cs.getPropertyValue(`--${name}`).trim() : "");
  const T = {};
  TOKENS.forEach((k) => { T[k] = tok(k) || FALLBACK[k]; });
  T.font = tok("sans") || "Manrope, -apple-system, 'Segoe UI', Roboto, sans-serif";
  const palette = [1, 2, 3, 4, 5, 6, 7].map((i) => tok(`viz${i}`)).filter(Boolean);
  T.palette = palette.length === 7 ? palette : FALLBACK_PALETTE;
  return T;
}

function watchTheme() {
  if (themeWatch || typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.documentElement) return;
  let queued = false;
  themeWatch = new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      LIVE.forEach((h) => h.update(h.model));
    });
  });
  themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "data-accent", "data-signal"] });
}

/** Charts whose node has been off the page for a while are disposed. */
function sweep() {
  const now = Date.now();
  LIVE.forEach((h) => {
    const st = h._state;
    if (h.node.isConnected) { st.lostAt = 0; return; }
    if (!st.lostAt) st.lostAt = now;
    else if (now - st.lostAt > 4000) h.dispose();
  });
  if (!LIVE.size && sweeper) {
    clearInterval(sweeper);
    sweeper = null;
  }
}

function startSweeper() {
  if (sweeper || typeof ResizeObserver === "undefined") return;
  sweeper = setInterval(sweep, 5000);
}

/* ------------------------------------------------------------- downloading */
const FILE_W = 760;

async function fileSvg(s) {
  const ec = await loadECharts();
  const T = readTheme(s.node || document.documentElement);
  const view = s.view === "table" ? s.lastChart || s.views.find((v) => v !== "table") : s.view;
  const title = s.opts.title || s.model.title || "";
  const head = title ? 46 : 16;
  const note = s.model.note || "";
  const foot = note ? 28 : 14;
  const ch = heightFor(s.model, view, FILE_W - 40, false);
  const off = ec.init(null, null, { renderer: "svg", ssr: true, width: FILE_W - 40, height: ch });
  let inner;
  try {
    const option = buildOption(s.model, view, T, { width: FILE_W - 40, compact: false });
    // A file cannot be clicked into: no treemap breadcrumb.
    option.series.forEach((x) => { if (x.breadcrumb) x.breadcrumb = { show: false }; });
    off.setOption({ ...option, animation: false });
    inner = off.renderToSVGString();
  } finally {
    off.dispose();
  }
  const H = head + ch + foot;
  const font = esc(T.font);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${FILE_W}" height="${H}" viewBox="0 0 ${FILE_W} ${H}" font-family="${font}">`
    + `<rect width="${FILE_W}" height="${H}" fill="${esc(T.surface)}"/>`
    + (title ? `<text x="20" y="30" font-size="16" font-weight="700" fill="${esc(T.ink)}">${esc(title)}</text>` : "")
    + inner.replace(/^<svg /, `<svg x="20" y="${head}" `)
    + (note ? `<text x="20" y="${H - 12}" font-size="11" fill="${esc(T.mut)}">${esc(note)}</text>` : "")
    + "</svg>";
}

async function savePng(s) {
  const svg = await fileSvg(s);
  const size = svg.match(/width="(\d+)" height="(\d+)"/);
  const width = Number(size[1]), height = Number(size[2]);
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = () => reject(new Error("The chart could not be turned into a picture."));
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  });
  const k = 2;
  const canvas = document.createElement("canvas");
  canvas.width = width * k;
  canvas.height = height * k;
  const ctx = canvas.getContext("2d");
  ctx.scale(k, k);
  ctx.drawImage(img, 0, 0, width, height);
  const blob = await new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("The picture could not be made."))), "image/png"));
  save(blob, fileName(s, "png"));
}

function save(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

function fileName(s, ext) {
  const t = s.opts.title || s.model.title || "";
  const slug = t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
  return `${slug || "chart"}.${ext}`;
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}
