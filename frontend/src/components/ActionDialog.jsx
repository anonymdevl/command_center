import React, { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import { boot, brand } from "../api/boot.js";
import { useLayer } from "../backstack.js";

/**
 * Put a piece of work on someone's desk, from wherever it was noticed.
 *
 * Opened by the buttons on alerts, findings and the like (legacy/actions.js) through a
 * "cc-action" event. Whatever the kind -- assign, request evidence, escalate, raise a
 * finding -- the work is handed out in the business's ERPNext as the manager who sent it
 * (api/actions.create_task), and the person is told there. When it concerns one ERPNext
 * document (req.doctype / req.docname: an alert whose records are exactly one), ERPNext
 * assigns that document to them: their To-Do, the document's Assigned To, and ERPNext's
 * own notification. Otherwise it is a To-Do of its own, with a mention that notifies
 * them. The dialog says which before sending, and afterwards whether they were notified.
 * The assistant never reaches this; only a person pressing the button does.
 *
 * Escalate goes up the line. It asks whose work it is (pre-filled from the To-Do it was
 * given out as, or the document's Assigned To: api/actions.whose_work), reads their
 * manager from ERPNext's Reports To (actions.manager_of, as this manager), and says
 * before sending exactly who it goes to and why. When ERPNext names no manager it says
 * why and how to fix that there, and the sender chooses someone themselves -- never
 * silently. The person whose work it is stays on it and is told it was escalated.
 *
 * Two decisions come through here too (legacy/work.js): "decide" applies a workflow
 * action to a document waiting on this person, and "review" accepts or sends back work
 * they handed out. Both ask first and say exactly what will change; after either, a
 * "cc-work-changed" event tells the screen to read the queue again.
 *
 * Outstanding Tasks (16 Nov 2026): "new_task" is this same form with a subject, a
 * priority and, optionally, the ERPNext document it concerns (assigned on it through
 * assign_to.add); "reassign", "cancel_task" and "edit_task" change open work the manager
 * handed out (TaskChange below, api/actions reassign_task / cancel_task / update_task),
 * asking first and saying afterwards whether each person was told.
 *
 * Close (17 Nov 2026): "close_task" closes open work handed out as finished or no longer
 * needed (api/actions close_task): a calm comment on the To-Do, no mention, nobody told.
 * "bulk_tasks" is Close Selected / Cancel Selected on Outstanding Tasks (BulkChange): it
 * says how many and to whom before anything changes, then sends them one by one
 * (api/actions bulk_tasks) and says how many were done and why any were not.
 *
 * The business (17 Nov 2026). Every action goes to the business of the record it acts
 * on -- the alert's, the task row's, the approval card's, the drawer's (req.business_code,
 * set where the event is fired) -- never to the screen's scope: in "All businesses" that
 * is no business, and it used to fall back to the default one, so business B's alert was
 * assigned on business A's ERPNext. A request that carries none (a designed screen's
 * button) goes to the business shown, or, in "All businesses", to the one chosen here;
 * the people listed are always that business's. Bulk Close / Cancel runs as a job the
 * dialog follows (bulk_status), and says how many were told and who was not. A write
 * ERPNext did not confirm ("NotConfirmed") says it may have gone through and to check
 * before trying again; trying again does not make the To-Do twice (api/actions).
 */

const KINDS = {
  assign: { title: "Assign this", verb: "Assign", lead: "", days: 3 },
  evidence: { title: "Request evidence", verb: "Send the request", lead: "Please send the evidence for: ", days: 3 },
  escalate: { title: "Escalate", verb: "Escalate", lead: "Escalated: ", days: 1, priority: "High" },
  finding: { title: "Raise as a finding", verb: "Raise it", lead: "Finding: ", days: 7 },
  new_task: { title: "New Task", verb: "Create Task", lead: "", days: 3 },
};

/** Changes to open work the manager handed out (TaskChange). */
const CHANGES = new Set(["reassign", "cancel_task", "close_task", "edit_task"]);
const PRIORITIES = ["Low", "Medium", "High"];

let peopleCache = {};

const realScopes = () => (boot.scopes || []).filter((s) => s.code && s.code !== "__all__");

/** The business an action goes to: the record's own; else the one on screen; never
 *  "All businesses" (api/actions._business refuses it). "" when it must be chosen. */
export function businessOf(req, scope) {
  if (req?.business_code) return req.business_code;
  if (scope && scope !== "__all__") return scope;
  const real = realScopes();
  return real.length === 1 ? real[0].code : "";
}

/** People of one business, read once per business. */
function loadPeople(business, set) {
  if (!business) {
    set([]);
    return;
  }
  if (peopleCache[business]) {
    set(peopleCache[business]);
    return;
  }
  api.people(business).then((p) => {
    peopleCache[business] = p || [];
    set(peopleCache[business]);
  }).catch(() => set([]));
}

/** A refusal in words; one ERPNext did not confirm says it may have gone through. */
function Failure({ error, unsure }) {
  if (!error) return null;
  return (
    <div className="dlg-err" role="alert">
      {unsure ? <b>Not confirmed: it may have gone through. Check in ERPNext before trying again. </b> : null}
      {error}
    </div>
  );
}

const unsureOf = (err) => err?.excType === "NotConfirmed";

const firstName = (name) => (name || "").trim().split(/\s+/)[0] || name || "";

/** Who an escalation goes to and why, before it is sent. */
function escalationPlan(mgr, ofName, toUser, toName) {
  const of = firstName(ofName);
  const stays = `${of} stays on it and is told it was escalated.`;
  if (!toUser) return mgr?.found ? "" : "Choose who it goes to.";
  if (mgr?.found && mgr.manager_user === toUser) {
    return `Escalates to ${mgr.manager_name}, ${of}’s manager in ERPNext (Reports To). ${stays}`;
  }
  if (mgr?.found) {
    return `Escalates to ${toName}, chosen by you. ERPNext names ${mgr.manager_name} as ${of}’s `
      + `manager (Reports To). ${stays}`;
  }
  return `Escalates to ${toName}, chosen by you, because ERPNext names no manager for ${of}. ${stays}`;
}

/** What sending will do, in plain words, before it is sent. */
function plan(req, name, doc) {
  const them = name || "the person you choose";
  if (doc?.doctype && doc?.name) {
    return `Assigns ${doc.doctype} ${doc.name} to ${them} in ERPNext, as you: it goes on their To-Do list, `
      + "the document shows them under Assigned To, and ERPNext notifies them.";
  }
  if (req.doctype && req.docname) {
    return `Assigns ${req.doctype} ${req.docname} to ${them} in ERPNext, as you: it goes on their To-Do list, `
      + "the document shows them under Assigned To, and ERPNext notifies them.";
  }
  return `Puts this on ${them}’s To-Do list in ERPNext, from you, and mentions them on it so ERPNext `
    + "notifies them. It concerns no single ERPNext document, so no document changes.";
}

function addDays(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  // The local date, not toISOString's UTC one, which is a day out east or west of GMT.
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export default function ActionDialog({ scope }) {
  const [req, setReq] = useState(null); // {kind, title, detail, owner} or a decision
  const [people, setPeople] = useState([]);
  const [who, setWho] = useState("");
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");
  const [state, setState] = useState("idle"); // idle | saving | done | failed
  const [done, setDone] = useState(null);
  const [error, setError] = useState("");
  // Escalate only: whose work it is, where that came from, and their manager in ERPNext.
  const [whose, setWhose] = useState("");
  const [prefill, setPrefill] = useState(null); // {user, name, via, todo}
  const [mgr, setMgr] = useState(null);
  const [mgrState, setMgrState] = useState("idle"); // idle | loading | done | failed
  // New Task only: its subject, priority and the ERPNext document it concerns, if any.
  const [subject, setSubject] = useState("");
  const [prio, setPrio] = useState("Medium");
  const [docType, setDocType] = useState("");
  const [docName, setDocName] = useState("");
  // The business it goes to (businessOf), and whether it has to be chosen here.
  const [biz, setBiz] = useState("");
  const [pickBiz, setPickBiz] = useState(false);
  const [unsure, setUnsure] = useState(false);
  const first = useRef(null);
  // Back closes the dialog, not the screen under it (backstack.js).
  useLayer(Boolean(req), () => setReq(null), "dialog");

  useEffect(() => {
    const open = (e) => {
      const r = e.detail || {};
      const decision = r.kind === "decide" || r.kind === "review" || r.kind === "alert"
        || r.kind === "bulk_tasks" || CHANGES.has(r.kind);
      const k = KINDS[r.kind] || KINDS.assign;
      setReq({ ...r, kind: decision || KINDS[r.kind] ? r.kind : "assign" });
      setWho("");
      setDue(addDays(k.days));
      setNote(decision || r.kind === "new_task" ? "" : [r.title, r.detail].filter(Boolean).join("\n\n"));
      setSubject("");
      setPrio("Medium");
      setDocType("");
      setDocName("");
      setState("idle");
      setError("");
      setUnsure(false);
      setDone(null);
      const fixed = businessOf(r, scope);
      setBiz(fixed || r.preset_business || "");
      setPickBiz(!fixed);
      setMgr(null);
      setMgrState("idle");
      // A delegated task says who it was given to; otherwise ERPNext is asked (below).
      const given = r.kind === "escalate" && r.assignee
        ? { user: r.assignee, name: r.assignee_name || "", via: "the person the task was given to", todo: r.todo || null }
        : null;
      setPrefill(given);
      setWhose(given ? given.user : "");
    };
    window.addEventListener("cc-action", open);
    return () => window.removeEventListener("cc-action", open);
  }, [scope]);

  useEffect(() => {
    if (!req) return;
    const esc = (e) => e.key === "Escape" && setReq(null);
    document.addEventListener("keydown", esc);
    setTimeout(() => first.current?.focus(), 30);
    return () => document.removeEventListener("keydown", esc);
  }, [req]);

  // The people, and whose work it is, of the business it goes to: never another's.
  useEffect(() => {
    if (!req || !KINDS[req.kind]) return undefined;
    loadPeople(biz, setPeople);
    let stale = false;
    if (biz && req.kind === "escalate" && !req.assignee) {
      api.whoseWork({ business_code: biz, doctype: req.doctype || null, name: req.docname || null,
                      todo: req.todo || null, alert: req.alert || null })
        .then((w) => {
          if (stale || !w?.user) return;
          setPrefill(w);
          setWhose((cur) => cur || w.user);
        }).catch(() => {});
    }
    return () => { stale = true; };
  }, [req, biz]);

  // Escalate: whenever whose work it is changes, ask ERPNext who their manager is.
  const escalating = req?.kind === "escalate";
  useEffect(() => {
    if (!escalating || !whose || !biz) {
      setMgr(null);
      setMgrState("idle");
      return undefined;
    }
    let stale = false;
    setMgrState("loading");
    setMgr(null);
    api.managerOf({ business_code: biz, user: whose }).then((m) => {
      if (stale) return;
      setMgr(m || null);
      setMgrState("done");
      setWho(m?.found && m.manager_user !== whose ? m.manager_user : "");
    }).catch((err) => {
      if (stale) return;
      setMgr({ found: false, reason: err?.message || "ERPNext could not be asked.", fix: "Choose who it goes to yourself." });
      setMgrState("failed");
      setWho("");
    });
    return () => { stale = true; };
  }, [escalating, whose, biz]);

  if (!req) return null;
  if (req.kind === "bulk_tasks") {
    return <BulkChange req={req} scope={scope} close={() => setReq(null)} />;
  }
  if (CHANGES.has(req.kind)) {
    return <TaskChange req={req} scope={scope} close={() => setReq(null)} />;
  }
  if (!KINDS[req.kind]) {
    return <Decision req={req} scope={scope} note={note} setNote={setNote} close={() => setReq(null)} />;
  }
  const k = KINDS[req.kind];
  const creating = req.kind === "new_task";
  const doc = creating && docType.trim() && docName.trim()
    ? { doctype: docType.trim(), name: docName.trim() } : null;
  const person = people.find((p) => p.user === who);
  const owner = people.find((p) => p.user === whose);
  const ownerName = owner?.name || (prefill?.user === whose ? prefill?.name : "") || mgr?.user_name || whose;
  const toName = person?.name || (mgr?.manager_user === who ? mgr?.manager_name : "") || who;
  // The manager ERPNext names may not be on the people list (a disabled account, say):
  // they are still offered, by name, so the pre-filled choice is visible.
  const extra = (user, name) => (user && !people.some((p) => p.user === user)
    ? <option value={user}>{name || user}</option> : null);

  const submit = async (e) => {
    e.preventDefault();
    if (!biz) {
      setError("Choose the business this goes to.");
      return;
    }
    if (escalating && !whose) {
      setError("Choose whose work this is.");
      return;
    }
    if (!who) {
      setError(escalating ? "Choose who it is escalated to." : "Choose who this goes to.");
      return;
    }
    if (creating && !subject.trim()) {
      setError("Say what the task is.");
      return;
    }
    if (creating && !!docType.trim() !== !!docName.trim()) {
      setError("Give both the document type and its name, or leave both empty.");
      return;
    }
    if (escalating && who === whose) {
      setError("That is the person whose work it is. An escalation goes to someone else: their manager.");
      return;
    }
    setState("saving");
    setError("");
    setUnsure(false);
    try {
      const title = creating ? subject.trim()
        : `${k.lead}${req.title || `From ${brand.product}`}`.slice(0, 140);
      const res = await api.createTask({
        business_code: biz,
        subject: title.slice(0, 140),
        description: note,
        allocated_to: who,
        due_date: due || null,
        priority: creating ? prio : k.priority || null,
        reference_type: creating ? doc?.doctype || null : req.doctype || null,
        reference_name: creating ? doc?.name || null : req.docname || null,
        alert: req.alert || null,
        escalate_of: escalating ? whose : null,
        escalate_todo: escalating && prefill?.user === whose ? prefill?.todo || null : null,
      });
      // An alert that has become someone's To-Do says so, and says which.
      if (req.alert && res?.name) {
        await api.alertAct({ name: req.alert, action: "actioned", todo: res.name }).catch(() => {});
        window.dispatchEvent(new CustomEvent("cc-alerts-changed"));
      }
      window.dispatchEvent(new CustomEvent("cc-work-changed"));
      setDone({ ...(res || {}), person: res?.to_name || toName || who });
      setState("done");
    } catch (err) {
      setError(err?.message || "ERPNext did not accept it.");
      setUnsure(unsureOf(err));
      setState("failed");
    }
  };
  const bizName = realScopes().find((s) => s.code === biz)?.label;

  return (
    <div className="dlg-scrim" onMouseDown={(e) => e.target === e.currentTarget && setReq(null)}>
      <div className="dlg" role="dialog" aria-modal="true" aria-labelledby="dlg-t">
        {state === "done" ? (
          <>
            <div className="dlg-ok" aria-hidden="true">✓</div>
            <h3 id="dlg-t">{done.escalation && !done.already ? `Escalated to ${done.person}`
              : done.document && !done.already ? `Assigned to ${done.person}` : `On ${done.person}’s list`}</h3>
            <p className="dlg-sub">{done.said || "It is in ERPNext, from you."}</p>
            {done.notice ? (
              <p className={done.notified === false ? "dlg-err" : "dlg-hint"} role={done.notified === false ? "alert" : undefined}>
                {done.notice}
              </p>
            ) : null}
            {pickBiz && bizName ? <p className="dlg-hint">In {bizName}’s ERPNext.</p> : null}
            {done.escalation?.told_notice ? (
              <p className={done.escalation.told === false ? "dlg-err" : "dlg-hint"}
                 role={done.escalation.told === false ? "alert" : undefined}>
                {done.escalation.told_notice}
              </p>
            ) : null}
            <div className="dlg-acts">
              {done.document?.url ? (
                <a className="ap-act" href={done.document.url} target="_blank" rel="noreferrer">
                  Open {done.document.doctype} ↗
                </a>
              ) : null}
              {done.url ? (
                <a className="ap-act" href={done.url} target="_blank" rel="noreferrer">
                  Open the To-Do ↗
                </a>
              ) : null}
              <button type="button" className="ap-act pri" onClick={() => setReq(null)}>Done</button>
            </div>
          </>
        ) : (
          <form onSubmit={submit}>
            <h3 id="dlg-t">{k.title}</h3>
            {req.title ? <p className="dlg-sub">{req.title}</p> : null}
            {creating ? (
              <>
                <label htmlFor="dlg-subject">Subject</label>
                <input id="dlg-subject" ref={first} type="text" maxLength={140} value={subject}
                       onChange={(e) => setSubject(e.target.value)} placeholder="What needs doing" />
              </>
            ) : null}
            {req.owner ? <p className="dlg-hint">Suggested owner: {req.owner}</p> : null}
            {pickBiz ? (
              <>
                <label htmlFor="dlg-biz">Business</label>
                <select id="dlg-biz" value={biz} onChange={(e) => { setBiz(e.target.value); setWho(""); setWhose(""); setPrefill(null); }}>
                  <option value="">Choose the business it belongs to</option>
                  {realScopes().map((s) => <option key={s.code} value={s.code}>{s.label}</option>)}
                </select>
              </>
            ) : null}

            {escalating ? (
              <>
                <label htmlFor="dlg-whose">Whose work is this?</label>
                <select id="dlg-whose" ref={first} value={whose} onChange={(e) => setWhose(e.target.value)}>
                  <option value="">{!biz ? "Choose the business first" : people.length ? "Choose a person" : "Loading people…"}</option>
                  {extra(whose, ownerName)}
                  {people.map((p) => (
                    <option key={p.user} value={p.user}>{p.name}</option>
                  ))}
                </select>
                {prefill?.user && prefill.user === whose ? (
                  <p className="dlg-hint">Filled in from {prefill.via}.</p>
                ) : null}
                {mgrState === "loading" ? (
                  <p className="dlg-hint">Looking up {firstName(ownerName)}’s manager in ERPNext…</p>
                ) : null}
                {mgr && !mgr.found && mgrState !== "loading" ? (
                  <div className="dlg-err" role="status">
                    <b>No manager found in ERPNext.</b> {mgr.reason}
                    {mgr.fix ? <span className="dlg-fix">{mgr.fix}</span> : null}
                  </div>
                ) : null}

                <label htmlFor="dlg-who">Escalate to</label>
                <select id="dlg-who" value={who} onChange={(e) => setWho(e.target.value)}>
                  <option value="">{mgr && !mgr.found ? "Choose someone yourself" : "Choose a person"}</option>
                  {mgr?.found ? extra(mgr.manager_user, mgr.manager_name) : null}
                  {people.filter((p) => p.user !== whose).map((p) => (
                    <option key={p.user} value={p.user}>{p.name}</option>
                  ))}
                </select>
                {whose && mgrState !== "loading" && escalationPlan(mgr, ownerName, who, toName) ? (
                  <p className="dlg-plan">{escalationPlan(mgr, ownerName, who, toName)}</p>
                ) : null}
              </>
            ) : (
              <>
                <label htmlFor="dlg-who">To</label>
                <select id="dlg-who" ref={creating ? null : first} value={who} onChange={(e) => setWho(e.target.value)}>
                  <option value="">{!biz ? "Choose the business first" : people.length ? "Choose a person" : "Loading people…"}</option>
                  {people.map((p) => (
                    <option key={p.user} value={p.user}>{p.name}</option>
                  ))}
                </select>
              </>
            )}

            <label htmlFor="dlg-due">By</label>
            <input id="dlg-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />

            {creating ? (
              <>
                <label htmlFor="dlg-prio">Priority</label>
                <select id="dlg-prio" value={prio} onChange={(e) => setPrio(e.target.value)}>
                  {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </>
            ) : null}

            <label htmlFor="dlg-note">{creating ? "Details" : "Note"}</label>
            <textarea id="dlg-note" rows={creating ? 4 : 5} value={note} onChange={(e) => setNote(e.target.value)} />

            {creating ? (
              <fieldset className="dlg-doc">
                <legend>ERPNext Document (Optional)</legend>
                <div className="dlg-two">
                  <div>
                    <label htmlFor="dlg-doctype">Document Type</label>
                    <input id="dlg-doctype" type="text" list="dlg-doctypes" value={docType}
                           onChange={(e) => setDocType(e.target.value)} placeholder="Choose or type one" />
                    <datalist id="dlg-doctypes">
                      {DOC_TYPES.map((d) => <option key={d} value={d} />)}
                    </datalist>
                  </div>
                  <div>
                    <label htmlFor="dlg-docname">Document Name</label>
                    <input id="dlg-docname" type="text" value={docName}
                           onChange={(e) => setDocName(e.target.value)} placeholder="Its ID in ERPNext" />
                  </div>
                </div>
              </fieldset>
            ) : null}

            <Failure error={error} unsure={unsure} />
            <div className="dlg-acts">
              <button type="button" className="ap-act" onClick={() => setReq(null)}>Cancel</button>
              <button type="submit" className="ap-act pri" disabled={state === "saving"}>
                {state === "saving" ? "Sending…" : k.verb}
              </button>
            </div>
            <p className="dlg-foot">{plan(req, who ? toName : "", creating ? doc : null)}</p>
          </form>
        )}
      </div>
    </div>
  );
}


/** Document types offered on New Task; any other may be typed. */
const DOC_TYPES = ["Sales Invoice", "Sales Order", "Quotation", "Customer", "Purchase Order",
  "Purchase Invoice", "Supplier", "Payment Entry", "Journal Entry", "Delivery Note",
  "Purchase Receipt", "Material Request", "Stock Entry", "Item", "Issue", "Project", "Task",
  "Employee"];

const CHANGE_WORDS = {
  reassign: { title: "Reassign", verb: "Reassign", done: "Reassigned" },
  cancel_task: { title: "Cancel Assignment", verb: "Cancel Assignment", done: "Assignment Cancelled" },
  close_task: { title: "Close Task", verb: "Close Task", done: "Task Closed" },
  edit_task: { title: "Edit Date And Priority", verb: "Save Changes", done: "Changed" },
};

/** Reassign, withdraw, or change the date and priority of open work handed out. Asks first. */
function TaskChange({ req, scope, close }) {
  const w = CHANGE_WORDS[req.kind];
  // The task's own business (legacy/work.js taskRequest), never the screen's scope.
  const business = businessOf(req, scope);
  const [people, setPeople] = useState(peopleCache[business] || []);
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");
  const [due, setDue] = useState(req.date || "");
  const [prio, setPrio] = useState(PRIORITIES.includes(req.priority) ? req.priority : "Medium");
  const [state, setState] = useState("idle");
  const [error, setError] = useState("");
  const [unsure, setUnsure] = useState(false);
  const [res, setRes] = useState(null);
  const them = req.assignee_name || req.assignee || "them";
  const onDoc = req.doctype && req.docname;

  useEffect(() => {
    if (req.kind !== "reassign" || people.length) return;
    loadPeople(business, setPeople);
  }, [req.kind, business, people.length]);

  useEffect(() => {
    const esc = (e) => e.key === "Escape" && close();
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [close]);

  const toName = people.find((p) => p.user === to)?.name || to;
  const what = req.kind === "reassign"
    ? (onDoc
      ? `ERPNext assigns ${req.doctype} ${req.docname} to ${to ? toName : "the person you choose"} first, and only then takes it off ${them}, `
        + "so both are notified there and it is never with no one. A comment on the document says you moved it."
      : `A new To-Do with the same subject and details goes to ${to ? toName : "the person you choose"}, who is mentioned on it; `
        + `only then is ${them}’s To-Do cancelled in ERPNext. A comment on the old To-Do tells ${them}.`)
    : req.kind === "cancel_task"
      ? (onDoc
        ? `ERPNext takes ${req.doctype} ${req.docname} off ${them}: their To-Do is cancelled and they leave Assigned To. `
          + "A comment on the document tells them it was withdrawn."
        : `${them}’s To-Do is cancelled in ERPNext, and a comment on it tells them it was withdrawn.`)
      : req.kind === "close_task"
        ? `The To-Do is closed in ERPNext, as finished or no longer needed. A short comment on it says you closed it; `
          + `${them} is not mentioned, so ERPNext does not notify them, and it does not count as work they marked done.`
        : `The To-Do’s date and priority change in ERPNext, and a comment on it tells ${them} what changed.`;

  const submit = async (e) => {
    e.preventDefault();
    if (req.kind === "reassign" && !to) {
      setError("Choose who it goes to now.");
      return;
    }
    if (!business) {
      setError("Open this task from the business it belongs to, then try again.");
      return;
    }
    setState("saving");
    setError("");
    setUnsure(false);
    try {
      const got = req.kind === "reassign"
        ? await api.reassignTask({ business_code: business, todo: req.todo, to_user: to, note })
        : req.kind === "cancel_task"
          ? await api.cancelTask({ business_code: business, todo: req.todo, reason: note })
          : req.kind === "close_task"
          ? await api.closeTask({ business_code: business, todo: req.todo, note })
          : await api.updateTask({ business_code: business, todo: req.todo, due_date: due || "", priority: prio });
      setRes(got || {});
      setState("done");
      window.dispatchEvent(new CustomEvent("cc-work-changed"));
    } catch (err) {
      setError(err?.message || "ERPNext did not accept it.");
      setUnsure(unsureOf(err));
      setState("failed");
      window.dispatchEvent(new CustomEvent("cc-work-changed"));
    }
  };

  const notice = (text, ok) => (text ? (
    <p className={ok === false ? "dlg-err" : "dlg-hint"} role={ok === false ? "alert" : undefined}>{text}</p>
  ) : null);

  return (
    <div className="dlg-scrim" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div className="dlg" role="dialog" aria-modal="true" aria-labelledby="dlg-t">
        {state === "done" ? (
          <>
            <div className="dlg-ok" aria-hidden="true">✓</div>
            <h3 id="dlg-t">{req.kind === "reassign" ? `Reassigned to ${res.to_name || toName}` : w.done}</h3>
            <p className="dlg-sub">{res.said || "Done in ERPNext, as you."}</p>
            {notice(res.removed_notice, res.removed === true)}
            {notice(res.notice, res.notified)}
            {notice(res.told_notice, res.told)}
            <div className="dlg-acts">
              {res.url ? (
                <a className="ap-act" href={res.url} target="_blank" rel="noreferrer">Open the To-Do ↗</a>
              ) : null}
              <button type="button" className="ap-act pri" onClick={close}>Done</button>
            </div>
          </>
        ) : (
          <form onSubmit={submit}>
            <h3 id="dlg-t">{w.title}</h3>
            <p className="dlg-sub">{req.title}</p>
            <p className="dlg-hint">Now with {them}{req.date ? `, due ${new Date(`${req.date}T00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}` : ""}.</p>
            {req.kind === "reassign" ? (
              <>
                <label htmlFor="dlg-to">Give it to</label>
                <select id="dlg-to" value={to} onChange={(e) => setTo(e.target.value)} autoFocus>
                  <option value="">{people.length ? "Choose a person" : "Loading people…"}</option>
                  {people.filter((p) => p.user !== req.assignee).map((p) => (
                    <option key={p.user} value={p.user}>{p.name}</option>
                  ))}
                </select>
                <label htmlFor="dlg-note">Note (optional)</label>
                <textarea id="dlg-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
              </>
            ) : null}
            {req.kind === "cancel_task" ? (
              <>
                <p className="dlg-plan">Cancel this assignment? It is for work given to the wrong person by mistake.</p>
                <label htmlFor="dlg-note">Reason (optional)</label>
                <textarea id="dlg-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
              </>
            ) : null}
            {req.kind === "close_task" ? (
              <>
                <p className="dlg-plan">Close this task? Use it when the work is finished or no longer needed.</p>
                <label htmlFor="dlg-note">Note (optional)</label>
                <textarea id="dlg-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
              </>
            ) : null}
            {req.kind === "edit_task" ? (
              <div className="dlg-two">
                <div>
                  <label htmlFor="dlg-due">Due date</label>
                  <input id="dlg-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} autoFocus />
                </div>
                <div>
                  <label htmlFor="dlg-prio">Priority</label>
                  <select id="dlg-prio" value={prio} onChange={(e) => setPrio(e.target.value)}>
                    {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
              </div>
            ) : null}
            <Failure error={error} unsure={unsure} />
            <div className="dlg-acts">
              <button type="button" className="ap-act" onClick={close}>{req.kind === "cancel_task" ? "Keep It" : "Cancel"}</button>
              <button type="submit" className={`ap-act pri${req.kind === "cancel_task" ? " dgr" : ""}`} disabled={state === "saving"}>
                {state === "saving" ? "Working…" : w.verb}
              </button>
            </div>
            <p className="dlg-foot">{what}</p>
          </form>
        )}
      </div>
    </div>
  );
}

/** "Close 12 tasks: Ama (5), Kofi (4), Esi (3)" -- how many, and to whom, most first. */
function bulkPlan(action, tasks) {
  const by = new Map();
  tasks.forEach((t) => {
    const who = firstName(t.to_name || t.to) || "No one";
    by.set(who, (by.get(who) || 0) + 1);
  });
  const people = [...by.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([who, n]) => `${who} (${n})`).join(", ");
  const n = tasks.length;
  return `${action === "close" ? "Close" : "Cancel"} ${n} ${n === 1 ? "task" : "tasks"}: ${people}`;
}

/** Close Selected / Cancel Selected: says how many and to whom first, then one by one, as
 *  a job on the server (api/actions bulk_tasks) that this follows (bulk_status) until it
 *  has finished: how many were done, which could not be and why, and -- for Cancel --
 *  how many were told and who was not, and why. Closing the dialog does not stop it. */
function BulkChange({ req, scope, close }) {
  const closing = req.action === "close";
  const business = businessOf(req, scope);
  const [note, setNote] = useState("");
  const [state, setState] = useState("idle"); // idle | saving | running | done | failed
  const [error, setError] = useState("");
  const [res, setRes] = useState(null);
  const tasks = req.tasks || [];
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  useEffect(() => {
    const esc = (e) => e.key === "Escape" && state !== "saving" && close();
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [close, state]);

  const follow = async (got) => {
    let cur = got || {};
    while (alive.current && !cur.finished && cur.state !== "unknown") {
      setRes(cur);
      // eslint-disable-next-line no-await-in-loop
      await new Promise((ok) => { setTimeout(ok, 1500); });
      try {
        // eslint-disable-next-line no-await-in-loop
        cur = (await api.bulkStatus(cur.bulk_id)) || cur;
      } catch {
        /* a missed poll is asked again */
      }
    }
    if (!alive.current) return;
    setRes(cur);
    setState("done");
    window.dispatchEvent(new CustomEvent("cc-tasks-unselect"));
    window.dispatchEvent(new CustomEvent("cc-work-changed"));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!business) {
      setError("Open these tasks from the business they belong to, then try again.");
      return;
    }
    setState("saving");
    setError("");
    try {
      const got = await api.bulkTasks({ business_code: business, action: req.action,
                                        todos: tasks.map((t) => t.name), note });
      setState("running");
      follow(got);
    } catch (err) {
      setError(err?.message || "ERPNext did not accept it.");
      setState("failed");
    }
  };

  const titleOf = Object.fromEntries(tasks.map((t) => [t.name, t.title]));
  const failed = res?.failed || [];
  const notTold = res?.not_told || [];
  const working = state === "saving" || state === "running";
  const shown = state === "done" || state === "running";
  return (
    <div className="dlg-scrim" onMouseDown={(e) => e.target === e.currentTarget && state !== "saving" && close()}>
      <div className="dlg" role="dialog" aria-modal="true" aria-labelledby="dlg-t">
        {shown ? (
          <>
            <div className="dlg-ok" aria-hidden="true">
              {state === "running" ? "…" : failed.length || notTold.length || res?.state !== "done" ? "!" : "✓"}
            </div>
            <h3 id="dlg-t">{state === "running" ? (closing ? "Closing Tasks" : "Cancelling Assignments")
              : closing ? "Tasks Closed" : "Assignments Cancelled"}</h3>
            <p className="dlg-sub" role="status">{res?.said || "Starting…"}</p>
            {failed.length ? (
              <>
                <p className="dlg-hint">Not {closing ? "closed" : "cancelled"}:</p>
                <ul className="dlg-fails">
                  {failed.slice(0, 50).map((f) => (
                    <li key={f.todo}>
                      <b>{titleOf[f.todo] || f.todo}</b>{" "}
                      {f.unsure ? "ERPNext did not confirm it; it may have gone through. " : ""}{f.reason}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            {notTold.length ? (
              <>
                <p className="dlg-hint">Cancelled, but not told:</p>
                <ul className="dlg-fails">
                  {notTold.slice(0, 50).map((f) => (
                    <li key={f.todo}><b>{f.to_name || f.to || titleOf[f.todo] || f.todo}</b> {f.reason}</li>
                  ))}
                </ul>
              </>
            ) : null}
            <div className="dlg-acts">
              <button type="button" className="ap-act pri" onClick={close}>
                {state === "running" ? "Close (It Carries On)" : "Done"}
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={submit}>
            <h3 id="dlg-t">{closing ? "Close Selected" : "Cancel Selected"}</h3>
            <p className="dlg-plan">{bulkPlan(req.action, tasks)}</p>
            <p className="dlg-hint">{closing
              ? "Each To-Do is closed in ERPNext, as finished or no longer needed, with a short comment saying you closed it. No one is mentioned, so ERPNext notifies no one."
              : "Each assignment is withdrawn in ERPNext, as Cancel Assignment does, and each person is told by a mention that they no longer need to do it."}</p>
            <label htmlFor="dlg-note">{closing ? "Note (optional)" : "Reason (optional)"}</label>
            <textarea id="dlg-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
            {error ? <div className="dlg-err" role="alert">{error}</div> : null}
            <div className="dlg-acts">
              <button type="button" className="ap-act" onClick={close} disabled={working}>Keep Them</button>
              <button type="submit" className={`ap-act pri${closing ? "" : " dgr"}`} disabled={working}>
                {working ? "Working…" : closing ? `Close ${tasks.length}` : `Cancel ${tasks.length}`}
              </button>
            </div>
            <p className="dlg-foot">They are sent one by one; one that ERPNext refuses does not stop the others, and you are told which and why, and who was not told.</p>
          </form>
        )}
      </div>
    </div>
  );
}

/** Approve / reject a document, or accept / send back handed-out work. Asks first. */
const ALERT_VERBS = {
  defer: ["Defer", "It leaves your list until the date you choose, then comes back if the condition is still there.", "Deferred"],
  dismiss: ["Dismiss", "It stays dismissed while the condition lasts. Your reason is kept so the rule can be tuned.", "Dismissed"],
  false_positive: ["Not a real problem", "Marked as a false alarm. Your reason is kept so the rule that raised it can be corrected.", "Marked not a real problem"],
};

function inDays(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function Decision({ req, scope, note, setNote, close }) {
  const business = businessOf(req, scope);
  const [state, setState] = useState("idle");
  const [error, setError] = useState("");
  const [unsure, setUnsure] = useState(false);
  const [result, setResult] = useState(null);
  const [until, setUntil] = useState(inDays(7));
  const alertVerb = req.kind === "alert" ? ALERT_VERBS[req.verb] : null;
  const back = req.kind === "review" && req.verdict === "return";
  const needsNote = back || !!alertVerb;
  const verb = alertVerb ? alertVerb[0] : req.kind === "decide" ? req.action : back ? "Send it back" : "Accept it";
  const what = alertVerb ? alertVerb[1] : req.kind === "decide"
    ? `This applies “${req.action}” to ${req.doctype} ${req.name} in ERPNext, as you. ERPNext checks that your role may take this step, and records it in the document's history.`
    : back
      ? "The To-Do reopens on their list, with your note as a comment they will see."
      : "The To-Do is tagged Accepted and leaves your Delegated Tasks Done.";

  const submit = async (e) => {
    e.preventDefault();
    if (needsNote && !note.trim()) {
      setError(back ? "Say what is still needed, so they know what to do."
        : "Give a reason. It is kept so the rule can be tuned.");
      return;
    }
    if (!alertVerb && !business) {
      setError("Open this from the business it belongs to, then try again.");
      return;
    }
    setState("saving");
    setError("");
    setUnsure(false);
    try {
      // A decision carries the state and stamp its card showed: refused, never applied to
      // a later step, when someone else has moved the document on (api/actions).
      const res = alertVerb
        ? await api.alertAct({ name: req.alert, action: req.verb, reason: note,
                               until: req.verb === "defer" ? until : null })
        : req.kind === "decide"
          ? await api.decide({ business_code: business, doctype: req.doctype, name: req.name, action: req.action,
                               expected_state: req.state, expected_modified: req.modified, state_field: req.state_field })
          : await api.review({ business_code: business, todo: req.todo, verdict: req.verdict, note });
      setResult(res || {});
      setState("done");
      window.dispatchEvent(new CustomEvent(alertVerb ? "cc-alerts-changed" : "cc-work-changed"));
    } catch (err) {
      setError(err?.message || "ERPNext did not accept it.");
      setUnsure(unsureOf(err));
      setState("failed");
      // A card the document has moved on from is read again, so the queue shows where it is.
      if (err?.excType === "MovedOn") window.dispatchEvent(new CustomEvent("cc-work-changed"));
    }
  };

  return (
    <div className="dlg-scrim" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div className="dlg" role="dialog" aria-modal="true" aria-labelledby="dlg-t">
        {state === "done" ? (
          <>
            <div className="dlg-ok" aria-hidden="true">✓</div>
            <h3 id="dlg-t">{alertVerb ? alertVerb[2] : req.kind === "decide" ? `${req.action}: done` : back ? "Sent back" : "Accepted"}</h3>
            <p className="dlg-sub">
              {alertVerb
                ? req.verb === "defer"
                  ? `It comes back on ${new Date(`${until}T00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" })} if the condition is still there.`
                  : "It is off the list, with your reason on record."
                : req.kind === "decide"
                ? `${req.doctype} ${req.name} is now at “${result.workflow_state || "its next step"}”.`
                : back ? "It is open on their list again, with your note." : "It is off your list."}
            </p>
            {back && result?.notice ? (
              <p className={result.notified === false ? "dlg-err" : "dlg-hint"} role={result.notified === false ? "alert" : undefined}>
                {result.notice}
              </p>
            ) : null}
            <div className="dlg-acts">
              <button type="button" className="ap-act pri" onClick={close}>Done</button>
            </div>
          </>
        ) : (
          <form onSubmit={submit}>
            <h3 id="dlg-t">{verb}</h3>
            <p className="dlg-sub">{req.title}</p>
            <p className="dlg-hint">{what}</p>
            {alertVerb && req.verb === "defer" ? (
              <>
                <label htmlFor="dlg-until">Bring it back on</label>
                <input id="dlg-until" type="date" value={until} min={inDays(1)} onChange={(e) => setUntil(e.target.value)} />
              </>
            ) : null}
            {req.kind === "review" || alertVerb ? (
              <>
                <label htmlFor="dlg-note">{alertVerb ? "Reason" : back ? "What is still needed" : "Note (optional)"}</label>
                <textarea id="dlg-note" rows={4} value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
              </>
            ) : null}
            <Failure error={error} unsure={unsure} />
            <div className="dlg-acts">
              <button type="button" className="ap-act" onClick={close}>Cancel</button>
              <button type="submit" className="ap-act pri" disabled={state === "saving"} autoFocus={req.kind === "decide"}>
                {state === "saving" ? "Working…" : verb}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
