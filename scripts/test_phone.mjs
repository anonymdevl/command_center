// Every screen on a phone, with real-length text: nothing makes the page scroll sideways.
//
//     node scripts/test_phone.mjs            (375 and 428 wide, iPhone SE to 13 Pro Max)
//     node scripts/test_phone.mjs 390        (one width)
//
// The iPhone report of 17 Nov 2026: Home and the Executive Summary scrolled sideways into
// empty space. The cause was long unbroken text -- an alert's "Email: not sent: email is
// not set up on this platform" chip on one line, owners and document names carrying an
// email address or a link -- and short sample strings never show it. So this starts the
// preview (vite, frontend/preview/mock.js), opens it in headless Chrome at each width
// with ?long=1 (every name, title, reason, email and note carries a long email address
// and an ERPNext link) and ?admin=1 (Settings and its sections), and reads what
// ?phone=1 measured on every screen and every Settings section: the page wider than the
// window, the main column wider than itself, and the innermost elements past its edge
// that are not inside a box of their own that scrolls. Any of them fails the check.
//
// It also fails when fewer screens were walked than there are, so a preview that stops
// rendering cannot pass by measuring nothing. Needs Google Chrome (or CHROME=<path>);
// without one it says it was skipped and exits 0 -- preflight prints that line.
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const FRONT = path.join(ROOT, "frontend");
const WIDTHS = process.argv.slice(2).map(Number).filter(Boolean);
const widths = WIDTHS.length ? WIDTHS : [375, 428];
const SCREENS = 21; // nineteen designed screens, Settings and Plan & Usage
const SETTINGS = 10; // Settings sections an administrator sees
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = [process.env.CHROME,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"].find((p) => p && existsSync(p));
if (!chrome) {
  console.log("SKIPPED: no Chrome found (set CHROME=<path>); the phone layout was not checked.");
  process.exit(0);
}

const vitePath = path.join(FRONT, "node_modules", "vite", "dist", "node", "index.js");
if (!existsSync(vitePath)) {
  console.log("FAIL: frontend/node_modules is missing; run npm install in frontend first.");
  process.exit(1);
}
const { createServer } = await import(pathToFileURL(vitePath).href);
const server = await createServer({
  root: FRONT, configFile: path.join(FRONT, "vite.config.js"), base: "/", logLevel: "error",
  server: { port: 0, strictPort: false, host: "127.0.0.1", hmr: false },
});
await server.listen();
const port = server.httpServer.address().port;

/** Headless Chrome, driven over the DevTools protocol (Node's own WebSocket). */
async function browser() {
  const dir = mkdtempSync(path.join(os.tmpdir(), "cc-phone-"));
  const proc = spawn(chrome, ["--headless=new", "--disable-gpu", "--no-first-run",
    "--no-default-browser-check", "--hide-scrollbars", "--remote-debugging-port=0",
    `--user-data-dir=${dir}`, "about:blank"], { stdio: "ignore" });
  const portFile = path.join(dir, "DevToolsActivePort");
  for (let i = 0; i < 100 && !existsSync(portFile); i++) await sleep(100);
  const [devPort] = readFileSync(portFile, "utf8").split("\n");
  const list = await (await fetch(`http://127.0.0.1:${devPort}/json/list`)).json();
  const ws = new WebSocket(list.find((t) => t.type === "page").webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let seq = 0;
  const waiting = new Map();
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && waiting.has(msg.id)) {
      waiting.get(msg.id)(msg);
      waiting.delete(msg.id);
    }
  };
  const send = (method, params = {}) => new Promise((r) => {
    seq += 1;
    waiting.set(seq, r);
    ws.send(JSON.stringify({ id: seq, method, params }));
  });
  const close = () => {
    try { ws.close(); } catch { /* gone */ }
    proc.kill();
    setTimeout(() => rmSync(dir, { recursive: true, force: true }), 500);
  };
  return { send, close };
}

let failed = 0;
const b = await browser();
try {
  for (const w of widths) {
    await b.send("Emulation.setDeviceMetricsOverride", { width: w, height: 900, deviceScaleFactor: 1, mobile: true });
    const url = `http://127.0.0.1:${port}/preview.html?phone=1&long=1&admin=1&theme=light&w=${w}#command`;
    await b.send("Page.navigate", { url });
    let raw = null;
    for (let i = 0; i < 240 && !raw; i++) {
      await sleep(500);
      const r = await b.send("Runtime.evaluate", {
        expression: "document.getElementById('cc-phone')?.textContent || ''", returnByValue: true });
      raw = r.result?.result?.value || null;
    }
    if (!raw) {
      failed += 1;
      console.log(`FAIL at ${w}px: the preview wrote no measurement in two minutes.`);
      continue;
    }
    const got = JSON.parse(raw);
    if (got.width !== w) {
      failed += 1;
      console.log(`FAIL: asked for ${w}px, the window was ${got.width}px.`);
    }
    const screens = got.walked.filter((v) => !v.includes("/")).length;
    const sections = got.walked.filter((v) => v.startsWith("settings/")).length;
    if (screens < SCREENS || sections < SETTINGS) {
      failed += 1;
      console.log(`FAIL at ${w}px: walked ${screens} screens and ${sections} Settings sections, `
        + `expected ${SCREENS} and ${SETTINGS}.`);
    }
    for (const [name, r] of Object.entries(got.report)) {
      failed += 1;
      console.log(`FAIL at ${w}px, ${name}: page ${r.page}px and main column ${r.main}px too wide`);
      r.offenders.forEach((o) => console.log(`    ${o}`));
    }
    console.log(`${w}px: ${screens} screens and ${sections} Settings sections walked, `
      + `${Object.keys(got.report).length} too wide`);
  }
} finally {
  b.close();
  await server.close();
}
if (failed) {
  console.log(`${failed} phone layout problem(s)`);
  process.exit(1);
}
console.log("phone layout: nothing wider than the screen");
