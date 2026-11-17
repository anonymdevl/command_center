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
// Every table cell is checked too (17 Nov 2026: on a phone, Today's "What" column ran over
// "Given to", and so did most tables): a cell whose content is wider than the cell while
// the cell does not clip, or a block inside a cell narrower than its own text that does
// not clip, paints over the next column and fails. Measured with the sample text as it
// is as well as with ?long=1, because the long strings put every cell in the widest band
// and hid the fault in the other two.
//
// And the phone's Back button (17 Nov 2026: Back with a drawer open left the platform for
// the site before it): at 375 wide it opens the menu and presses Back (the menu closes),
// chooses Outstanding Tasks from the menu, opens a task and presses Back (the drawer closes,
// the list is still there), opens it again and closes it with its X, and presses Back once
// more, which must be the screen before -- not the page the browser had open first.
//
// Folded rows (17 Nov 2026): every one-line row that opens for the rest (legacy/fold.js)
// fits its line at each width, open or closed; its toggle is a button with aria-expanded
// and aria-controls; Enter and Space work it; and its primary action is clicked without
// opening it -- on a phone and on a desktop.
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
  // A busy machine (a test suite running beside it) can take a while to start Chrome.
  for (let i = 0; i < 600 && !existsSync(portFile); i++) await sleep(100);
  if (!existsSync(portFile)) {
    proc.kill();
    console.log("FAIL: headless Chrome did not start within a minute.");
    process.exit(1);
  }
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
  for (const [w, long] of widths.flatMap((x) => [[x, true], [x, false]])) {
    const at = `${w}px${long ? "" : " (sample text)"}`;
    await b.send("Emulation.setDeviceMetricsOverride", { width: w, height: 900, deviceScaleFactor: 1, mobile: true });
    const url = `http://127.0.0.1:${port}/preview.html?phone=1${long ? "&long=1" : ""}&admin=1&theme=light&w=${w}#command`;
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
      console.log(`FAIL at ${at}: the preview wrote no measurement in two minutes.`);
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
      console.log(`FAIL at ${at}: walked ${screens} screens and ${sections} Settings sections, `
        + `expected ${SCREENS} and ${SETTINGS}.`);
    }
    let wide = 0;
    let spilt = 0;
    for (const [name, r] of Object.entries(got.report)) {
      failed += 1;
      if (r.page > 0 || r.main > 0 || r.offenders.length) {
        wide += 1;
        console.log(`FAIL at ${at}, ${name}: page ${r.page}px and main column ${r.main}px too wide`);
        r.offenders.forEach((o) => console.log(`    ${o}`));
      }
      if (r.spilled) {
        spilt += 1;
        console.log(`FAIL at ${at}, ${name}: ${r.spilled} table cell(s) paint past their own box`);
        r.cells.forEach((o) => console.log(`    ${o}`));
      }
    }
    console.log(`${at}: ${screens} screens and ${sections} Settings sections walked, `
      + `${wide} too wide, ${spilt} with cells running into the next`);
  }
  // Back, at a phone's width, from a page the browser had open before the platform.
  {
    await b.send("Emulation.setDeviceMetricsOverride", { width: 375, height: 800, deviceScaleFactor: 1, mobile: true });
    await b.send("Page.navigate", { url: "about:blank" });
    await sleep(300);
    await b.send("Page.navigate", { url: `http://127.0.0.1:${port}/preview.html?theme=light#command` });
    let ready = false;
    for (let i = 0; i < 120 && !ready; i++) {
      await sleep(500);
      const r = await b.send("Runtime.evaluate", {
        expression: "!!document.querySelector('#cc-main h1, #cc-main h2, #cc-main .card')", returnByValue: true });
      ready = !!r.result?.result?.value;
    }
    const steps = await b.send("Runtime.evaluate", { awaitPromise: true, returnByValue: true, expression: `(async () => {
      const wait = (ms) => new Promise((r) => setTimeout(r, ms));
      const out = [];
      const say = (ok, what) => out.push([ok, what]);
      const back = async () => { history.back(); await wait(900); };
      const drawerOn = () => !!document.querySelector(".drawer.on");
      const navOn = () => !!document.querySelector(".shell.navopen");
      try {
        await wait(600);
        document.querySelector(".menu-b").click();
        await wait(400);
        say(navOn(), "the menu opens");
        await back();
        say(!navOn() && location.hash === "#command", "Back closes the menu and stays on the screen (" + location.hash + ")");
        document.querySelector(".menu-b").click();
        await wait(400);
        const item = [...document.querySelectorAll(".nav .navi")].find((n) => n.textContent.trim().startsWith("Outstanding Tasks"));
        item.click();
        await wait(1800);
        say(!navOn() && location.hash === "#delegation", "choosing Outstanding Tasks from the menu (" + location.hash + ")");
        const row = () => document.querySelector("#cc-main tr.work-row");
        row().click();
        await wait(700);
        say(drawerOn(), "a task's drawer opens");
        await back();
        say(!drawerOn() && location.hash === "#delegation" && !!row(), "Back closes the drawer and the list is still there (" + location.hash + ")");
        row().click();
        await wait(700);
        document.querySelector(".drawer.on .dw-x").click();
        await wait(900);
        say(!drawerOn(), "X closes the drawer");
        await back();
        await wait(900);
        say(location.protocol.startsWith("http") && location.hash === "#command", "the next Back is the screen before (" + location.href + ")");
      } catch (e) {
        say(false, "the Back walk stopped: " + e);
      }
      return out;
    })()` });
    const got = steps.result?.result?.value || [[false, "the Back walk never finished: Back left the platform"]];
    got.forEach(([ok, what]) => {
      if (!ok) {
        failed += 1;
        console.log(`FAIL, Back on a phone: ${what}`);
      }
    });
    console.log(`Back on a phone: ${got.filter(([ok]) => ok).length} of ${got.length} steps as they should be`);
  }
  // Folded rows (legacy/fold.js, 17 Nov 2026), on a phone and on a desktop: on every
  // screen that has them, each row's toggle is a real button with aria-expanded and an
  // aria-controls that names its expansion, which stays in the DOM while closed; Enter
  // and Space (real key presses) open and close it; the chevron opens it too; and the
  // primary action on the row is on top where it is drawn and is clicked without
  // opening the row.
  for (const w of [375, 1280]) {
    await b.send("Emulation.setDeviceMetricsOverride", { width: w, height: 900, deviceScaleFactor: 1, mobile: w < 768 });
    await b.send("Page.navigate", { url: `http://127.0.0.1:${port}/preview.html?theme=light&long=1#command` });
    await sleep(2500);
    const run = async (expression) => (await b.send("Runtime.evaluate", {
      expression, awaitPromise: true, returnByValue: true })).result?.result?.value;
    const key = async (k, code, text) => {
      await b.send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code, windowsVirtualKeyCode: k === "Enter" ? 13 : 32, text });
      await b.send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code, windowsVirtualKeyCode: k === "Enter" ? 13 : 32 });
      await sleep(250);
    };
    const out = [];
    for (const view of ["command", "brief", "myday", "approvals", "delegation", "health", "risk"]) {
      const got = await run(`(async () => {
        const wait = (ms) => new Promise((r) => setTimeout(r, ms));
        location.hash = ${JSON.stringify(view)};
        await wait(2200);
        const out = [];
        const say = (ok, what) => out.push([ok, ${JSON.stringify(`${w}px #${view}: `)} + what]);
        // Rows on a tab that is not shown (Business Health, Risk) are looked at on their tab.
        const pane = document.querySelector("#cc-main .tabpane:not(.on) .fold")?.closest(".tabpane");
        if (pane) {
          document.querySelectorAll(\`#cc-main .tabbar[data-g="\${pane.dataset.g}"] .tab\`)[Number(pane.dataset.i)]?.click();
          await wait(400);
        }
        const toggles = [...document.querySelectorAll("#cc-main .fold-t")];
        say(toggles.length > 0, "has folded rows");
        let primaries = 0;
        for (const t of toggles) {
          const card = t.closest(".fold");
          const name = (t.textContent || "").trim().slice(0, 40);
          const panel = document.getElementById(t.getAttribute("aria-controls") || "-");
          say(t.tagName === "BUTTON" && t.type === "button", "the toggle of " + name + " is a button");
          say(["true", "false"].includes(t.getAttribute("aria-expanded")), name + " has aria-expanded");
          say(!!panel && card.contains(panel), name + "'s aria-controls names its expansion");
          if (!panel) continue;
          const open = () => t.getAttribute("aria-expanded") === "true";
          say(!open() && panel.hidden && panel.childElementCount > 0, name + " starts closed, its expansion in the DOM");
          const pri = card.querySelector(":scope > .fold-row > .fold-pri > button");
          if (pri) {
            primaries += 1;
            pri.scrollIntoView({ block: "center" });
            await wait(50);
            const r = pri.getBoundingClientRect();
            const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            say(r.width > 0 && !!top && pri.contains(top), name + "'s primary action is on top where it is drawn");
            pri.click();
            await wait(250);
            say(!open() && panel.hidden, "clicking " + name + "'s primary action does not open the row");
            document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
            await wait(250);
          }
          card.querySelector(":scope > .fold-row > .fold-chev").click();
          say(open() && !panel.hidden, "the chevron opens " + name);
          t.click();
          say(!open() && panel.hidden, "the toggle closes " + name);
        }
        const first = toggles[0];
        if (first) {
          first.scrollIntoView({ block: "center" });
          first.focus();
        }
        window.__foldFirst = first || null;
        return { out, primaries };
      })()`);
      if (!got) {
        out.push([false, `${w}px #${view}: the check did not finish`]);
        continue;
      }
      out.push(...got.out);
      if (["myday", "approvals", "delegation", "command"].includes(view)) {
        out.push([got.primaries > 0, `${w}px #${view}: rows carry their primary action`]);
      }
      const state = () => run("window.__foldFirst?.getAttribute('aria-expanded') || ''");
      if (!(await state())) continue;
      await key("Enter", "Enter", "\r");
      out.push([(await state()) === "true", `${w}px #${view}: Enter opens the first row`]);
      await key(" ", "Space", " ");
      out.push([(await state()) === "false", `${w}px #${view}: Space closes it again`]);
    }
    out.forEach(([ok, what]) => {
      if (!ok) {
        failed += 1;
        console.log(`FAIL, folded rows: ${what}`);
      }
    });
    console.log(`Folded rows at ${w}px: ${out.filter(([ok]) => ok).length} of ${out.length} checks as they should be`);
  }
} finally {
  b.close();
  await server.close();
}
if (failed) {
  console.log(`${failed} phone layout problem(s)`);
  process.exit(1);
}
console.log("phone layout: nothing wider than the screen, no cell past its own box");
