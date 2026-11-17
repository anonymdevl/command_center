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
frappe.local = types.SimpleNamespace()
frappe.conf = {"command_center_gemini_key": "test"}
frappe.logged = []
frappe.log_error = lambda title=None, message=None: frappe.logged.append(
    (title, message, frappe.db.rolled_back))
frappe.get_traceback = lambda: "Traceback: boom"


class _Cache:
    def __init__(self):
        self.d = {}

    def get_value(self, k):
        return self.d.get(k)

    def set_value(self, k, v, expires_in_sec=None):
        self.d[k] = v

    def delete_value(self, k):
        self.d.pop(k, None)


_cache = _Cache()
frappe.cache = lambda: _cache
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

REAL_CHAT = gemini.chat  # the scripted tests replace it; the model tests need the real one

agent._system_parts = lambda business_code: ("SYSTEM", "")
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

    def chat(contents, decls, system, timeout=40, mode="AUTO"):
        last = contents[-1]["parts"] if contents else []
        calls.append({"tools": decls is not None, "n_contents": len(contents), "mode": mode,
                      "responses": sum(1 for p in last if "functionResponse" in p)})
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
r = agent.answer("Q", "GIGMANN")
check(r and r["answered"] is False and "unreachable" in r["analyst_error"],
      "no answer from the model says so, with the reason, for the fallback to show")
check(any("unreachable" in (m or "") for _, m, _ in frappe.logged), "and the reason is logged")

# 7. Follow-ups carry the last turns only, trimmed.
h = [{"q": f"q{i}", "a": f"a{i}"} for i in range(9)]
check(len(agent._history(h)) == 8, "history keeps the last four turns")

# 8. Oversized results are trimmed by rows, not cut mid-JSON.
big = {"rows": [{"n": "x" * 500}] * 200}
fit = agent._fit(big)
check("trimmed" in fit and len(fit["rows"]) < 200, "large results are trimmed by rows")

# 8b. Live steps: each lookup is reported, in words; a broken reporter never stops an answer.
reset()
said = []
script(("call", [("find", {"text": "ubuntu"}), ("query_data", {"fact": "fact_purchase_invoice_line",
                                                                "group_by": ["supplier"]})]),
       ("text", "Done."))
tools.TOOLS["query_data"] = (lambda **k: {"data_set": "fact_purchase_invoice_line", "rows": []},
                             tools.TOOLS["query_data"][1])
r = agent.answer("Q", "GIGMANN", on_step=said.append)
check(said == ["Looking up “ubuntu”", "Adding up supplier bill lines by supplier"],
      f"each lookup is reported in plain words, got {said}")
reset()
script(("call", [("find", {"text": "x"})]), ("text", "Still answered."))
r = agent.answer("Q", "GIGMANN", on_step=lambda t: 1 / 0)
check(r and r["answer"] == "Still answered.", "a failing progress reporter does not stop the answer")

# 8c. The model may reply without a lookup ("Hi"), but not with figures it never read.
reset()
calls = script(("text", "Hi Michael. Ask me about sales, stock or who owes what."))
r = agent.answer("Hi", "GIGMANN")
check(r and r["answered"] and r["answer"].startswith("Hi Michael") and len(calls) == 1
      and calls[0]["mode"] == "AUTO", f"a greeting is answered as one, no lookup: {calls}")
reset()
calls = script(("text", "Customers owe GHS 9.18M."), ("call", [("find", {"text": "x"})]),
               ("text", "Customers owe GHS 9.18M (looked up)."))
r = agent.answer("How much are we owed?", "GIGMANN")
check([c["mode"] for c in calls] == ["AUTO", "ANY", "AUTO"] and r["answer"].endswith("(looked up)."),
      f"figures with nothing looked up are sent back to look: {[c['mode'] for c in calls]}")

# 8d. Every parallel call gets a response, even past the cap -- Gemini refuses the next
#     turn when the counts differ.
reset()
many = [("find", {"text": str(i)}) for i in range(agent.MAX_CALLS_PER_STEP + 3)]
calls = script(("call", many), ("text", "ok"))
agent.answer("Q", "GIGMANN")
check(calls[1]["responses"] == len(many),
      f"{len(many)} calls, {calls[1]['responses']} responses")

# 9. Every tool declaration is one Gemini accepts. One invalid schema -- an OBJECT with no
#    properties is the usual one -- makes Gemini refuse the whole request, and with it
#    every answer.
bad = []


def walk(name, sch, path):
    # Top level included: an empty parameters object is the case that broke the live
    # site, because the first version of this test skipped it.
    if sch.get("type") == "object" and not sch.get("properties"):
        bad.append(f"{name}:{path or 'parameters'}")
    for k, v in (sch.get("properties") or {}).items():
        walk(name, v, f"{path}.{k}")
    if "items" in sch:
        walk(name, sch["items"], f"{path}[]")


for d in tools.declarations():
    if "parameters" in d:
        walk(d["name"], d["parameters"], "")
check(not bad, f"tool schemas Gemini would reject: {bad}")
check(len({d["name"] for d in tools.declarations()}) == len(tools.declarations()),
      "tool names are unique")

# 10. Only allowlisted ERPNext reports run.
try:
    tools.run("run_report", {"report": "Some Custom Script Report"}, "GIGMANN")
    check(False, "an unlisted report is refused")
except tools.ToolError:
    check(True, "an unlisted report is refused")

# 11. Model choice when Google retires one (18 Oct 2026: 2.5 Flash 404'd for new keys).
listed = [{"name": f"models/{n}", "supportedGenerationMethods": m} for n, m in [
    ("gemini-2.5-flash", ["generateContent"]), ("gemini-3.8-flash", ["generateContent"]),
    ("gemini-3.8-flash-lite", ["generateContent"]), ("gemini-3.9-flash-preview", ["generateContent"]),
    ("gemini-3.8-flash-image", ["generateContent"]), ("gemini-flash-latest", ["generateContent"]),
    ("gemini-3.8-pro", ["generateContent"]), ("text-embedding-9", ["embedContent"])]]
check(gemini.choose_model(listed, "analyst") == "gemini-3.8-flash",
      f"the analyst takes the newest stable Flash: {gemini.choose_model(listed, 'analyst')}")
check(gemini.choose_model(listed, "router") == "gemini-3.8-flash-lite",
      f"the router prefers lite: {gemini.choose_model(listed, 'router')}")
check(gemini.choose_model([], "analyst") is None, "nothing suitable gives None")

# 12. A retired model: one re-choice from Google's list, one retry, remembered.
import types as _t
posted = []


class _R:
    def __init__(self, code, body):
        self.status_code, self._b, self.text = code, body, str(body)

    def json(self):
        return self._b


KEY_SENT = []


def _post(url, params=None, headers=None, json=None, timeout=None):
    # The key travels as Google's header, never in the address (17 Nov 2026).
    KEY_SENT.append(((params or {}).get("key"), (headers or {}).get("x-goog-api-key"), url))
    posted.append(url.split("/models/")[1].split(":")[0])
    if "gemini-3.8-flash:" in url:
        return _R(200, {"candidates": [{"content": {"role": "model", "parts": [{"text": "OK"}]}}]})
    return _R(404, {"error": {"message": "no longer available"}})


sys.modules["requests"] = _t.SimpleNamespace(post=_post, get=lambda *a, **k: _R(200, {"models": listed}))
_cache.d.clear()
frappe.conf.pop("command_center_analyst_model", None)
gemini.PREFERRED["analyst"] = "gemini-2.5-flash"
content, err = REAL_CHAT([{"role": "user", "parts": [{"text": "hi"}]}], None, "S")
check(KEY_SENT and all(k is None and h == frappe.conf["command_center_gemini_key"]
                       and "key=" not in u for k, h, u in KEY_SENT),
      f"the Gemini key is sent as the x-goog-api-key header, never in the URL: {KEY_SENT[:2]}")
check(err is None and posted == ["gemini-2.5-flash", "gemini-3.8-flash"],
      f"404 -> re-choose -> retry once: {posted}, {err}")
check(gemini.analyst_model() == "gemini-3.8-flash", "the working model is remembered")
posted.clear()
frappe.conf["command_center_analyst_model"] = "gemini-2.5-flash"
REAL_CHAT([{"role": "user", "parts": [{"text": "hi"}]}], None, "S")
check(posted == ["gemini-2.5-flash"], "a model named in site_config is never second-guessed")
frappe.conf.pop("command_center_analyst_model", None)

# 12b. An allowance used up (18 Oct 2026: free tier, 20 a day on 3.8 Flash): that model
# is remembered as out, the next one the key may use answers, and when every one is out
# the error says so in words, with when it comes back.
QUOTA = ('{"error": {"code": 429, "message": "You exceeded your current quota... Quota exceeded '
         'for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, '
         'limit: 20, model: gemini-3.8-flash\\nPlease retry in 9h41m36.7s.", '
         '"status": "RESOURCE_EXHAUSTED"}}')
posted.clear()
_cache.d.clear()
frappe.local = types.SimpleNamespace()
gemini.PREFERRED["analyst"] = "gemini-3.8-flash"


class _Q(_R):
    def __init__(self):
        self.status_code, self._b, self.text = 429, {}, QUOTA


def _post_q(url, params=None, headers=None, json=None, timeout=None):
    posted.append(url.split("/models/")[1].split(":")[0])
    if "gemini-3.8-flash-lite:" in url:
        return _R(200, {"candidates": [{"content": {"role": "model", "parts": [{"text": "OK"}]}}]})
    return _Q()


sys.modules["requests"] = _t.SimpleNamespace(post=_post_q, get=lambda *a, **k: _R(200, {"models": listed}))
content, err = REAL_CHAT([{"role": "user", "parts": [{"text": "hi"}]}], None, "S")
check(err is None and posted[0] == "gemini-3.8-flash" and posted[-1] == "gemini-3.8-flash-lite",
      f"a used-up allowance falls over to the next model: {posted}, {err}")
check(gemini.is_out("gemini-3.8-flash"), "the used-up model is remembered as out")
check(gemini.retry_after(QUOTA) == 9 * 3600 + 41 * 60 + 36, f"retry_after: {gemini.retry_after(QUOTA)}")
posted.clear()
REAL_CHAT([{"role": "user", "parts": [{"text": "hi"}]}], None, "S")
check(posted and posted[0] != "gemini-3.8-flash", f"a model that is out is not tried again: {posted}")
# A new key (a new Google project) has its own allowance: nothing learned under the old
# key carries over.
_old_key = frappe.conf["command_center_gemini_key"]
frappe.conf["command_center_gemini_key"] = "another-project"
check(not gemini.is_out("gemini-3.8-flash"), "a new key starts with every model available")
frappe.conf["command_center_gemini_key"] = _old_key
check(gemini.is_out("gemini-3.8-flash"), "the old key's used-up model is still remembered for it")

sys.modules["requests"] = _t.SimpleNamespace(post=lambda *a, **k: _Q(), get=lambda *a, **k: _R(200, {"models": listed}))
_cache.d.clear()
frappe.local = types.SimpleNamespace()
content, err = REAL_CHAT([{"role": "user", "parts": [{"text": "hi"}]}], None, "S")
check(content is None and err and "allowance" in err and "9h 41m" in err and "billing" in err,
      f"every model out: said in words, with when it is back: {err}")
_cache.d.clear()

# 12c. Plain figure questions are answered from the KPI engine, never sent to the model;
# anything asking for analysis is left to the analyst (ask/quick.py).
from command_center.ask import quick as _quick
for _q, _want in {
    "How many unpaid invoices do we have?": "ar_count",
    "How many unpaid supplier invoices are there?": "ap_count",
    "How much do we owe suppliers?": "ap_total",
    "How much are we owed?": "ar_total",
    "What is our stock worth?": "stock_value",
    "How many open sales orders do we have?": "order_book_count",
    "How many employees do we have?": "headcount",
    "Who owes us the most?": None,
    "How did unpaid invoices change over the last 6 months?": None,
    "Why are so many invoices unpaid?": None,
    "Show me unpaid invoices by customer": None,
}.items():
    _m = _quick.match(_q)
    check((_m[0][0] if _m else None) == _want, f"quick.match({_q!r}) gave {_m and _m[0][0]}, wanted {_want}")

# 12d. A tool is given only the arguments it takes: a model's extra one ("question")
# failed erpnext_count every time.
_seen_args = {}


def _probe(doctype, filters=None):
    _seen_args.update(doctype=doctype, filters=filters)
    return {"ok": True}


tools.TOOLS["_probe"] = (_probe, {})
tools.run("_probe", {"doctype": "Sales Invoice", "question": "how many?", "business_code": "X"}, "GIG")
check(_seen_args == {"doctype": "Sales Invoice", "filters": None},
      f"tools.run passed arguments the tool does not take: {_seen_args}")
tools.TOOLS.pop("_probe")

# 12e. The model is told the rule behind each figure, so a breakdown it builds agrees
# with the card (806, not 888 with the drafts counted).
from command_center.kpi.registry import load_all as _load_all
_defs = agent._definitions(_load_all())
check("ar_count: Unpaid Sales Invoices = count of rows in fact_sales_invoice where "
      "outstanding_amount > 0 and src_docstatus = 1" in _defs,
      "the definitions do not state the unpaid-invoices rule: " + _defs[:300])
check("users_active:" in _defs and "read straight from ERPNext" in _defs,
      "the live figures are missing from the definitions")
check(len(_defs) < 16000, f"the definitions are {len(_defs)} characters, too long for every call")
print("definitions:", len(_defs), "characters,", _defs.count("\n") + 1, "figures")

# 13. Thinking is asked for low; a model that refuses the setting is asked again without it.
sent = []


def _post2(url, params=None, headers=None, json=None, timeout=None):
    import copy
    sent.append(copy.deepcopy(json["generationConfig"]))
    if "thinkingConfig" in json["generationConfig"]:
        return _R(400, {"error": {"message": "Unknown name thinkingLevel at generationConfig.thinkingConfig"}})
    return _R(200, {"candidates": [{"content": {"role": "model", "parts": [{"text": "OK"}]}}]})


sys.modules["requests"] = _t.SimpleNamespace(post=_post2, get=lambda *a, **k: _R(200, {"models": listed}))
content, err = REAL_CHAT([{"role": "user", "parts": [{"text": "hi"}]}], None, "S")
check(err is None and sent[0].get("thinkingConfig") == {"thinkingLevel": "low"}
      and "thinkingConfig" not in sent[1] and "temperature" not in sent[0],
      f"low thinking, no temperature, and a retry without thinking on refusal: {sent}")

# 14. The time budget: with little left, the analyst answers instead of looking further.
calls_seen = []
_saved = gemini.chat


def _chat_budget(contents, decls, system, timeout=40, mode="AUTO"):
    calls_seen.append({"tools": decls is not None, "timeout": timeout})
    if decls is None:
        return {"role": "model", "parts": [{"text": "From what I have so far."}]}, None
    return {"role": "model", "parts": [{"functionCall": {"name": "find", "args": {"text": "x"}}}]}, None


gemini.chat = _chat_budget
reset()
r = agent.answer("Q", "GIGMANN", deadline=29)
check(r and r["answered"] and calls_seen[0]["tools"] and not calls_seen[1]["tools"],
      f"a spent budget ends in an answer, not a timeout: {calls_seen}")
check(calls_seen[0]["timeout"] in (25, 26), f"each call gets what is left: {calls_seen[0]['timeout']}")
check(r.get("cut_short") and r.get("_resume") and "functionResponse" in
      r["_resume"]["contents"][-1]["parts"][0],
      "a cut-short answer says so, and keeps the conversation up to the last lookup's result")

# 14b. A deeper look resumes from there: no forced first lookup, more rounds, the earlier
#      lookups kept in "what it checked".
calls_seen.clear()
modes = []


def _chat_resume(contents, decls, system, timeout=40, mode="AUTO"):
    modes.append((mode, len(contents)))
    return {"role": "model", "parts": [{"text": "The fuller answer."}]}, None


gemini.chat = _chat_resume
r2 = agent.answer("Q", "GIGMANN", resume=r["_resume"], max_steps=20, deadline=600)
check(r2["answer"] == "The fuller answer." and modes[0][0] == "AUTO"
      and modes[0][1] == len(r["_resume"]["contents"]) and r2["checked"][:1] == r["checked"][:1],
      f"resume continues where it stopped: {modes}")
gemini.chat = _saved


# 15. A timeout says so in words, not a traceback.
class _Timeout(Exception):
    pass


def _post_slow(*a, **k):
    raise _Timeout("read timed out")


sys.modules["requests"] = _t.SimpleNamespace(
    post=_post_slow, get=lambda *a, **k: _R(200, {"models": listed}),
    exceptions=_t.SimpleNamespace(Timeout=_Timeout, ConnectionError=ConnectionError))
content, err = REAL_CHAT([{"role": "user", "parts": [{"text": "hi"}]}], None, "S", timeout=40)
check(content is None and "did not reply in time" in (err or ""), f"timeout message: {err}")

# 16. A model that stalls is left for the next, the person is told, and it is remembered
# (19 Oct 2026: one call waited its full 60 seconds and the question failed).
_cache.d.clear()
frappe.conf.pop("command_center_analyst_model", None)
gemini.PREFERRED["analyst"] = "gemini-3.8-flash"
asked, said = [], []


def _post_stall(url, params=None, headers=None, json=None, timeout=None):
    model = url.split("/models/")[1].split(":")[0]
    asked.append((model, timeout))
    if model == "gemini-3.8-flash":
        raise _Timeout("read timed out")
    return _R(200, {"candidates": [{"content": {"role": "model", "parts": [{"text": "OK"}]}}]})


sys.modules["requests"] = _t.SimpleNamespace(
    post=_post_stall, get=lambda *a, **k: _R(200, {"models": listed}),
    exceptions=_t.SimpleNamespace(Timeout=_Timeout, ConnectionError=ConnectionError))
frappe.local.cc_on_step = said.append
content, err = REAL_CHAT([{"role": "user", "parts": [{"text": "hi"}]}],
                         [{"name": "t", "description": "d"}], "S", timeout=60)
check(err is None and [m for m, _ in asked][:2] == ["gemini-3.8-flash", "gemini-2.5-flash"],
      f"a stalled model is swapped for the next: {asked}, {err}")
check(asked[0][1] == gemini.REPLY_WAIT, f"it waits {gemini.REPLY_WAIT}s, not the whole budget: {asked}")
check(said and "did not reply" in said[0] and "Gemini 2.5 Flash" in said[0], f"the person is told: {said}")
asked.clear()
REAL_CHAT([{"role": "user", "parts": [{"text": "hi"}]}], None, "S", timeout=60)
check(asked and asked[0][0] != "gemini-3.8-flash", f"the slow model is skipped next time: {asked}")
frappe.local.cc_on_step = None

# 17. Undelivered orders are goods to deliver, never "money we owe" (19 Oct 2026).
check("never \"we owe them\"" in agent.SYSTEM.replace("\\\n", ""),
      "the analyst is told undelivered orders are not money we owe")
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "command_center",
                         "ask", "intents.py")).read()
check("owe them" not in _src.replace("we still owe them", ""),
      "the built-in answers do not call undelivered orders money we owe")

# 18. Claude (14 Nov 2026). The same loop on Anthropic's message shapes: the session's
# scope still wins, every tool_use gets its tool_result by id, an instruction after the
# results joins that unsent turn rather than editing a sent one, and the provider is
# Claude once its key is on the site.
from command_center.ask import claude, llm  # noqa: E402

REAL_CLAUDE_CHAT = claude.chat
check(llm.provider() == "gemini", "with only a Gemini key, Gemini answers")
frappe.conf["command_center_anthropic_key"] = "test"
check(llm.provider() == "claude", "with an Anthropic key, Claude answers")
frappe.conf["command_center_ai_provider"] = "gemini"
check(llm.provider() == "gemini", "a provider named in site_config is the one used")
frappe.conf["command_center_ai_provider"] = "claude"
_k = frappe.conf.pop("command_center_anthropic_key")
check(llm.provider() is None, "a provider named without its key is not used")
frappe.conf["command_center_anthropic_key"] = _k


def claude_script(*turns):
    sent = []
    it = iter(turns)

    def chat(messages, decls, static, dynamic, kind="analyst", timeout=60, final=False):
        sent.append({"messages": json.loads(json.dumps(messages)), "decls": decls,
                     "kind": kind, "final": final})
        kind_, payload = next(it)
        if kind_ == "err":
            return None, payload
        if kind_ == "text":
            return [{"type": "thinking", "thinking": "", "signature": "sig"},
                    {"type": "text", "text": payload}], None
        return [{"type": "thinking", "thinking": "", "signature": "sig"}] + [
            {"type": "tool_use", "id": f"tu_{i}", "name": n, "input": a}
            for i, (n, a) in enumerate(payload)], None
    claude.chat = chat
    return sent


import json  # noqa: E402

reset()
sent = claude_script(("call", [("find", {"text": "ubuntu", "business_code": "SOMEONE-ELSE"}),
                               ("find", {"text": "akai"})]),
                     ("text", "UBUNTU owes **GHS 636,675**."))
r = agent.answer("How much does Ubuntu owe?", "GIGMANN")
check(r and r["answered"] and r["planner"] == "claude" and "636,675" in r["answer"],
      f"Claude answers after a tool call: {r}")
check(seen.get("find") == "GIGMANN", "Claude's call runs in the session's scope, not the model's")
_second = sent[1]["messages"]
_results = _second[-1]["content"]
check(_second[-2]["role"] == "assistant" and _second[-2]["content"][0]["type"] == "thinking",
      "the reply goes back unchanged, thinking block included")
check([b["tool_use_id"] for b in _results] == ["tu_0", "tu_1"]
      and all(b["type"] == "tool_result" for b in _results),
      f"every tool_use gets its tool_result, by id, in order: {_results}")
check(sent[0]["decls"] == sent[1]["decls"] and sent[0]["decls"],
      "the same tool list goes on every round (changing it edits the history)")

reset()
sent = claude_script(*([("call", [("find", {"text": "x"})])] * agent.MAX_STEPS
                       + [("text", "Done, from what I have.")]))
r = agent.answer("Q", "GIGMANN")
check(r and r["answered"] and sent[-1]["final"] and sent[-1]["decls"],
      "out of rounds, the last request asks for the answer, tools still declared")
_last = sent[-1]["messages"][-1]
check(_last["role"] == "user" and _last["content"][0]["type"] == "tool_result"
      and _last["content"][-1]["type"] == "text",
      "the 'answer now' instruction joins the unsent tool-result turn, after the results")

reset()
sent = claude_script(("text", "We are owed GHS 9,177,568.91."), ("call", [("find", {"text": "x"})]),
                     ("text", "Looked up: GHS 1."))
r = agent.answer("How much are we owed?", "GIGMANN")
check(len(sent) == 3 and "without looking anything up" in json.dumps(sent[1]["messages"][-1]),
      "a figure stated from memory is sent back to be looked up")

reset()
sent = claude_script(("call", [("find", {"text": "x"})]), ("text", "ok"))
r = agent.answer("Q", "GIGMANN", deep=True)
check(sent and all(x["kind"] == "deep" for x in sent), "the deeper look runs on the deep model")
check(claude.model_for("deep") == "claude-opus-5-5" and claude.model_for("analyst") == "claude-sonnet-5-5",
      "Sonnet 5.5 for everyday questions, Opus 5.5 for the deeper look")

reset()
sent = claude_script(("call", [("writes_underneath", {})]), ("text", "Done."))
r = agent.answer("Q", "GIGMANN")
check(frappe.db.rolled_back == 1, "a write while Claude answers is rolled back too")

# The request itself: the fixed opening is cached, what varies comes after the marker,
# no forced tool use, and nothing in the opening that changes between questions.
claude.chat = REAL_CLAUDE_CHAT
_decls = tools.declarations()
b1 = claude.request([{"role": "user", "content": "a"}], _decls, "STATIC", "Today is 1", "analyst")
b2 = claude.request([{"role": "user", "content": "b"}], _decls, "STATIC", "Today is 2", "analyst",
                    final=True)
check(b1["system"][0]["text"] == "STATIC" and "cache_control" in b1["system"][0]
      and "cache_control" not in b1["system"][1],
      "the cache marker is on the fixed instructions, and the dated line comes after it")
check(json.dumps(b1["tools"]) == json.dumps(b2["tools"]) and b1["system"][0] == b2["system"][0],
      "two questions send a byte-identical opening (tools, then the fixed instructions)")
check("tool_choice" not in b1 and b2["tool_choice"] == {"type": "none"},
      "no forced tool use; the last round asks for the answer with tool_choice none")
check(b1["thinking"] == {"type": "adaptive"} and b1["output_config"]["effort"] == "medium",
      "adaptive thinking at medium effort for everyday questions")
check(all(t.get("input_schema", {}).get("type") == "object" for t in b1["tools"]),
      "every tool has an object input schema, the ones that take nothing too")
check({t["name"] for t in b1["tools"]} == set(tools.TOOLS),
      "Claude is offered exactly the read tools in the registry, nothing else")
check(not ({"{today}", "{as_of}", "{business}"} & set(
    x for x in ("{today}", "{as_of}", "{business}") if x in agent.SYSTEM)),
      "the fixed instructions carry no date, horizon or business name (they would defeat the cache)")
check(claude.label("claude-sonnet-5-5") == "Claude Sonnet 5.5", claude.label("claude-sonnet-5-5"))
check(claude.questions_per_minute({"requests_per_minute": 50, "input_tokens_per_minute": 30000,
                                   "output_tokens_per_minute": 8000}) == 1,
      "questions a minute are the tightest of the three limits")
frappe.conf.pop("command_center_anthropic_key", None)
frappe.conf.pop("command_center_ai_provider", None)
_r = REAL_CLAUDE_CHAT([], [], "S", "D")
check(_r == (None, "no Anthropic key configured"), f"no key, no call: {_r}")

# 19. Stop (15 Nov 2026). The flag is read between rounds and before each lookup; a
# stopped question ends with no further model call, in a partial answer made only of
# what was in hand -- the model's own words and the figures its lookups returned.
frappe.conf["command_center_anthropic_key"] = "test"
frappe.whitelist = lambda *a, **k: (lambda f: f)  # api/ modules are imported from here on
_FIG = {"ar_total": {"label": "Owed to us", "value": 9177568.91, "unit": "currency",
                     "currency": "GHS", "note": "806 unpaid invoices"}}
tools.TOOLS["get_figures"] = (lambda keys=None, business_code=None: _FIG,
                              tools.TOOLS["get_figures"][1])
_flag = {"on": False}
reset()
sent = claude_script(("call", [("get_figures", {"keys": ["ar_total"]})]),
                     ("call", [("find", {"text": "never run"})]), ("text", "never sent"))


def _stop_after_first_lookup():
    return _flag["on"]


_orig_run = tools.run


def _run_then_stop(name, args, business_code=None):
    out = _orig_run(name, args, business_code)
    _flag["on"] = True  # the person presses Stop while this lookup runs
    return out


tools.run = _run_then_stop
said = []
r = agent.answer("How much are we owed?", "GIGMANN", should_stop=_stop_after_first_lookup,
                 on_step=said.append)
tools.run = _orig_run
check(len(sent) == 1, f"no model call after Stop: {len(sent)} calls")
check(r and r["answered"] and r["stopped"] and r["answer"].startswith("**" + agent.STOPPED),
      f"a stopped question answers with the stopped note: {r and r['answer'][:80]}")
check("Owed to us: GHS 9,177,568.91 (806 unpaid invoices)" in r["answer"],
      f"the partial answer keeps the figures already read, as the tool gave them: {r['answer']}")
check(not r["cut_short"] and r["_resume"] is None, "a stopped question never starts a deeper look")
check(seen.get("find") is None, "the lookups chosen after Stop are not run")
check(said and said[0].kind == "get_figures" and said[0].group == "Reading the headline figures"
      and said[0] == "Reading the headline figures",
      f"each step carries its kind and group, and is still its words: {said}")

# Stopped before the first round: nothing is sent at all. The flag set by api/ask.py is
# read from frappe.local when no should_stop is passed.
reset()
sent = claude_script(("text", "never sent"))
frappe.local.cc_should_stop = lambda: True
r = agent.answer("Q", "GIGMANN")
frappe.local.cc_should_stop = None
check(not sent and r["stopped"] and "Nothing had been looked up yet" in r["answer"],
      f"stopped before it began: no model call, and it says so: {len(sent)}, {r.get('answer')}")

# Stopped while the model was choosing lookups: they are not run; its words are kept.
reset()
_calls = {"n": 0}


def _chat_words(messages, decls, static, dynamic, kind="analyst", timeout=60, final=False):
    _calls["n"] += 1
    _flag["on"] = True
    return [{"type": "text", "text": "Checking the ageing first."},
            {"type": "tool_use", "id": "tu_0", "name": "find", "input": {"text": "x"}}], None


claude.chat = _chat_words
_flag["on"] = False
r = agent.answer("Q", "GIGMANN", should_stop=lambda: _flag["on"])
check(_calls["n"] == 1 and seen.get("find") is None and "Checking the ageing first." in r["answer"],
      f"the lookups chosen as Stop arrived are not run, its words are kept: {r['answer']}")

# A flag that cannot be read never stops an answer.
reset()
sent = claude_script(("text", "Answered."))
r = agent.answer("Q", "GIGMANN", should_stop=lambda: 1 / 0)
check(r["answer"] == "Answered." and not r.get("stopped"), "a broken stop flag is ignored")
claude.chat = REAL_CLAUDE_CHAT
frappe.conf.pop("command_center_anthropic_key", None)

# 20. Live steps as the page reads them (api/ask._record): {text, kind, group}; a run of
# one kind is kept whole (the page shows "×N"), a repeated message with no kind once.
from command_center.api import ask as _ask_api  # noqa: E402

_steps = []
for _s in [tools.step("run_report", {"report": "General Ledger"}),
           tools.step("run_report", {"report": "Trial Balance"}),
           "Gemini 3.8 Flash did not reply; trying another", "Gemini 3.8 Flash did not reply; trying another",
           tools.step("erpnext_list", {"doctype": "Quotation"}), tools.step("erpnext_count", {"doctype": "Lead"})]:
    _ask_api._record(_steps, _s)
check([x["kind"] for x in _steps] == ["run_report", "run_report", None, "erpnext", "erpnext"],
      f"steps recorded with their kinds, repeats of a kindless message once: {_steps}")
check(_steps[0] == {"text": "Running ERPNext's General Ledger", "kind": "run_report",
                    "group": "Running an ERPNext report"}, f"a step's words: {_steps[0]}")
check(tools.describe("compare_periods", {"fact": "fact_sales_invoice_line", "measure": "base_net_amount"})
      == "Comparing base net amount in sales invoice lines with an earlier period",
      tools.describe("compare_periods", {"fact": "fact_sales_invoice_line", "measure": "base_net_amount"}))
check(set(tools.STEP_KINDS) >= set(tools.TOOLS) - {"writes_underneath", "boom"},
      f"every tool has a step group: {set(tools.TOOLS) - set(tools.STEP_KINDS)}")
check("compare_periods" in agent.SYSTEM and "compare_periods" in tools.TOOLS,
      "the compare tool is offered and documented in the instructions")

# 21. The page's grouping of those steps (frontend/src/legacy/steps.js), run in Node.
import shutil  # noqa: E402
import subprocess  # noqa: E402

_node = shutil.which("node")
if _node:
    _t = subprocess.run([_node, os.path.join(ROOT, "scripts", "test_steps.mjs")],
                        capture_output=True, text=True, timeout=60)
    check(_t.returncode == 0, "scripts/test_steps.mjs failed:\n" + (_t.stdout + _t.stderr)[-800:])
else:
    print("note: node is not installed here, so the page's step grouping was not run")

print(f"analyst: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
