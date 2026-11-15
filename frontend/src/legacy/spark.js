/**
 * The small chart on a recommendation: the figure's recent points and, once its history
 * is long enough, the business's usual range as a band (recommend/metrics.py spark()).
 *
 * Drawn with the platform's ECharts (viz.js loads it once, as its own chunk) in the
 * theme's tokens, read where the chart sits, so it is right in light and dark. No
 * toolbar: the card says in words what the chart shows, and the band's numbers are in
 * its title for a screen reader. Nothing from data is written as HTML.
 */

import { loadECharts, readTheme } from "./viz.js";

export function sparkline(chart, words) {
  if (!chart || !(chart.points || []).length) return null;
  const node = document.createElement("div");
  node.className = "rec-spark";
  node.setAttribute("role", "img");
  node.setAttribute("aria-label", words || chart.label || "Recent values");
  if (words) node.title = words;
  loadECharts().then((echarts) => {
    if (!node.isConnected) {
      // Not yet on the page: draw when it is (the card is appended after this returns).
      requestAnimationFrame(() => draw(echarts, node, chart));
      return;
    }
    draw(echarts, node, chart);
  }).catch(() => node.remove());
  return node;
}

function draw(echarts, node, chart) {
  if (!node.isConnected) return;
  const T = readTheme(node);
  const xs = chart.points.map((p) => p[0]);
  const ys = chart.points.map((p) => p[1]);
  const band = chart.low != null && chart.high != null;
  const series = [];
  if (band) {
    const low = chart.unit === "percent" ? chart.low : Math.max(chart.low, 0);
    series.push(
      { type: "line", data: xs.map(() => low), stack: "band", symbol: "none", lineStyle: { opacity: 0 }, silent: true },
      { type: "line", data: xs.map(() => chart.high - low), stack: "band", symbol: "none", lineStyle: { opacity: 0 },
        areaStyle: { color: T.accent, opacity: 0.12 }, silent: true },
    );
  }
  series.push({ type: "line", data: ys, symbol: "none", smooth: false, lineStyle: { width: 1.5, color: T.accent } });
  series.push({ type: "line", data: ys.map((v, i) => (i === ys.length - 1 ? v : null)), symbol: "circle", symbolSize: 5,
    itemStyle: { color: T.accent }, lineStyle: { opacity: 0 }, silent: true });
  const c = echarts.init(node, null, { renderer: "svg" });
  paint(c, xs, series);
  // Light and dark: drawn again in the new theme's colours when it changes.
  const mo = typeof MutationObserver === "undefined" ? null : new MutationObserver(() => {
    if (!node.isConnected) {
      mo.disconnect();
      return;
    }
    const t = readTheme(node);
    series.forEach((s) => {
      if (s.areaStyle) s.areaStyle.color = t.accent;
      if (s.itemStyle) s.itemStyle.color = t.accent;
      if (s.lineStyle && s.lineStyle.color) s.lineStyle.color = t.accent;
    });
    paint(c, xs, series);
  });
  mo?.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "data-accent"] });
  const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
    if (!node.isConnected) {
      ro.disconnect();
      c.dispose();
      return;
    }
    c.resize();
  });
  ro?.observe(node);
}

function paint(c, xs, series) {
  c.setOption({
    animation: false,
    grid: { left: 1, right: 4, top: 4, bottom: 2 },
    xAxis: { type: "category", data: xs, show: false, boundaryGap: false },
    yAxis: { type: "value", show: false, scale: true },
    tooltip: { show: false },
    series,
  }, true);
}
