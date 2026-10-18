"""The analyst's loop, tested without a site and without Gemini.

    python3 scripts/test_analyst.py

Frappe and pypika are stood in for, and Gemini's replies are scripted, so what is under
test is agent.py's own behaviour: that a model's function calls are honoured only through
tools.run, that a refused or unknown tool goes back to the model as a message rather than
an exception, that the session's business scope overrides any the model sends, that the
step budget ends in a forced answer, that a write made while answering is rolled back and
recorded, and that errors are logged only after that guard -- so the guard cannot erase
them. What it cannot test is Gemini's judgement or the real queries; those are checked on
the site.
"""

from __future__ import annotations

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# --- stand-ins ------------------------------------------------------------
class _DB:
    def __init__(self):
        self.transaction_writes = 0
        self.rolled_back = 0

    def rollback(self):
        self.rolled_back += 1


frappe = types.ModuleType("frappe")
frappe.db = _DB()
frappe.conf = {"command_center_gemini_key": "test"}
frappe.logged = []
frappe.log_error = lambda title=None, message=None: frappe.logged.append(
    (title, message, frappe.db.rolled_back))
frappe.get_traceback = lambda: "Traceback: boom"
frappe.utils = types.SimpleNamespace(today=lambda: "2026-10-18",
                                     get_url_to_form=lambda d, n: f"/app/{d}/{n}")
sys.modules["frappe"] = frappe
qb = types.ModuleType("frappe.query_builder")
fns = types.ModuleType("frappe.query_builder.functions")
for _n in ("Avg", "Count", "Max", "Min", "Sum"):
    setattr(fns, _n, lambda *a, **k: None)
sys.modules["frappe.query_builder"] = qb
sys.modules["frappe.query_builder.functions"] = fns
pypika = types.ModuleType("pypika")
pypika.CustomFunction = lambda *a, **k: (lambda *x: None)
pypika.Order = types.SimpleNamespace(asc="asc", desc="desc")
sys.modules["pypika"] = pypika

from command_center.ask import agent, gemini, tools  # noqa: E402

agent._system = lambda business_code: "SYSTEM"
seen = {}


def fake_find(text, business_code=None):
    seen["find"] = business_code
    return [{"name": "UBUNTU ORTHOPAEDICS", "kind": "customer"}]


def fake_writer(business_code=None):
    frappe.db.transaction_writes += 1  # something underneath wrote
    return {"ok": True}


tools.TOOLS["find"] = (fake_find, tools.TOOLS["find"][1])
tools.TOOLS["writes_underneath"] = (fake_writer, {"name": "writes_underneath"})


def script(*turns):
    """Gemini replies in order; each is ('call', [(name, args)...]) or ('text', str) or ('err', str)."""
    calls = []
    it = iter(turns)

    def chat(contents, decls, system, timeout=40):
        calls.append({"tools": decls is not None, "n_contents": len(contents)})
        kind, payload = next(it)
        if kind == "err":
            return None, payload
        if kind == "text":
            return {"role": "model", "parts": [{"text": payload}]}, None
        return {"role": "model", "parts": [{"functionCall": {"name": n, "args": a}}
                                           for n, a in payload]}, None
    gemini.chat = chat
    return calls


def reset():
    frappe.db.__init__()
    frappe.logged.clear()
    seen.clear()


passed = failed = 0


def check(ok, what):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print("FAIL:", what)


# 1. Tool call, then an answer. Scope from the session wins over the model's.
reset()
script(("call", [("find", {"text": "ubuntu", "business_code": "SOMEONE-ELSE"})]),
       ("text", "UBUNTU owes **GHS 636,675**."))
r = agent.answer("How much does Ubuntu owe?", "GIGMANN")
check(r and r["answered"] and "636,675" in r["answer"], "answers after a tool call")
check(seen.get("find") == "GIGMANN", "business scope comes from the session, not the model")
check(r["checked"] and r["checked"][0].startswith("find("), "the call is listed in what it checked")
check(r["format"] == "markdown" and r["mode"] == "analyst", "payload is marked as the analyst's")

# 2. An unknown tool goes back to the model as a refusal, not an exception.
reset()
script(("call", [("delete_everything", {})]), ("text", "I cannot do that."))
r = agent.answer("Delete the invoices", "GIGMANN")
check(r and "refused" in r["checked"][0], "unknown tool is refused and recorded")
check(frappe.db.rolled_back == 0, "no rollback when nothing wrote")

# 3. A write underneath is rolled back and recorded -- and logged after the rollback.
reset()
script(("call", [("writes_underneath", {})]), ("text", "Done looking."))
r = agent.answer("Anything", "GIGMANN")
check(frappe.db.rolled_back == 1, "a write made while answering is rolled back")
check(r and r["degraded"] and "rolled back" in r["degraded"][-1], "the rollback is reported")
check(frappe.logged and all(rb == 1 for _, _, rb in frappe.logged),
      "errors are logged after the rollback, so the guard cannot erase them")

# 4. A tool that crashes: the model is told, the traceback is logged, the answer survives.
reset()
tools.TOOLS["boom"] = (lambda business_code=None: 1 / 0, {"name": "boom"})
script(("call", [("boom", {})]), ("text", "That figure could not be checked."))
r = agent.answer("Q", "GIGMANN")
check(r and "failed" in r["checked"][0], "a crashing tool is marked failed")
check(any("tool boom failed" in (m or "") for _, m, _ in frappe.logged), "its traceback is logged")

# 5. Step budget: after MAX_STEPS rounds of calls, one final turn without tools.
reset()
calls = script(*([("call", [("find", {"text": "x"})])] * agent.MAX_STEPS
                 + [("text", "Here is what I found so far.")]))
r = agent.answer("Q", "GIGMANN")
check(r and r["answer"].startswith("Here is"), "answers when the step budget runs out")
check(calls[-1]["tools"] is False and all(c["tools"] for c in calls[:-1]),
      "only the forced final turn is sent without tools")

# 6. Gemini unreachable: None, so engine.py falls back to the patterns.
reset()
script(("err", "Gemini unreachable"))
check(agent.answer("Q", "GIGMANN") is None, "no answer from the model returns None")
check(any("unreachable" in (m or "") for _, m, _ in frappe.logged), "and the reason is logged")

# 7. Follow-ups carry the last turns only, trimmed.
h = [{"q": f"q{i}", "a": f"a{i}"} for i in range(9)]
check(len(agent._history(h)) == 8, "history keeps the last four turns")

# 8. Oversized results are trimmed by rows, not cut mid-JSON.
big = {"rows": [{"n": "x" * 500}] * 200}
fit = agent._fit(big)
check("trimmed" in fit and len(fit["rows"]) < 200, "large results are trimmed by rows")

# 9. Every tool declaration is one Gemini accepts. One invalid schema -- an OBJECT with no
#    properties is the usual one -- makes Gemini refuse the whole request, and with it
#    every answer.
bad = []


def walk(name, sch, path):
    if sch.get("type") == "object" and not sch.get("properties") and path:
        bad.append(f"{name}:{path}")
    for k, v in (sch.get("properties") or {}).items():
        walk(name, v, f"{path}.{k}")
    if "items" in sch:
        walk(name, sch["items"], f"{path}[]")


for d in tools.declarations():
    walk(d["name"], d.get("parameters", {}), "")
check(not bad, f"tool schemas Gemini would reject: {bad}")
check(len({d["name"] for d in tools.declarations()}) == len(tools.declarations()),
      "tool names are unique")

# 10. Only allowlisted ERPNext reports run.
try:
    tools.run("run_report", {"report": "Some Custom Script Report"}, "GIGMANN")
    check(False, "an unlisted report is refused")
except tools.ToolError:
    check(True, "an unlisted report is refused")

print(f"analyst: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
