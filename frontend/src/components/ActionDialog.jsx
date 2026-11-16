import React, { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import { brand } from "../api/boot.js";

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
 */

const KINDS = {
  assign: { title: "Assign this", verb: "Assign", lead: "", days: 3 },
  evidence: { title: "Request evidence", verb: "Send the request", lead: "Please send the evidence for: ", days: 3 },
  escalate: { title: "Escalate", verb: "Escalate", lead: "Escalated: ", days: 1, priority: "High" },
  finding: { title: "Raise as a finding", verb: "Raise it", lead: "Finding: ", days: 7 },
};

let peopleCache = {};

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
function plan(req, name) {
  const them = name || "the person you choose";
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
  const first = useRef(null);

  useEffect(() => {
    const open = (e) => {
      const r = e.detail || {};
      const decision = r.kind === "decide" || r.kind === "review" || r.kind === "alert";
      const k = KINDS[r.kind] || KINDS.assign;
      setReq({ ...r, kind: decision || KINDS[r.kind] ? r.kind : "assign" });
      setWho("");
      setDue(addDays(k.days));
      setNote(decision ? "" : [r.title, r.detail].filter(Boolean).join("\n\n"));
      setState("idle");
      setError("");
      setDone(null);
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
  }, []);

  useEffect(() => {
    if (!req) return;
    const esc = (e) => e.key === "Escape" && setReq(null);
    document.addEventListener("keydown", esc);
    if (!KINDS[req.kind]) return () => document.removeEventListener("keydown", esc);
    const key = scope || "__all__";
    if (peopleCache[key]) {
      setPeople(peopleCache[key]);
    } else {
      api.people(scope).then((p) => {
        peopleCache[key] = p || [];
        setPeople(peopleCache[key]);
      }).catch(() => setPeople([]));
    }
    let stale = false;
    if (req.kind === "escalate" && !req.assignee) {
      api.whoseWork({ business_code: scope, doctype: req.doctype || null, name: req.docname || null,
                      todo: req.todo || null, alert: req.alert || null })
        .then((w) => {
          if (stale || !w?.user) return;
          setPrefill(w);
          setWhose((cur) => cur || w.user);
        }).catch(() => {});
    }
    setTimeout(() => first.current?.focus(), 30);
    return () => {
      stale = true;
      document.removeEventListener("keydown", esc);
    };
  }, [req, scope]);

  // Escalate: whenever whose work it is changes, ask ERPNext who their manager is.
  const escalating = req?.kind === "escalate";
  useEffect(() => {
    if (!escalating || !whose) {
      setMgr(null);
      setMgrState("idle");
      return undefined;
    }
    let stale = false;
    setMgrState("loading");
    setMgr(null);
    api.managerOf({ business_code: scope, user: whose }).then((m) => {
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
  }, [escalating, whose, scope]);

  if (!req) return null;
  if (!KINDS[req.kind]) {
    return <Decision req={req} scope={scope} note={note} setNote={setNote} close={() => setReq(null)} />;
  }
  const k = KINDS[req.kind];
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
    if (escalating && !whose) {
      setError("Choose whose work this is.");
      return;
    }
    if (!who) {
      setError(escalating ? "Choose who it is escalated to." : "Choose who this goes to.");
      return;
    }
    if (escalating && who === whose) {
      setError("That is the person whose work it is. An escalation goes to someone else: their manager.");
      return;
    }
    setState("saving");
    setError("");
    try {
      const subject = `${k.lead}${req.title || `From ${brand.product}`}`.slice(0, 140);
      const res = await api.createTask({
        business_code: scope,
        subject,
        description: note,
        allocated_to: who,
        due_date: due || null,
        priority: k.priority || null,
        reference_type: req.doctype || null,
        reference_name: req.docname || null,
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
      setState("failed");
    }
  };

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
            <p className="dlg-sub">{req.title}</p>
            {req.owner ? <p className="dlg-hint">Suggested owner: {req.owner}</p> : null}

            {escalating ? (
              <>
                <label htmlFor="dlg-whose">Whose work is this?</label>
                <select id="dlg-whose" ref={first} value={whose} onChange={(e) => setWhose(e.target.value)}>
                  <option value="">{people.length ? "Choose a person" : "Loading people…"}</option>
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
                <select id="dlg-who" ref={first} value={who} onChange={(e) => setWho(e.target.value)}>
                  <option value="">{people.length ? "Choose a person" : "Loading people…"}</option>
                  {people.map((p) => (
                    <option key={p.user} value={p.user}>{p.name}</option>
                  ))}
                </select>
              </>
            )}

            <label htmlFor="dlg-due">By</label>
            <input id="dlg-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />

            <label htmlFor="dlg-note">Note</label>
            <textarea id="dlg-note" rows={5} value={note} onChange={(e) => setNote(e.target.value)} />

            {error ? <div className="dlg-err" role="alert">{error}</div> : null}
            <div className="dlg-acts">
              <button type="button" className="ap-act" onClick={() => setReq(null)}>Cancel</button>
              <button type="submit" className="ap-act pri" disabled={state === "saving"}>
                {state === "saving" ? "Sending…" : k.verb}
              </button>
            </div>
            <p className="dlg-foot">{plan(req, who ? toName : "")}</p>
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
  const [state, setState] = useState("idle");
  const [error, setError] = useState("");
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
    setState("saving");
    setError("");
    try {
      const res = alertVerb
        ? await api.alertAct({ name: req.alert, action: req.verb, reason: note,
                               until: req.verb === "defer" ? until : null })
        : req.kind === "decide"
          ? await api.decide({ business_code: scope, doctype: req.doctype, name: req.name, action: req.action })
          : await api.review({ business_code: scope, todo: req.todo, verdict: req.verdict, note });
      setResult(res || {});
      setState("done");
      window.dispatchEvent(new CustomEvent(alertVerb ? "cc-alerts-changed" : "cc-work-changed"));
    } catch (err) {
      setError(err?.message || "ERPNext did not accept it.");
      setState("failed");
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
            {error ? <div className="dlg-err" role="alert">{error}</div> : null}
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
