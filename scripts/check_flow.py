"""Preflight rules for the task and approval flows (api/actions.py, api/work.py and the
screens that call them), each written against a fault found on 17 Nov 2026:

  business     every write goes to the business of the record it acts on. "All
               businesses" fell back to the default business, so B's alert was assigned
               on A's ERPNext. The server refuses it; no screen sends the scope instead.
  give_first   a move gives to the new person before it takes from the old. Reassign
               removed first, so a refused add left the work with nobody.
  escaped      every comment written to a business's ERPNext is built by a builder that
               escapes every value. Send Back wrote the manager's note as raw markup.
  stale        a decision carries the state its card showed, and the connectors check it
               against a fresh read. Approve on L1's card performed L2.
  idempotent   every To-Do or Task the platform creates is looked for first, so a retry
               after a lost answer does not make it twice.
  bulk_job     bulk changes run as a background job (200 tasks outlast a web request),
               and the summary says who was not told.
  not_known    a person whose ERPNext user could not be read "may not have been
               notified", never "notified".
  roles        the remote roles include the automatic ones (All, Guest, Desk User).
  tags         Accepted is an exact tag, not a substring.

`problems(src)` checks a dict of file texts; `selftest()` breaks each rule on purpose and
confirms it is caught, so a rule that can no longer fail is itself a failure.
"""

from __future__ import annotations

import ast
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = {
    "actions": "command_center/api/actions.py",
    "work": "command_center/api/work.py",
    "remote": "command_center/connectors/remote.py",
    "local": "command_center/connectors/local.py",
    "dialog": "frontend/src/components/ActionDialog.jsx",
    "drawer": "frontend/src/components/TaskDrawer.jsx",
    "workjs": "frontend/src/legacy/work.js",
    "alertsjs": "frontend/src/legacy/alerts.js",
}

COMMENT_BUILDERS = {"_mention_html", "_note_html", "_mention", "_escalation_note"}
GIVES = ("_assign(", "_todo(", "conn.assign(", "conn.insert(")
TAKES = ("conn.unassign(", '"status", "Cancelled"')


def read() -> dict:
    return {k: open(os.path.join(ROOT, p)).read() for k, p in FILES.items()}


def _functions(text):
    tree = ast.parse(text)
    lines = text.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node, "\n".join(lines[node.lineno - 1:node.end_lineno])


def _body(text, name):
    return next((b for n, b in _functions(text) if n.name == name), "")


def _method(text, cls, name):
    """The source of method `name` of class `cls`."""
    lines = text.splitlines()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for f in node.body:
                if isinstance(f, ast.FunctionDef) and f.name == name:
                    return "\n".join(lines[f.lineno - 1:f.end_lineno])
    return ""


def _callee(node):
    f = node.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None


def problems(src: dict) -> list[str]:
    out = []

    # -- business -------------------------------------------------------------------
    biz = _body(src["actions"], "_business")
    if not biz or "default_business_code" in biz or "frappe.throw" not in biz:
        out.append("business: actions._business must refuse “All businesses” for a write and "
                   "never fall back to the default business")
    if "actions._business(" not in _body(src["work"], "review"):
        out.append("business: work.review must resolve its business with actions._business, "
                   "so a Send Back or Accept never lands on the default business")
    for key in ("dialog", "drawer"):
        if re.search(r"business_code:\s*scope\b", src[key]):
            out.append(f"business: {FILES[key]} sends the screen's scope as the business; send "
                       f"the record's own (businessOf / task.business_code)")
    if "business_code: a.business_code" not in src["alertsjs"]:
        out.append("business: legacy/alerts.js does not send each alert's own business")
    tr = re.search(r"export function taskRequest\(kind, t\) \{(.*?)\n\}", src["workjs"], re.S)
    if not tr or "business_code: t.business_code" not in tr.group(1):
        out.append("business: legacy/work.js taskRequest does not send the task's own business")
    for key in ("workjs", "drawer"):
        for m in re.finditer(r'fire\((?:"cc-action", )?\{ kind: "(decide|review|bulk_tasks)"', src[key]):
            event = src[key][m.start():src[key].find("})", m.end())]
            if "business_code" not in event:
                out.append(f"business: {FILES[key]} fires {m.group(1)} without the record's "
                           f"own business")

    # -- give_first -----------------------------------------------------------------
    for node, body in _functions(src["actions"]):
        gives = [i for i, ln in enumerate(body.splitlines()) if any(g in ln for g in GIVES)
                 and not ln.strip().startswith(("#", "def "))]
        takes = [i for i, ln in enumerate(body.splitlines()) if any(t in ln for t in TAKES)
                 and not ln.strip().startswith("#")]
        if gives and takes and min(takes) < max(gives):
            out.append(f"give_first: actions.{node.name} takes work off someone before it has "
                       f"given it to the new person; give first, remove after")
    if not _body(src["actions"], "_reassign"):
        out.append("give_first: actions._reassign is gone; the rule has nothing to hold")

    # -- escaped --------------------------------------------------------------------
    for key in ("actions", "work"):
        for node in ast.walk(ast.parse(src[key])):
            if not isinstance(node, ast.Call):
                continue
            name = _callee(node)
            arg = (node.args[2] if name == "comment" and len(node.args) >= 3 else
                   node.args[1] if name == "add_comment" and len(node.args) >= 2 else None)
            if arg is None:
                continue
            if not (isinstance(arg, ast.Call) and _callee(arg) in COMMENT_BUILDERS):
                out.append(f"escaped: {FILES[key]}:{node.lineno} writes a comment not built by "
                           f"{sorted(COMMENT_BUILDERS)}, so its text may reach ERPNext unescaped")
    for name in ("_mention_html", "_note_html"):
        fn = next((n for n, _ in _functions(src["actions"]) if n.name == name), None)
        if fn is None:
            out.append(f"escaped: actions.{name} is gone")
            continue
        for v in ast.walk(fn):
            if isinstance(v, ast.FormattedValue) and not (
                    isinstance(v.value, ast.Call) and _callee(v.value) == "escape"):
                out.append(f"escaped: actions.{name} puts a value into the comment without "
                           f"escape() (line {v.lineno})")

    # -- stale ----------------------------------------------------------------------
    awa = _body(src["actions"], "apply_workflow_action")
    if "expected_state" not in awa or "expected=" not in awa or "frappe.throw" not in awa:
        out.append("stale: apply_workflow_action must require the card's expected_state and "
                   "pass it to the connector")
    for key in ("remote", "local"):
        if "check_unchanged(" not in _body(src[key], "apply_workflow"):
            out.append(f"stale: {FILES[key]} apply_workflow does not check the document against "
                       f"what the card showed")
    if "state: a.state" not in src["workjs"] or "expected_state: req.state" not in src["dialog"]:
        out.append("stale: the approval card must send the state it showed (work.js) and the "
                   "dialog must pass it on (ActionDialog.jsx)")

    # -- idempotent -----------------------------------------------------------------
    for node, body in _functions(src["actions"]):
        if "conn.insert(" in body and re.search(r'"doctype": "(ToDo|Task)"', body):
            look = min((body.find(k) for k in ("_recent_todo(", "_recent_task(") if k in body),
                       default=-1)
            if look < 0 or look > body.find("conn.insert("):
                out.append(f"idempotent: actions.{node.name} creates a To-Do or Task without first "
                           f"looking for the one an earlier try made")

    # -- bulk_job -------------------------------------------------------------------
    bulk = _body(src["actions"], "bulk_tasks")
    if "frappe.enqueue(" not in bulk or re.search(r"^\s+for \w+ in todos:", bulk, re.M):
        out.append("bulk_job: bulk_tasks must queue the batch as a job, not work through it "
                   "inside the web request")
    if '"not_told"' not in _body(src["actions"], "_bulk_view") or "not_told" not in src["dialog"]:
        out.append("bulk_job: the bulk summary must list who was not told, and the dialog show it")

    # -- not_known ------------------------------------------------------------------
    for name, pat in (("_tell", "mentionable is None"), ("_todo", "mentionable is None"),
                      ("_tell_escalated", 'esc["mentionable"] is None')):
        b = _body(src["actions"], name)
        if pat not in b or "may not have been" not in b:
            out.append(f"not_known: actions.{name} must say “may not have been notified” when "
                       f"the person's ERPNext user could not be read")

    # -- roles / tags ---------------------------------------------------------------
    if "automatic_roles(" not in _method(src["work"], "_Remote", "roles"):
        out.append("roles: work._Remote.roles must add the automatic roles (All, Guest, Desk User)")
    if re.search(r"ACCEPTED_TAG in \(?\s*r\._user_tags", src["work"]) or "_tags(r._user_tags)" not in src["work"]:
        out.append("tags: Accepted must be read as an exact tag (work._tags), not a substring")
    return out


# Each rule broken on purpose: (file, what is replaced, by what, the rule that must catch it).
MUTATIONS = [
    ("actions", "    if business_code and business_code != ALL:\n        return business_code\n",
     "    if business_code or default_business_code():\n        return business_code\n",
     "business"),
    ("alertsjs", "business_code: a.business_code", "biz: a.business_code", "business"),
    ("dialog", "business_code: business, todo: req.todo, to_user: to", "business_code: scope, todo: req.todo, to_user: to", "business"),
    ("workjs", "business_code: t.business_code, title: t.title", "title: t.title", "business"),
    ("workjs", 'kind: "decide", business_code: a.business_code,', 'kind: "decide",', "business"),
    ("drawer", 'verdict: "return", business_code: biz,', 'verdict: "return",', "business"),
    ("actions", "    # 1. Give it to the new person.",
     "    conn.unassign(doctype, name, old)\n    # 1. Give it to the new person.",
     "give_first"),
    ("work", 'actions._note_html(f"Accepted by {who}." + (f" {note}" if note else ""))',
     'f"Accepted by {who}." + (f" {note}" if note else "")', "escaped"),
    ("actions", "return f\"<p>{escape(str(text or ''))}</p>\"", "return f\"<p>{text}</p>\"", "escaped"),
    ("remote", "        check_unchanged(doc, expected)\n", "", "stale"),
    ("workjs", "state: a.state, ", "", "stale"),
    ("actions", "    name = _recent_todo(conn, me, user, body)\n", "    name = None\n", "idempotent"),
    ("actions", '    frappe.enqueue("command_center.api.actions._bulk_run"',
     '    for todo in todos: pass\n    frappe.enqueue("command_center.api.actions._bulk_run"', "bulk_job"),
    ("actions", "    if mentionable is None:\n        return None, (",
     "    if mentionable is ...:\n        return None, (", "not_known"),
    ("work", "return got | automatic_roles(self._user_type(user))", "return got", "roles"),
    ("work", "ACCEPTED_TAG in _tags(r._user_tags)", "ACCEPTED_TAG in (r._user_tags or \"\")", "tags"),
]


def selftest(src: dict) -> list[str]:
    """Each mutation must be caught by its own rule; a rule that cannot fail is reported."""
    out = []
    for key, old, new, rule in MUTATIONS:
        if old not in src[key]:
            out.append(f"check_flow selftest: the {rule} mutation no longer applies to "
                       f"{FILES[key]} ({old[:50]!r}); update it so the rule is still proved")
            continue
        broken = dict(src, **{key: src[key].replace(old, new, 1)})
        try:
            found = problems(broken)
        except SyntaxError:
            found = []
        if not any(p.startswith(rule + ":") for p in found):
            out.append(f"check_flow selftest: breaking {FILES[key]} for the {rule} rule was not "
                       f"caught; the rule cannot fail")
    return out


if __name__ == "__main__":
    s = read()
    got = problems(s) + selftest(s)
    print("\n".join(got) or f"check_flow: {len(MUTATIONS)} rules proved, all clear")
    raise SystemExit(1 if got else 0)
